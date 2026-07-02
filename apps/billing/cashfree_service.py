import base64
import hashlib
import hmac
import logging
import uuid
from decimal import Decimal, InvalidOperation

import requests as http_requests
from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

logger = logging.getLogger(__name__)

_MAX_WEBHOOK_AMOUNT = Decimal("1000000")


class CashfreeService:

    SANDBOX_URL = "https://sandbox.cashfree.com/pg"
    PRODUCTION_URL = "https://api.cashfree.com/pg"
    API_VERSION = "2023-08-01"

    @classmethod
    def _base_url(cls):
        env = getattr(settings, "CASHFREE_ENVIRONMENT", "sandbox")
        return cls.SANDBOX_URL if env == "sandbox" else cls.PRODUCTION_URL

    @classmethod
    def _headers(cls):
        return {
            "x-api-version": cls.API_VERSION,
            "x-client-id": getattr(settings, "CASHFREE_APP_ID", ""),
            "x-client-secret": getattr(settings, "CASHFREE_SECRET_KEY", ""),
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    @classmethod
    def create_order(cls, organization, amount, plan_id="", idempotency_key=""):
        from apps.billing.models import Payment

        order_id = f"SUC-{uuid.uuid4().hex[:12].upper()}"

        with transaction.atomic():
            if idempotency_key:
                existing = (
                    Payment.objects.select_for_update()
                    .filter(idempotency_key=idempotency_key)
                    .first()
                )
                if existing:
                    return existing

            payment = Payment.objects.create(
                organization=organization,
                cashfree_order_id=order_id,
                amount=amount,
                currency="INR",
                status="pending",
                plan_id_snapshot=plan_id,
                idempotency_key=idempotency_key or None,
            )

        app_id = getattr(settings, "CASHFREE_APP_ID", "")
        if not app_id or app_id in ("dev-placeholder", "test", "sandbox"):
            with transaction.atomic():
                payment.cashfree_session_id = f"dev_session_{order_id}"
                payment.save(update_fields=["cashfree_session_id", "updated_at"])
            logger.warning(
                "CASHFREE_APP_ID not configured — dev dummy session",
                extra={"org_id": str(organization.pk), "order_id": order_id},
            )
            return payment

        admin = organization.users.filter(role__in=["owner", "admin"]).first()
        payload = {
            "order_id": order_id,
            "order_amount": str(amount),
            "order_currency": "INR",
            "customer_details": {
                "customer_id": str(organization.pk),
                "customer_phone": (
                    getattr(admin, "phone", "9999999999") if admin else "9999999999"
                ),
                "customer_email": (
                    getattr(admin, "email", f"org_{organization.pk}@example.com")
                    if admin
                    else f"org_{organization.pk}@example.com"
                ),
                "customer_name": admin.name if admin else organization.name,
            },
        }

        try:
            resp = http_requests.post(
                f"{cls._base_url()}/orders",
                json=payload,
                headers=cls._headers(),
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()

            with transaction.atomic():
                payment.cashfree_session_id = data.get("payment_session_id", "")
                payment.save(update_fields=["cashfree_session_id", "updated_at"])

            return payment

        except http_requests.RequestException as exc:
            logger.error(
                "Cashfree create_order failed",
                extra={
                    "org_id": str(organization.pk),
                    "order_id": order_id,
                    "error_type": type(exc).__name__,
                },
            )
            payment.delete()
            raise ValidationError(
                {"detail": "Payment service temporarily unavailable. Please try again."}
            )

    @classmethod
    def verify_webhook_signature(cls, timestamp, raw_body, signature):
        secret = getattr(settings, "CASHFREE_SECRET_KEY", "")
        if not secret:
            return False

        data_to_sign = (timestamp + raw_body).encode("utf-8")
        expected = base64.b64encode(
            hmac.new(secret.encode("utf-8"), data_to_sign, hashlib.sha256).digest()
        ).decode("utf-8")
        return hmac.compare_digest(expected, signature)

    @classmethod
    def verify_client_signature(cls, order_id, order_amount, payment_id, signature):
        secret = getattr(settings, "CASHFREE_SECRET_KEY", "")
        data_to_sign = f"{order_id}{order_amount}{payment_id}"
        expected = hmac.new(
            secret.encode("utf-8"),
            data_to_sign.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    @classmethod
    def get_order_status(cls, order_id):
        try:
            resp = http_requests.get(
                f"{cls._base_url()}/orders/{order_id}",
                headers=cls._headers(),
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json()
        except http_requests.RequestException as exc:
            logger.error(
                "Cashfree get_order_status failed",
                extra={"order_id": order_id, "error_type": type(exc).__name__},
            )
            return None

    @classmethod
    def initiate_refund(cls, order_id, refund_amount, refund_id=None, reason=""):
        refund_id = refund_id or f"REF-{uuid.uuid4().hex[:12].upper()}"
        payload = {
            "refund_amount": str(refund_amount),
            "refund_id": refund_id,
            "refund_note": reason or "Admin-initiated refund",
        }

        try:
            resp = http_requests.post(
                f"{cls._base_url()}/orders/{order_id}/refunds",
                json=payload,
                headers=cls._headers(),
                timeout=15,
            )
            resp.raise_for_status()
            return resp.json()
        except http_requests.RequestException as exc:
            logger.error(
                "Cashfree initiate_refund failed",
                extra={
                    "order_id": order_id,
                    "refund_id": refund_id,
                    "error_type": type(exc).__name__,
                },
            )
            raise ValidationError({"detail": "Refund service temporarily unavailable."})


class WebhookProcessor:

    _PAYMENT_VALID_TRANSITIONS = {
        "pending": {"completed", "failed"},
        "completed": {"refunded"},
        "failed": set(),
        "refunded": set(),
    }

    @classmethod
    def _transition_payment_status(cls, payment, new_status):
        allowed = cls._PAYMENT_VALID_TRANSITIONS.get(payment.status, set())
        if new_status not in allowed:
            raise ValueError(
                f"Invalid payment status transition: {payment.status!r} → {new_status!r}"
            )
        payment.status = new_status

    @staticmethod
    @transaction.atomic
    def handle_payment_success(data):
        from apps.accounts.models import Organization
        from apps.billing.models import LedgerEntry, Payment, ProcessedWebhookEvent
        from apps.core.models import AuditLog

        order_data = data.get("data", {}).get("order", {})
        payment_data = data.get("data", {}).get("payment", {})
        order_id = order_data.get("order_id", "")
        payment_id = str(payment_data.get("cf_payment_id", ""))

        if not order_id or not payment_id:
            return

        try:
            _evt, _created = ProcessedWebhookEvent.objects.get_or_create(
                provider="cashfree",
                event_id=payment_id,
                defaults={"event_type": "PAYMENT_SUCCESS_WEBHOOK", "payload": data},
            )
        except IntegrityError:
            logger.info("Webhook already processed (race)", extra={"payment_id": payment_id})
            return
        if not _created:
            logger.info("Webhook already processed", extra={"payment_id": payment_id})
            return

        try:
            payment = Payment.objects.select_for_update().get(cashfree_order_id=order_id)
        except Payment.DoesNotExist:
            logger.error("Payment not found for webhook", extra={"order_id": order_id})
            return

        if payment.status == "completed":
            return

        try:
            webhook_amount = Decimal(str(order_data.get("order_amount", "0")))
        except (InvalidOperation, ValueError):
            logger.error("Invalid amount in webhook", extra={"order_id": order_id})
            return

        webhook_amount = min(webhook_amount, _MAX_WEBHOOK_AMOUNT)

        if webhook_amount != payment.amount:
            logger.error(
                "Webhook amount mismatch",
                extra={
                    "order_id": order_id,
                    "expected": str(payment.amount),
                    "received": str(webhook_amount),
                },
            )
            return

        payment.cashfree_payment_id = payment_id
        WebhookProcessor._transition_payment_status(payment, "completed")
        payment.save(update_fields=["cashfree_payment_id", "status", "updated_at"])

        org = payment.organization
        plan_slug = payment.plan_id_snapshot
        if plan_slug:
            from apps.billing.models import Plan, Subscription

            try:
                plan = Plan.objects.get(slug=plan_slug, is_active=True)
                Subscription.objects.filter(
                    organization=org, status__in=["active", "trialing"]
                ).update(
                    status="cancelled",
                    cancelled_at=timezone.now(),
                    updated_at=timezone.now(),
                )

                Subscription.objects.create(
                    organization=org,
                    plan=plan,
                    status="active",
                    current_period_start=timezone.now(),
                )

                Organization.objects.filter(pk=org.pk).update(plan=plan, updated_at=timezone.now())
                org.refresh_from_db()
            except Plan.DoesNotExist:
                logger.error("Plan not found for payment", extra={"plan_slug": plan_slug})

        LedgerEntry.objects.create(
            organization=org,
            entry_type="payment",
            amount=webhook_amount,
            currency=payment.currency,
            reference_type="Payment",
            reference_id=str(payment.pk),
            description=f"Cashfree payment confirmed. Order: {order_id}",
        )

        try:
            AuditLog.objects.create(
                organization=org,
                action="PAYMENT_RECEIVED",
                resource_type="Payment",
                resource_id=str(payment.pk),
                changes={
                    "order_id": order_id,
                    "payment_id": payment_id,
                    "amount": str(webhook_amount),
                },
            )
        except Exception as audit_exc:
            logger.warning(
                "AuditLog failed for PAYMENT_RECEIVED: %s",
                audit_exc,
                extra={"order_id": order_id},
            )

        logger.info(
            "Payment processed successfully",
            extra={
                "org_id": str(org.pk),
                "order_id": order_id,
                "amount": str(webhook_amount),
            },
        )

    @staticmethod
    @transaction.atomic
    def handle_payment_failed(data):
        from apps.billing.models import Payment

        order_data = data.get("data", {}).get("order", {})
        order_id = order_data.get("order_id", "")

        if not order_id:
            return

        try:
            payment = Payment.objects.select_for_update().get(cashfree_order_id=order_id)
        except Payment.DoesNotExist:
            return

        WebhookProcessor._transition_payment_status(payment, "failed")
        payment.save(update_fields=["status", "updated_at"])

        logger.warning(
            "Payment failed",
            extra={"org_id": str(payment.organization_id), "order_id": order_id},
        )

    @staticmethod
    @transaction.atomic
    def handle_refund(event_type, data):
        from apps.billing.models import LedgerEntry, Payment, ProcessedWebhookEvent
        from apps.core.models import AuditLog

        refund_data = data.get("data", {}).get("refund", {})
        order_data = data.get("data", {}).get("order", {})
        refund_id = str(refund_data.get("refund_id", ""))
        order_id = order_data.get("order_id", "")

        if not refund_id or not order_id:
            return

        try:
            _evt, _created = ProcessedWebhookEvent.objects.get_or_create(
                provider="cashfree",
                event_id=refund_id,
                defaults={"event_type": event_type, "payload": data},
            )
        except IntegrityError:
            logger.info("Refund already processed (race)", extra={"refund_id": refund_id})
            return
        if not _created:
            logger.info("Refund already processed", extra={"refund_id": refund_id})
            return

        try:
            payment = Payment.objects.select_for_update().get(cashfree_order_id=order_id)
        except Payment.DoesNotExist:
            logger.error("Payment not found for refund", extra={"order_id": order_id})
            return

        if event_type == "REFUND_SUCCESS_WEBHOOK":
            try:
                refund_amount = Decimal(str(refund_data.get("refund_amount", "0")))
            except (InvalidOperation, ValueError):
                return

            refund_amount = min(refund_amount, _MAX_WEBHOOK_AMOUNT)

            if refund_amount + payment.total_refunded > payment.amount:
                logger.error(
                    "Cumulative refund exceeds payment",
                    extra={
                        "refund_amount": str(refund_amount),
                        "total_refunded": str(payment.total_refunded),
                        "payment_amount": str(payment.amount),
                    },
                )
                return

            payment.total_refunded = F("total_refunded") + refund_amount
            payment.save(update_fields=["total_refunded", "updated_at"])
            payment.refresh_from_db()

            org = payment.organization
            LedgerEntry.objects.create(
                organization=org,
                entry_type="refund",
                amount=refund_amount,
                currency=payment.currency,
                reference_type="Refund",
                reference_id=refund_id,
                description=f"Refund via Cashfree. Refund ID: {refund_id}",
            )

            try:
                AuditLog.objects.create(
                    organization=org,
                    action="REFUND_PROCESSED",
                    resource_type="Payment",
                    resource_id=str(payment.pk),
                    changes={
                        "refund_id": refund_id,
                        "order_id": order_id,
                        "amount": str(refund_amount),
                    },
                )
            except Exception as audit_exc:
                logger.warning(
                    "AuditLog failed for REFUND_PROCESSED: %s",
                    audit_exc,
                    extra={"refund_id": refund_id},
                )

            logger.info(
                "Refund processed",
                extra={
                    "org_id": str(org.pk),
                    "refund_id": refund_id,
                    "amount": str(refund_amount),
                },
            )

        elif event_type == "REFUND_FAILED_WEBHOOK":
            logger.warning("Refund failed", extra={"refund_id": refund_id, "order_id": order_id})


class RefundService:

    @staticmethod
    @transaction.atomic
    def initiate_refund(organization, payment_id, amount, reason, admin_user):
        from apps.billing.models import Payment
        from apps.core.models import AuditLog

        try:
            payment = Payment.objects.select_for_update().get(
                pk=payment_id,
                organization=organization,
                status="completed",
            )
        except Payment.DoesNotExist:
            raise NotFound("Completed payment not found.")

        refund_amount = Decimal(str(amount))
        if refund_amount <= 0 or refund_amount > (payment.amount - payment.total_refunded):
            raise ValidationError(
                {
                    "detail": f"Refund amount must be between 0.01 and {payment.amount - payment.total_refunded}."
                }
            )

        refund_id = f"REF-{uuid.uuid4().hex[:12].upper()}"

        CashfreeService.initiate_refund(
            order_id=payment.cashfree_order_id,
            refund_amount=refund_amount,
            refund_id=refund_id,
            reason=reason,
        )

        try:
            AuditLog.objects.create(
                organization=organization,
                actor=admin_user,
                action="REFUND_INITIATED",
                resource_type="Payment",
                resource_id=str(payment.pk),
                changes={
                    "refund_id": refund_id,
                    "amount": str(refund_amount),
                    "reason": reason,
                },
            )
        except Exception as audit_exc:
            logger.warning(
                "AuditLog failed for REFUND_INITIATED: %s",
                audit_exc,
                extra={"payment_id": str(payment.pk)},
            )

        logger.info(
            "Refund initiated by admin",
            extra={
                "org_id": str(organization.pk),
                "payment_id": str(payment.pk),
                "refund_id": refund_id,
                "admin_id": str(admin_user.pk),
                "amount": str(refund_amount),
            },
        )

        return {
            "refund_id": refund_id,
            "status": "pending",
            "amount": str(refund_amount),
        }
