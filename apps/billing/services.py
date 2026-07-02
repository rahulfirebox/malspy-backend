import logging
from decimal import Decimal

from django.conf import settings
from django.db import OperationalError, ProgrammingError, transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from apps.core.exceptions import QuotaExceededException, ResourceNotFound
from apps.core.models import AuditLog

from .models import Invoice, LedgerEntry, Payment, Plan, Subscription

logger = logging.getLogger(__name__)

VALID_TRANSITIONS = {
    "pending": ["active", "trialing"],
    "trialing": ["active", "past_due", "cancelled"],
    "active": ["past_due", "cancelled", "unpaid"],
    "past_due": ["active", "cancelled", "unpaid"],
    "unpaid": ["cancelled"],
    "cancelled": [],
}
TERMINAL_STATES = {"cancelled"}

STRIPE_STATUS_MAP = {
    "active": "active",
    "trialing": "trialing",
    "past_due": "past_due",
    "canceled": "cancelled",
    "unpaid": "unpaid",
}


def _transition_subscription_status(sub, new_status, context=""):
    allowed = VALID_TRANSITIONS.get(sub.status, [])
    if new_status not in allowed:
        logger.warning(
            "Illegal subscription status transition %s -> %s rejected%s",
            sub.status,
            new_status,
            f" ({context})" if context else "",
            extra={"subscription_id": str(sub.id)},
        )
        raise ValidationError(
            {"detail": (f"Cannot transition subscription from '{sub.status}' to '{new_status}'.")}
        )
    sub.status = new_status


def list_active_plans(country: str = ""):
    from .models import PlanPrice

    try:
        plans = list(Plan.objects.filter(is_active=True).order_by("price_monthly"))
        price_map = {}
        if country:
            price_map = {
                str(pp.plan_id): pp
                for pp in PlanPrice.objects.filter(
                    country_code=country, is_active=True, plan__is_active=True
                ).select_related("plan")
            }
        return plans, price_map
    except (OperationalError, ProgrammingError) as e:
        logger.error(
            "BillingService.list_active_plans DB error: %s",
            e,
            extra={"country": country},
        )
        raise
    except ValidationError:
        raise
    except Exception as e:
        logger.error(
            "BillingService.list_active_plans unexpected error: %s",
            e,
            exc_info=True,
            extra={"country": country},
        )
        raise


def get_active_plan(plan_slug: str):
    try:
        return Plan.objects.get(slug=plan_slug, is_active=True)
    except Plan.DoesNotExist:
        return None
    except (OperationalError, ProgrammingError) as e:
        logger.error(
            "BillingService.get_active_plan DB error: %s",
            e,
            extra={"plan_slug": plan_slug},
        )
        raise


def get_payment_by_order(order_id: str, org):
    if org is None:
        raise ValidationError({"detail": "Organization context required."})
    try:
        return Payment.objects.get(cashfree_order_id=order_id, organization=org)
    except Payment.DoesNotExist:
        return None
    except (OperationalError, ProgrammingError) as e:
        logger.error(
            "BillingService.get_payment_by_order DB error: %s",
            e,
            extra={"order_id": order_id, "org_id": str(org.id)},
        )
        raise


def get_current_plan(org):
    if org is None:
        raise ValidationError({"detail": "Organization context required."})
    try:
        plan = org.plan
        sub = (
            Subscription.objects.filter(organization=org, status__in=["active", "trialing"])
            .select_related("plan")
            .first()
        )
        return plan, sub
    except (OperationalError, ProgrammingError) as e:
        logger.error(
            "BillingService.get_current_plan DB error: %s",
            e,
            extra={"org_id": str(org.id) if org else None},
        )
        return None, None
    except ValidationError:
        raise
    except Exception as e:
        logger.error(
            "BillingService.get_current_plan unexpected error: %s",
            e,
            exc_info=True,
            extra={"org_id": str(org.id) if org else None},
        )
        raise


def list_invoices(org):
    if org is None:
        raise ValidationError({"detail": "Organization context required."})
    try:
        return (
            Invoice.objects.filter(organization=org)
            .select_related("organization")
            .order_by("-created_at")
        )
    except (OperationalError, ProgrammingError) as e:
        logger.error(
            "BillingService.list_invoices DB error: %s",
            e,
            extra={"org_id": str(org.id) if org else None},
        )
        raise
    except ValidationError:
        raise
    except Exception as e:
        logger.error(
            "BillingService.list_invoices unexpected error: %s",
            e,
            exc_info=True,
            extra={"org_id": str(org.id) if org else None},
        )
        raise


def get_domain_quota_used(org):
    try:
        from apps.domains.models import Domain

        return Domain.objects.filter(
            organization=org, deleted_at__isnull=True, is_active=True
        ).count()
    except (OperationalError, ProgrammingError):
        raise
    except ValidationError:
        raise
    except Exception as e:
        logger.error(
            "Failed to get domain quota used",
            extra={"org_id": str(org.id), "error": str(e)},
        )
        raise


def upgrade_plan(org, user, plan_slug: str, billing_period: str = "monthly"):
    if org is None:
        raise ValidationError({"detail": "Organization context required."})
    try:
        new_plan = Plan.objects.get(slug=plan_slug, is_active=True)
    except Plan.DoesNotExist:
        raise ResourceNotFound("Plan not found.")
    except (OperationalError, ProgrammingError) as e:
        logger.error("BillingService.upgrade_plan DB error: %s", e, extra={"org_id": str(org.id)})
        raise ValidationError({"detail": "Service unavailable."})

    with transaction.atomic():
        org_locked = type(org).objects.select_for_update().get(pk=org.pk)
        org_locked.refresh_from_db()

        if Subscription.objects.filter(
            organization=org_locked, plan=new_plan, status__in=["active", "trialing"]
        ).exists():
            return new_plan

        old_plan = org_locked.plan
        is_downgrade = old_plan is not None and old_plan.price_monthly > new_plan.price_monthly
        if is_downgrade:
            from apps.agents.models import ServerAgent
            from apps.domains.models import Domain

            if new_plan.domain_quota != -1:
                current_domains = Domain.objects.filter(
                    organization=org_locked,
                    deleted_at__isnull=True,
                ).count()
                if current_domains > new_plan.domain_quota:
                    raise QuotaExceededException(
                        f"Cannot downgrade: you have {current_domains} monitored domains "
                        f"but the {new_plan.name} plan allows only "
                        f"{new_plan.domain_quota}. Remove excess domains first."
                    )

            if new_plan.agent_quota != -1:
                current_agents = ServerAgent.objects.filter(
                    organization=org_locked,
                    deleted_at__isnull=True,
                ).count()
                if current_agents > new_plan.agent_quota:
                    raise QuotaExceededException(
                        f"Cannot downgrade: you have {current_agents} server agents "
                        f"but the {new_plan.name} plan allows only "
                        f"{new_plan.agent_quota}. Remove excess agents first."
                    )

        old_plan_slug = org_locked.plan.slug if org_locked.plan else None
        org_locked.plan = new_plan
        org_locked.save(update_fields=["plan", "updated_at"])

        Subscription.objects.filter(
            organization=org_locked, status__in=["active", "trialing"]
        ).update(status="cancelled", cancelled_at=timezone.now(), updated_at=timezone.now())

        initial_status = "active" if new_plan.price_monthly == Decimal("0.00") else "pending"
        Subscription.objects.create(
            organization=org_locked,
            plan=new_plan,
            status=initial_status,
        )

        if billing_period == "yearly":
            ledger_amount = new_plan.price_yearly
        else:
            ledger_amount = new_plan.price_monthly

        LedgerEntry.objects.create(
            organization=org_locked,
            entry_type="subscription_activation",
            amount=ledger_amount,
            description=f"Plan upgraded to {plan_slug} ({billing_period})",
        )

        try:
            AuditLog.objects.create(
                organization=org_locked,
                actor=user,
                action="PLAN_UPGRADED",
                resource_type="Organization",
                resource_id=str(org_locked.id),
                changes={
                    "old_plan": old_plan_slug,
                    "new_plan": plan_slug,
                    "billing_period": billing_period,
                },
            )
        except ValidationError:
            raise
        except Exception as audit_exc:
            logger.warning(
                "AuditLog failed for upgrade_plan: %s",
                audit_exc,
                extra={"org_id": str(org_locked.id)},
            )

    return new_plan


def handle_stripe_event(event: dict) -> None:
    event_type = event.get("type", "")
    data_obj = event.get("data", {}).get("object", {})
    try:
        if event_type == "invoice.paid":
            with transaction.atomic():
                invoice = data_obj
                sid = invoice.get("id")
                stripe_sub_id = invoice.get("subscription")
                if sid:
                    rows_updated = Invoice.objects.filter(stripe_invoice_id=sid).update(
                        status="paid",
                        paid_at=timezone.now(),
                        invoice_pdf_url=invoice.get("invoice_pdf") or "",
                        updated_at=timezone.now(),
                    )
                    if rows_updated == 0:
                        logger.warning(
                            "invoice.paid: no Invoice row matched stripe_invoice_id=%s",
                            sid,
                            extra={
                                "stripe_event_id": event.get("id", ""),
                                "stripe_invoice_id": sid,
                            },
                        )
                    try:
                        org_for_invoice = None
                        if stripe_sub_id:
                            sub_ref = (
                                Subscription.objects.select_related("organization")
                                .filter(stripe_subscription_id=stripe_sub_id)
                                .first()
                            )
                            if sub_ref:
                                org_for_invoice = sub_ref.organization
                        AuditLog.objects.create(
                            organization=org_for_invoice,
                            actor=None,
                            action="INVOICE_PAID",
                            resource_type="Invoice",
                            resource_id=sid or "",
                            changes={
                                "status": "paid",
                                "stripe_event_id": event.get("id", ""),
                            },
                        )
                    except ValidationError:
                        raise
                    except Exception as audit_exc:
                        logger.warning(
                            "AuditLog failed for invoice.paid: %s",
                            audit_exc,
                            extra={
                                "stripe_event_id": event.get("id", ""),
                                "stripe_invoice_id": sid,
                            },
                        )
                if stripe_sub_id:
                    sub = (
                        Subscription.objects.select_for_update()
                        .select_related("plan", "organization")
                        .filter(stripe_subscription_id=stripe_sub_id)
                        .first()
                    )
                    if sub:
                        plan = sub.plan
                        org = sub.organization
                        org.plan = plan
                        org.save(update_fields=["plan", "updated_at"])
                        _transition_subscription_status(sub, "active", "invoice.paid")
                        sub.save(update_fields=["status", "updated_at"])
                        org.stripe_subscription_id = stripe_sub_id
                        org.save(update_fields=["stripe_subscription_id", "updated_at"])
                        amount = min(
                            Decimal(str(invoice.get("amount_paid", 0))) / 100,
                            Decimal("99999.99"),
                        )
                        LedgerEntry.objects.create(
                            organization=org,
                            entry_type="subscription_activation",
                            amount=amount,
                            currency=(invoice.get("currency") or "usd").upper(),
                            reference_type="Invoice",
                            reference_id=sid or "",
                            stripe_event_id=event.get("id", ""),
                            description=f"Plan activated: {plan.slug}",
                        )
                        try:
                            AuditLog.objects.create(
                                organization=org,
                                actor=None,
                                action="PLAN_ACTIVATED",
                                resource_type="Subscription",
                                resource_id=str(sub.id),
                                changes={
                                    "plan": plan.slug,
                                    "event": "invoice.paid",
                                    "stripe_event_id": event.get("id", ""),
                                },
                            )
                        except ValidationError:
                            raise
                        except Exception as audit_exc:
                            logger.warning(
                                "AuditLog failed for PLAN_ACTIVATED: %s",
                                audit_exc,
                                extra={"stripe_event_id": event.get("id", "")},
                            )
        elif event_type == "invoice.payment_failed":
            with transaction.atomic():
                invoice = data_obj
                sid = invoice.get("id")
                stripe_sub_id = invoice.get("subscription")
                if stripe_sub_id:
                    sub = (
                        Subscription.objects.select_for_update()
                        .select_related("organization", "plan")
                        .filter(stripe_subscription_id=stripe_sub_id)
                        .first()
                    )
                    if sub:
                        org = sub.organization
                        try:
                            _transition_subscription_status(
                                sub, "past_due", "invoice.payment_failed"
                            )
                        except ValidationError:
                            logger.warning(
                                "invoice.payment_failed: cannot transition %s -> past_due for sub %s",
                                sub.status,
                                sub.id,
                                extra={"stripe_event_id": event.get("id", "")},
                            )
                        else:
                            sub.save(update_fields=["status", "updated_at"])
                            LedgerEntry.objects.create(
                                organization=org,
                                entry_type="payment",
                                amount=Decimal("0.00"),
                                currency=(invoice.get("currency") or "usd").upper(),
                                reference_type="Invoice",
                                reference_id=sid or "",
                                stripe_event_id=event.get("id", ""),
                                description="Payment failed",
                            )
                            try:
                                AuditLog.objects.create(
                                    organization=org,
                                    actor=None,
                                    action="PAYMENT_FAILED",
                                    resource_type="Subscription",
                                    resource_id=str(sub.id),
                                    changes={
                                        "event": "invoice.payment_failed",
                                        "stripe_event_id": event.get("id", ""),
                                        "stripe_invoice_id": sid or "",
                                    },
                                )
                            except ValidationError:
                                raise
                            except Exception as audit_exc:
                                logger.warning(
                                    "AuditLog failed for invoice.payment_failed: %s",
                                    audit_exc,
                                    extra={"stripe_event_id": event.get("id", "")},
                                )
        elif event_type == "customer.subscription.created":
            with transaction.atomic():
                stripe_sub = data_obj
                stripe_sub_id = stripe_sub.get("id")
                stripe_customer_id = stripe_sub.get("customer")
                stripe_status = stripe_sub.get("status")
                new_status = STRIPE_STATUS_MAP.get(stripe_status)
                if stripe_sub_id and stripe_customer_id and new_status:
                    sub = (
                        Subscription.objects.select_for_update()
                        .select_related("organization")
                        .filter(organization__stripe_customer_id=stripe_customer_id)
                        .order_by("-created_at")
                        .first()
                    )
                    if (
                        sub
                        and sub.status in VALID_TRANSITIONS
                        and new_status in VALID_TRANSITIONS.get(sub.status, [])
                    ):
                        sub.stripe_subscription_id = stripe_sub_id
                        sub.status = new_status
                        sub.save(update_fields=["stripe_subscription_id", "status", "updated_at"])
                        org = sub.organization
                        org.stripe_subscription_id = stripe_sub_id
                        org.save(update_fields=["stripe_subscription_id", "updated_at"])
                        try:
                            AuditLog.objects.create(
                                organization=org,
                                actor=None,
                                action="SUBSCRIPTION_CREATED",
                                resource_type="Subscription",
                                resource_id=str(sub.id),
                                changes={
                                    "event": "customer.subscription.created",
                                    "stripe_event_id": event.get("id", ""),
                                    "stripe_subscription_id": stripe_sub_id,
                                    "status": new_status,
                                },
                            )
                        except ValidationError:
                            raise
                        except Exception as audit_exc:
                            logger.warning(
                                "AuditLog failed for customer.subscription.created: %s",
                                audit_exc,
                                extra={"stripe_event_id": event.get("id", "")},
                            )
        elif event_type == "customer.subscription.updated":
            with transaction.atomic():
                stripe_sub = data_obj
                stripe_sub_id = stripe_sub.get("id")
                stripe_status = stripe_sub.get("status")
                new_status = STRIPE_STATUS_MAP.get(stripe_status)
                if stripe_sub_id and new_status:
                    sub = (
                        Subscription.objects.select_for_update()
                        .select_related("organization")
                        .filter(stripe_subscription_id=stripe_sub_id)
                        .first()
                    )
                    if sub:
                        if new_status in VALID_TRANSITIONS.get(sub.status, []):
                            sub.status = new_status
                            sub.save(update_fields=["status", "updated_at"])
                            org = sub.organization
                            org.stripe_subscription_id = stripe_sub_id
                            org.save(update_fields=["stripe_subscription_id", "updated_at"])
                        else:
                            logger.warning(
                                "customer.subscription.updated: illegal transition %s -> %s for sub %s",
                                sub.status,
                                new_status,
                                sub.id,
                                extra={"stripe_event_id": event.get("id", "")},
                            )
        elif event_type == "customer.subscription.deleted":
            with transaction.atomic():
                ssid = data_obj.get("id")
                if ssid:
                    try:
                        free_plan = Plan.objects.get(slug="free", is_active=True)
                        sub = (
                            Subscription.objects.select_for_update()
                            .select_related("organization")
                            .filter(stripe_subscription_id=ssid)
                            .first()
                        )
                        if sub:
                            org = sub.organization
                            org.plan = free_plan
                            org.save(update_fields=["plan", "updated_at"])
                            _transition_subscription_status(
                                sub, "cancelled", "customer.subscription.deleted"
                            )
                            sub.cancelled_at = timezone.now()
                            sub.save(update_fields=["status", "cancelled_at", "updated_at"])
                            try:
                                AuditLog.objects.create(
                                    organization=org,
                                    actor=None,
                                    action="PLAN_CANCELLED",
                                    resource_type="Subscription",
                                    resource_id=str(sub.id),
                                    changes={
                                        "event": "customer.subscription.deleted",
                                        "stripe_event_id": event.get("id", ""),
                                        "reverted_to": "free",
                                    },
                                )
                            except ValidationError:
                                raise
                            except Exception as audit_exc:
                                logger.warning(
                                    "AuditLog failed for customer.subscription.deleted: %s",
                                    audit_exc,
                                    extra={"stripe_event_id": event.get("id", "")},
                                )
                    except Plan.DoesNotExist:
                        logger.error(
                            "handle_stripe_event: free plan not found",
                            extra={"stripe_event_id": event.get("id", "")},
                        )
        elif event_type == "checkout.session.completed":
            with transaction.atomic():
                stripe_sub_id = data_obj.get("subscription")
                stripe_customer_id = data_obj.get("customer")
                if stripe_customer_id and stripe_sub_id:
                    sub = (
                        Subscription.objects.select_for_update()
                        .filter(organization__stripe_customer_id=stripe_customer_id)
                        .first()
                    )
                    if sub:
                        sub.stripe_subscription_id = stripe_sub_id
                        _transition_subscription_status(sub, "active", "checkout.session.completed")
                        sub.save(
                            update_fields=[
                                "stripe_subscription_id",
                                "status",
                                "updated_at",
                            ]
                        )
                        org = sub.organization
                        org.stripe_subscription_id = stripe_sub_id
                        org.save(update_fields=["stripe_subscription_id", "updated_at"])
                        LedgerEntry.objects.create(
                            organization=org,
                            entry_type="checkout_completed",
                            amount=Decimal("0.00"),
                            stripe_event_id=event.get("id", ""),
                            description="Checkout session completed",
                        )
                        try:
                            AuditLog.objects.create(
                                organization=org,
                                actor=None,
                                action="CHECKOUT_COMPLETED",
                                resource_type="Subscription",
                                resource_id=str(sub.id),
                                changes={
                                    "event": "checkout.session.completed",
                                    "stripe_event_id": event.get("id", ""),
                                    "stripe_subscription_id": stripe_sub_id,
                                },
                            )
                        except ValidationError:
                            raise
                        except Exception as audit_exc:
                            logger.warning(
                                "AuditLog failed for checkout.session.completed: %s",
                                audit_exc,
                                extra={"stripe_event_id": event.get("id", "")},
                            )
    except ValidationError:
        raise
    except Exception as exc:
        logger.error(
            "handle_stripe_event failed type=%s: %s",
            event_type,
            exc,
            exc_info=True,
            extra={"stripe_event_id": event.get("id", ""), "event_type": event_type},
        )
        raise


def cancel_subscription(org, user):
    if org is None:
        raise ValidationError({"detail": "Organization context required."})
    try:
        Plan.objects.get(slug="free", is_active=True)
    except Plan.DoesNotExist:
        raise NotFound("Free plan not configured.")
    except (OperationalError, ProgrammingError) as e:
        logger.error(
            "BillingService.cancel_subscription DB error: %s",
            e,
            extra={"org_id": str(org.id)},
        )
        raise ValidationError({"detail": "Service unavailable."})

    with transaction.atomic():
        subscription = (
            Subscription.objects.select_for_update()
            .filter(organization=org, status__in=["active", "trialing"])
            .order_by("-created_at")
            .first()
        )
        if not subscription:
            raise ValidationError({"detail": "No active subscription to cancel."})

        if subscription.status == "cancelled":
            return {
                "status": "cancelled",
                "plan": org.plan.slug if org.plan else "free",
            }

        stripe_sub_id = subscription.stripe_subscription_id

    if stripe_sub_id:
        gateway = getattr(settings, "PAYMENT_GATEWAY", "cashfree")
        if gateway in ("stripe", "dual"):
            try:
                import stripe

                stripe.Subscription.cancel(stripe_sub_id)
            except ValidationError:
                raise
            except Exception as e:
                logger.error(
                    "Stripe cancel failed: %s",
                    e,
                    extra={"org_id": str(org.id), "stripe_sub_id": stripe_sub_id},
                )
                raise ValidationError(
                    {"detail": "Failed to cancel subscription with payment provider."}
                )

    with transaction.atomic():

        subscription = (
            Subscription.objects.select_for_update()
            .filter(organization=org, status__in=["active", "trialing"])
            .order_by("-created_at")
            .first()
        )
        if not subscription:

            return {
                "status": "cancelled",
                "plan": org.plan.slug if org.plan else "free",
            }

        _transition_subscription_status(subscription, "cancelled", "cancel_subscription")
        subscription.cancelled_at = timezone.now()
        subscription.save(update_fields=["status", "cancelled_at", "updated_at"])

        org_locked = type(org).objects.select_for_update().get(pk=org.pk)

        LedgerEntry.objects.create(
            organization=org_locked,
            entry_type="subscription_cancellation",
            amount=Decimal("0.00"),
            description="Subscription cancelled",
        )

        try:
            AuditLog.objects.create(
                organization=org_locked,
                actor=user,
                action="CANCEL_SUBSCRIPTION",
                resource_type="Subscription",
                resource_id=str(subscription.id),
            )
        except ValidationError:
            raise
        except Exception as audit_exc:
            logger.warning(
                "AuditLog failed for cancel_subscription: %s",
                audit_exc,
                extra={"org_id": str(org_locked.id)},
            )

    return {"status": "cancelled", "plan": org.plan.slug if org.plan else "free"}


def expire_trial(org):
    if org is None:
        return

    with transaction.atomic():
        sub = (
            Subscription.objects.select_for_update()
            .filter(organization=org, status="trialing")
            .select_related("plan")
            .first()
        )
        if not sub:
            return

        trial_end = None
        if sub.current_period_end:
            trial_end = sub.current_period_end
        else:

            trial_end = sub.created_at + timezone.timedelta(days=14)

        if timezone.now() < trial_end:
            return

        _transition_subscription_status(sub, "past_due", "expire_trial")
        sub.save(update_fields=["status", "updated_at"])

        LedgerEntry.objects.create(
            organization=org,
            entry_type="subscription_activation",
            amount=Decimal("0.00"),
            description="Trial expired — subscription moved to past_due",
        )

        try:
            AuditLog.objects.create(
                organization=org,
                actor=None,
                action="TRIAL_EXPIRED",
                resource_type="Subscription",
                resource_id=str(sub.id),
                changes={"trial_end": trial_end.isoformat()},
            )
        except ValidationError:
            raise
        except Exception as audit_exc:
            logger.warning(
                "AuditLog failed for expire_trial: %s",
                audit_exc,
                extra={"org_id": str(org.id)},
            )
