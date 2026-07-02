

from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Plan",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("slug", models.CharField(max_length=20, unique=True)),
                ("name", models.CharField(max_length=50)),
                ("price_monthly", models.DecimalField(decimal_places=2, max_digits=10)),
                ("scan_quota", models.IntegerField(help_text="-1 = unlimited")),
                ("domain_quota", models.IntegerField(help_text="-1 = unlimited")),
                (
                    "agent_quota",
                    models.IntegerField(default=0, help_text="0=none, -1=unlimited"),
                ),
                ("browser_scan_enabled", models.BooleanField(default=False)),
                ("server_side_scan", models.BooleanField(default=False)),
                ("pdf_report", models.BooleanField(default=False)),
                ("api_access", models.BooleanField(default=False)),
                ("scheduled_scans", models.BooleanField(default=False)),
                ("slack_notifications", models.BooleanField(default=False)),
                ("waf_enabled", models.BooleanField(default=False)),
                ("db_scan_enabled", models.BooleanField(default=False)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "db_table": "plans",
                "ordering": ["price_monthly"],
            },
        ),
        migrations.CreateModel(
            name="Subscription",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "deleted_at",
                    models.DateTimeField(blank=True, db_index=True, null=True),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("active", "Active"),
                            ("cancelled", "Cancelled"),
                            ("past_due", "Past Due"),
                            ("trialing", "Trialing"),
                        ],
                        db_index=True,
                        default="active",
                        max_length=20,
                    ),
                ),
                (
                    "stripe_subscription_id",
                    models.CharField(blank=True, max_length=100, null=True),
                ),
                ("current_period_start", models.DateTimeField(blank=True, null=True)),
                ("current_period_end", models.DateTimeField(blank=True, null=True)),
                ("cancelled_at", models.DateTimeField(blank=True, null=True)),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="subscriptions",
                        to="accounts.organization",
                    ),
                ),
                (
                    "plan",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="subscriptions",
                        to="billing.plan",
                    ),
                ),
            ],
            options={
                "db_table": "subscriptions",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="Invoice",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "deleted_at",
                    models.DateTimeField(blank=True, db_index=True, null=True),
                ),
                (
                    "stripe_invoice_id",
                    models.CharField(
                        blank=True, max_length=100, null=True, unique=True
                    ),
                ),
                ("amount", models.DecimalField(decimal_places=2, max_digits=10)),
                ("currency", models.CharField(default="USD", max_length=3)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("paid", "Paid"),
                            ("unpaid", "Unpaid"),
                            ("void", "Void"),
                        ],
                        db_index=True,
                        default="unpaid",
                        max_length=20,
                    ),
                ),
                ("paid_at", models.DateTimeField(blank=True, null=True)),
                (
                    "invoice_pdf_url",
                    models.CharField(blank=True, max_length=500, null=True),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="invoices",
                        to="accounts.organization",
                    ),
                ),
                (
                    "subscription",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="invoices",
                        to="billing.subscription",
                    ),
                ),
            ],
            options={
                "db_table": "invoices",
                "ordering": ["-created_at"],
            },
        ),
    ]
