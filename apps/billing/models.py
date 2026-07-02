import uuid
from decimal import Decimal

from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.core.models import BaseModel


class Plan(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=50, unique=True)
    price_monthly = models.DecimalField(max_digits=10, decimal_places=2)
    price_yearly = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    scan_quota = models.IntegerField(help_text="-1 = unlimited")
    domain_quota = models.IntegerField(help_text="-1 = unlimited")
    agent_quota = models.IntegerField(default=0, help_text="0=none, -1=unlimited")
    browser_scan_enabled = models.BooleanField(default=False)
    server_side_scan = models.BooleanField(default=False)
    pdf_report = models.BooleanField(default=False)
    api_access = models.BooleanField(default=False)
    scheduled_scans = models.BooleanField(default=False)
    slack_notifications = models.BooleanField(default=False)
    waf_enabled = models.BooleanField(default=False)
    db_scan_enabled = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "plans"
        ordering = ["price_monthly"]
        constraints = [
            models.CheckConstraint(
                check=Q(scan_quota__gte=-1) & Q(domain_quota__gte=-1) & Q(agent_quota__gte=-1),
                name="check_plan_quota_fields_valid",
            ),
        ]

    def __str__(self):
        return f"{self.name} (${self.price_monthly}/mo)"


class PlanPrice(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="prices")
    country_code = models.CharField(max_length=3, db_index=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="USD")
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "plan_prices"
        constraints = [
            models.UniqueConstraint(
                fields=["plan", "country_code"],
                name="unique_plan_price_per_country",
            ),
        ]
        ordering = ["amount"]


class Subscription(BaseModel):
    organization = models.ForeignKey(
        "accounts.Organization",
        on_delete=models.PROTECT,
        related_name="subscriptions",
    )
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="subscriptions")
    status = models.CharField(
        max_length=20,
        choices=[
            ("active", "Active"),
            ("cancelled", "Cancelled"),
            ("past_due", "Past Due"),
            ("trialing", "Trialing"),
            ("unpaid", "Unpaid"),
        ],
        default="active",
        db_index=True,
    )
    stripe_subscription_id = models.CharField(max_length=100, blank=True, default="")
    current_period_start = models.DateTimeField(null=True, blank=True)
    current_period_end = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    plan_expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "subscriptions"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization"],
                condition=Q(status__in=["active", "trialing"]) & Q(deleted_at__isnull=True),
                name="unique_active_subscription_per_org",
            ),
            models.CheckConstraint(
                check=Q(
                    status__in=[
                        "active",
                        "cancelled",
                        "past_due",
                        "trialing",
                        "unpaid",
                    ]
                ),
                name="subscription_status_valid",
            ),
        ]


class Invoice(BaseModel):
    organization = models.ForeignKey(
        "accounts.Organization",
        on_delete=models.PROTECT,
        related_name="invoices",
    )
    subscription = models.ForeignKey(
        Subscription,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="invoices",
    )
    stripe_invoice_id = models.CharField(max_length=100, null=True, blank=True, unique=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default="USD")
    status = models.CharField(
        max_length=20,
        choices=[("paid", "Paid"), ("unpaid", "Unpaid"), ("void", "Void")],
        default="unpaid",
        db_index=True,
    )
    period_start = models.DateTimeField(null=True, blank=True)
    period_end = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    invoice_pdf_url = models.CharField(max_length=500, blank=True, default="")

    class Meta:
        db_table = "invoices"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                check=Q(status__in=["paid", "unpaid", "void"]),
                name="invoice_status_valid",
            ),
        ]


class Payment(BaseModel):

    PAYMENT_STATUSES = [
        ("pending", "Pending"),
        ("completed", "Completed"),
        ("failed", "Failed"),
        ("refunded", "Refunded"),
    ]

    organization = models.ForeignKey(
        "accounts.Organization",
        on_delete=models.PROTECT,
        related_name="payments",
    )
    cashfree_order_id = models.CharField(max_length=255, unique=True, db_index=True)
    cashfree_payment_id = models.CharField(max_length=255, blank=True, default="")
    cashfree_session_id = models.CharField(max_length=255, blank=True, default="")
    subscription = models.ForeignKey(
        Subscription,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="payments",
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="INR")
    status = models.CharField(
        max_length=20,
        default="pending",
        choices=PAYMENT_STATUSES,
        db_index=True,
    )
    total_refunded = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    plan_id_snapshot = models.CharField(max_length=255, blank=True, default="")
    idempotency_key = models.CharField(max_length=255, null=True, blank=True, unique=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "payments"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                check=Q(status__in=["pending", "completed", "failed", "refunded"]),
                name="payment_valid_status",
            ),
            models.CheckConstraint(
                check=Q(total_refunded__lte=models.F("amount")),
                name="payment_refund_cap",
            ),
        ]

    def __str__(self):
        return f"Payment {self.cashfree_order_id} ({self.status})"


class ProcessedWebhookEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider = models.CharField(max_length=50, default="stripe")
    event_id = models.CharField(max_length=255, db_index=True)
    event_type = models.CharField(max_length=100, blank=True, default="")
    payload = models.JSONField(default=dict, blank=True)
    processed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "processed_webhook_events"
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "event_id"],
                name="unique_webhook_event_per_provider",
            ),
        ]


class LedgerEntry(BaseModel):

    ENTRY_TYPES = [
        ("payment", "Payment"),
        ("refund", "Refund"),
        ("credit", "Credit"),
        ("debit", "Debit"),
        ("subscription_activation", "Subscription Activation"),
        ("subscription_cancellation", "Subscription Cancellation"),
        ("checkout_completed", "Checkout Completed"),
    ]

    organization = models.ForeignKey(
        "accounts.Organization",
        on_delete=models.PROTECT,
        related_name="ledger_entries",
        db_index=True,
    )
    entry_type = models.CharField(max_length=32, choices=ENTRY_TYPES, db_index=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="USD")
    reference_type = models.CharField(max_length=64, blank=True)
    reference_id = models.CharField(max_length=128, blank=True)
    stripe_event_id = models.CharField(max_length=128, blank=True, db_index=True)
    description = models.TextField(blank=True)
    created_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ledger_entries_created",
    )

    class Meta:
        db_table = "ledger_entries"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["organization", "-created_at"]),
        ]
        constraints = [
            models.CheckConstraint(
                check=Q(
                    entry_type__in=[
                        "payment",
                        "refund",
                        "credit",
                        "debit",
                        "subscription_activation",
                        "subscription_cancellation",
                        "checkout_completed",
                    ]
                ),
                name="ledger_entry_type_valid",
            ),
        ]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValueError("LedgerEntry is immutable and cannot be updated.")
        super().save(*args, **kwargs)
