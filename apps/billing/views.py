import logging
import time

from django.conf import settings
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from apps.core.pagination import StandardCursorPagination
from apps.core.permissions import IsAdmin, RequiresOrg
from apps.core.throttling import SensitiveActionThrottle

from . import services
from .cashfree_service import CashfreeService, WebhookProcessor
from .models import ProcessedWebhookEvent
from .serializers import (
    CreateOrderSerializer,
    InvoiceSerializer,
    PlanSerializer,
    UpgradePlanSerializer,
    VerifyPaymentSerializer,
)

logger = logging.getLogger(__name__)

_BILLING_CACHE_TTL = 86400
_GW_CASHFREE = "cashfree"


def _cashfree_redirect_data(gateway: str, plan_slug: str, plan) -> dict | None:

    if gateway == _GW_CASHFREE and plan.price_monthly > 0:
        return {
            "gateway": "cashfree",
            "message": "Use /billing/create-order/ for Cashfree payment",
            "plan_slug": plan_slug,
        }
    return None


class PlansListView(GenericAPIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = PlanSerializer
    pagination_class = StandardCursorPagination
    throttle_classes = [SensitiveActionThrottle]

    def get(self, request):
        country = request.query_params.get("country", "").upper().strip()
        plans, price_map = services.list_active_plans(country=country)
        serializer = PlanSerializer(plans, many=True)
        data = serializer.data

        if country and price_map:
            for plan_dict in data:
                pp = price_map.get(plan_dict["id"])
                if pp:
                    plan_dict["localized_price"] = str(pp.amount)
                    plan_dict["localized_currency"] = pp.currency
                else:
                    plan_dict["localized_price"] = None
                    plan_dict["localized_currency"] = None

        return Response(data)


class BillingPlanView(GenericAPIView):
    permission_classes = [IsAuthenticated, RequiresOrg, IsAdmin]
    serializer_class = PlanSerializer
    throttle_classes = [SensitiveActionThrottle]

    def get(self, request):
        org = request.user.organization
        plan, sub = services.get_current_plan(org)

        domain_quota_used = services.get_domain_quota_used(org)

        data = {
            "plan": plan.slug if plan else "free",
            "plan_name": plan.name if plan else "Free",
            "price_monthly": str(plan.price_monthly) if plan else "0.00",
            "scan_quota_used": org.scan_quota_used,
            "scan_quota_limit": plan.scan_quota if plan else 0,
            "domain_quota_used": domain_quota_used,
            "domain_quota_limit": plan.domain_quota if plan else 0,
            "subscription_status": sub.status if sub else None,
            "stripe_subscription_id": sub.stripe_subscription_id if sub else None,
            "quota_reset_at": (org.quota_reset_at.isoformat() if org.quota_reset_at else None),
        }
        return Response(data)


class InvoiceListView(GenericAPIView):
    permission_classes = [IsAuthenticated, RequiresOrg, IsAdmin]
    serializer_class = InvoiceSerializer
    pagination_class = StandardCursorPagination

    def get(self, request):
        org = request.user.organization
        qs = services.list_invoices(org)
        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = InvoiceSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = InvoiceSerializer(qs, many=True)
        return Response({"results": serializer.data, "count": qs.count()})


class UpgradePlanView(GenericAPIView):
    permission_classes = [IsAuthenticated, RequiresOrg, IsAdmin]
    throttle_classes = [SensitiveActionThrottle]
    serializer_class = UpgradePlanSerializer

    def post(self, request):
        idempotency_key = request.headers.get("Idempotency-Key")
        if not idempotency_key:
            return Response(
                {"detail": "Idempotency-Key header is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cache_key = f"billing:upgrade:{idempotency_key}"
        cached = cache.get(cache_key)
        if cached:
            return Response(cached, status=status.HTTP_200_OK)

        ser = UpgradePlanSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        org = request.user.organization
        billing_period = ser.validated_data.get("billing_period", "monthly")

        gateway = getattr(settings, "PAYMENT_GATEWAY", "cashfree")
        plan_slug = ser.validated_data["plan_slug"]
        plan = services.get_active_plan(plan_slug)
        if plan is None:
            return Response({"detail": "Plan not found."}, status=status.HTTP_404_NOT_FOUND)

        redirect = _cashfree_redirect_data(gateway, plan_slug, plan)
        if redirect:
            return Response(redirect)

        new_plan = services.upgrade_plan(
            org=org,
            user=request.user,
            plan_slug=plan_slug,
            billing_period=billing_period,
        )
        cache.delete(f"org:{org.id}:plan")
        cache.delete(f"org:{org.id}:quota")
        response_data = PlanSerializer(new_plan).data
        cache.set(cache_key, response_data, timeout=_BILLING_CACHE_TTL)
        return Response(response_data, status=status.HTTP_200_OK)


class CancelSubscriptionView(GenericAPIView):
    permission_classes = [IsAuthenticated, RequiresOrg, IsAdmin]
    throttle_classes = [SensitiveActionThrottle]

    def post(self, request):
        idempotency_key = request.headers.get("Idempotency-Key")

        if idempotency_key:
            cache_key = f"billing:cancel:{idempotency_key}"
            cached = cache.get(cache_key)
            if cached:
                return Response(cached, status=status.HTTP_200_OK)

        org = request.user.organization
        result = services.cancel_subscription(org=org, user=request.user)
        cache.delete(f"org:{org.id}:plan")
        cache.delete(f"org:{org.id}:quota")
        response_data = result

        if idempotency_key:
            cache_key = f"billing:cancel:{idempotency_key}"
            cache.set(cache_key, response_data, timeout=_BILLING_CACHE_TTL)

        return Response(response_data, status=status.HTTP_200_OK)


@method_decorator(csrf_exempt, name="dispatch")
class StripeWebhookView(GenericAPIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [SensitiveActionThrottle]

    def post(self, request):
        idempotency_key = request.headers.get("Idempotency-Key")
        if not idempotency_key:
            return Response(
                {"detail": "Idempotency-Key header required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        import stripe

        webhook_secret = getattr(settings, "STRIPE_WEBHOOK_SECRET", None)
        if not webhook_secret:
            logger.error("STRIPE_WEBHOOK_SECRET not configured", extra={})
            return Response(
                {"error_code": "WEBHOOK_CONFIG_ERROR", "message": "Webhook secret not configured."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        sig_header = request.META.get("HTTP_STRIPE_SIGNATURE", "")
        payload = request.body

        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, webhook_secret, tolerance=300
            )
        except stripe.error.SignatureVerificationError:
            logger.warning("Stripe webhook signature verification failed", extra={})
            return Response(
                {"error_code": "INVALID_SIGNATURE", "message": "Invalid signature."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as exc:
            logger.error("Stripe webhook parse error: %s", exc, extra={})
            return Response(
                {"error_code": "INVALID_PAYLOAD", "message": "Invalid payload."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        event_id = event.get("id", "")
        try:
            with transaction.atomic():
                services.handle_stripe_event(event)
                ProcessedWebhookEvent.objects.create(
                    provider="stripe",
                    event_id=event_id,
                    event_type=event.get("type", ""),
                )
        except IntegrityError:
            return Response({"status": "already_processed"})

        return Response({"received": True})


class CreateOrderView(GenericAPIView):

    permission_classes = [IsAuthenticated, RequiresOrg, IsAdmin]
    throttle_classes = [SensitiveActionThrottle]
    serializer_class = CreateOrderSerializer

    def post(self, request):
        idempotency_key = request.headers.get("Idempotency-Key", "")
        if not idempotency_key:
            return Response(
                {"detail": "Idempotency-Key header is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cache_key = f"billing:create_order:{idempotency_key}"
        cached = cache.get(cache_key)
        if cached:
            return Response(cached, status=status.HTTP_201_CREATED)

        ser = CreateOrderSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        org = request.user.organization
        plan_slug = ser.validated_data["plan_slug"]

        plan = services.get_active_plan(plan_slug)
        if plan is None:
            return Response(
                {"detail": "Plan not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if plan.price_monthly <= 0:
            return Response(
                {"detail": "Cannot create payment order for free plan."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        payment = CashfreeService.create_order(
            organization=org,
            amount=plan.price_monthly,
            plan_id=plan_slug,
            idempotency_key=idempotency_key,
        )

        response_data = {
            "order_id": payment.cashfree_order_id,
            "payment_session_id": payment.cashfree_session_id,
            "amount": str(payment.amount),
            "currency": payment.currency,
            "plan_slug": plan_slug,
            "plan_name": plan.name,
        }
        cache.set(cache_key, response_data, timeout=300)
        return Response(response_data, status=status.HTTP_201_CREATED)


class VerifyPaymentView(GenericAPIView):

    permission_classes = [IsAuthenticated, RequiresOrg, IsAdmin]
    throttle_classes = [SensitiveActionThrottle]
    serializer_class = VerifyPaymentSerializer

    def post(self, request):
        idempotency_key = request.headers.get("Idempotency-Key")
        if not idempotency_key:
            return Response(
                {"detail": "Idempotency-Key header required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        ser = VerifyPaymentSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        order_id = ser.validated_data["order_id"]

        payment = services.get_payment_by_order(
            order_id=order_id,
            org=request.user.organization,
        )
        if payment is None:
            return Response(
                {"detail": "Payment not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if payment.status == "completed":
            return Response({"status": "completed"})

        order_status = CashfreeService.get_order_status(order_id)
        if order_status and order_status.get("order_status") == "PAID":
            return Response({"status": "completed"})

        return Response({"status": payment.status})


@method_decorator(csrf_exempt, name="dispatch")
class CashfreeWebhookView(GenericAPIView):

    permission_classes = []
    authentication_classes = []

    def post(self, request):
        idempotency_key = request.headers.get("Idempotency-Key")
        if not idempotency_key:
            return Response(
                {"detail": "Idempotency-Key header required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        signature = request.headers.get("x-webhook-signature", "")
        timestamp = request.headers.get("x-webhook-timestamp", "")
        raw_body = request.body.decode("utf-8", errors="replace")

        if not signature or not timestamp:
            logger.warning("Cashfree webhook missing headers", extra={})
            return Response({"received": False}, status=status.HTTP_400_BAD_REQUEST)

        try:
            ts = float(timestamp)
            if abs(time.time() - ts) > 300:
                logger.warning(
                    "Cashfree webhook timestamp outside ±300s window",
                    extra={"timestamp": timestamp},
                )
                return Response({"received": False}, status=status.HTTP_400_BAD_REQUEST)
        except (ValueError, TypeError):
            return Response({"received": False}, status=status.HTTP_400_BAD_REQUEST)

        secret = getattr(settings, "CASHFREE_SECRET_KEY", "")
        if not secret:
            logger.error("Cashfree webhook credential not configured — rejecting webhook", extra={})
            return Response({"received": False}, status=status.HTTP_400_BAD_REQUEST)

        if not CashfreeService.verify_webhook_signature(timestamp, raw_body, signature):
            logger.warning("Cashfree webhook signature mismatch", extra={})
            return Response({"received": False}, status=status.HTTP_400_BAD_REQUEST)

        data = request.data
        event_type = data.get("type", "")

        try:
            if event_type == "PAYMENT_SUCCESS_WEBHOOK":
                WebhookProcessor.handle_payment_success(data)
            elif event_type == "PAYMENT_FAILED_WEBHOOK":
                WebhookProcessor.handle_payment_failed(data)
            elif event_type in ("REFUND_SUCCESS_WEBHOOK", "REFUND_FAILED_WEBHOOK"):
                WebhookProcessor.handle_refund(event_type, data)
            else:
                logger.info("Unhandled Cashfree event type", extra={"event_type": event_type})
        except Exception:
            logger.exception("Cashfree webhook processing error", extra={"event_type": event_type})
            return Response({"received": False, "status": "processing_failed"})

        return Response({"received": True})
