from rest_framework import serializers

from .models import Invoice, Plan, Subscription

_BILLING_PERIODS = ["monthly", "yearly"]


class PlanReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plan
        fields = [
            "id",
            "slug",
            "name",
            "price_monthly",
            "price_yearly",
            "scan_quota",
            "domain_quota",
            "agent_quota",
            "api_access",
            "pdf_report",
            "browser_scan_enabled",
            "server_side_scan",
            "scheduled_scans",
            "slack_notifications",
            "waf_enabled",
            "db_scan_enabled",
            "is_active",
            "created_at",
        ]
        read_only_fields = fields


class PlanWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plan
        fields = [
            "slug",
            "name",
            "price_monthly",
            "price_yearly",
            "scan_quota",
            "domain_quota",
            "agent_quota",
            "api_access",
            "pdf_report",
            "browser_scan_enabled",
            "server_side_scan",
            "scheduled_scans",
            "slack_notifications",
            "waf_enabled",
            "db_scan_enabled",
            "is_active",
        ]


PlanSerializer = PlanReadSerializer


class SubscriptionReadSerializer(serializers.ModelSerializer):
    plan = PlanReadSerializer(read_only=True)

    class Meta:
        model = Subscription
        fields = [
            "id",
            "plan",
            "status",
            "stripe_subscription_id",
            "current_period_start",
            "current_period_end",
            "cancelled_at",
            "plan_expires_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class SubscriptionWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subscription
        fields = [
            "plan",
            "status",
            "stripe_subscription_id",
            "current_period_start",
            "current_period_end",
            "cancelled_at",
            "plan_expires_at",
        ]


SubscriptionSerializer = SubscriptionReadSerializer


class InvoiceReadSerializer(serializers.ModelSerializer):
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = Invoice
        fields = [
            "id",
            "stripe_invoice_id",
            "amount",
            "currency",
            "status",
            "period_start",
            "period_end",
            "paid_at",
            "invoice_pdf_url",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class InvoiceWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Invoice
        fields = [
            "subscription",
            "stripe_invoice_id",
            "amount",
            "currency",
            "status",
            "period_start",
            "period_end",
            "paid_at",
            "invoice_pdf_url",
        ]


InvoiceSerializer = InvoiceReadSerializer


class UpgradePlanSerializer(serializers.Serializer):
    plan_slug = serializers.CharField(max_length=50)
    billing_period = serializers.ChoiceField(choices=_BILLING_PERIODS)

    def validate_plan_slug(self, value):
        if value == "free":
            raise serializers.ValidationError(
                {"plan_slug": "Cannot upgrade to free plan via this endpoint."}
            )
        if not Plan.objects.filter(slug=value, is_active=True).exists():
            raise serializers.ValidationError({"plan_slug": "Invalid plan slug."})
        return value


class CreateOrderSerializer(serializers.Serializer):
    plan_slug = serializers.CharField(max_length=50)

    def validate_plan_slug(self, value):
        if value == "free":
            raise serializers.ValidationError("Cannot create order for free plan.")
        if not Plan.objects.filter(slug=value, is_active=True).exists():
            raise serializers.ValidationError("Invalid plan slug.")
        return value


class VerifyPaymentSerializer(serializers.Serializer):
    order_id = serializers.CharField(max_length=255)
