

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0006_ledger_entry"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("billing", "0006_plan_price_yearly"),
    ]

    operations = [
        migrations.CreateModel(
            name="LedgerEntry",
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
                    "entry_type",
                    models.CharField(
                        choices=[
                            ("payment", "Payment"),
                            ("refund", "Refund"),
                            ("credit", "Credit"),
                            ("debit", "Debit"),
                            ("subscription_activation", "Subscription Activation"),
                        ],
                        db_index=True,
                        max_length=32,
                    ),
                ),
                ("amount", models.DecimalField(decimal_places=2, max_digits=12)),
                ("currency", models.CharField(default="USD", max_length=3)),
                ("reference_type", models.CharField(blank=True, max_length=64)),
                ("reference_id", models.CharField(blank=True, max_length=128)),
                (
                    "stripe_event_id",
                    models.CharField(blank=True, db_index=True, max_length=128),
                ),
                ("description", models.TextField(blank=True)),
            ],
            options={
                "db_table": "ledger_entries",
                "ordering": ["-created_at"],
            },
        ),
        migrations.RemoveConstraint(
            model_name="subscription",
            name="unique_active_subscription_per_org",
        ),

        migrations.RemoveField(
            model_name="plan",
            name="deleted_at",
        ),
        migrations.RemoveField(
            model_name="plan",
            name="updated_at",
        ),
        migrations.AlterField(
            model_name="subscription",
            name="stripe_subscription_id",
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
        migrations.AddConstraint(
            model_name="subscription",
            constraint=models.UniqueConstraint(
                condition=models.Q(("status__in", ["active", "trialing"])),
                fields=("organization",),
                name="unique_active_subscription_per_org",
            ),
        ),
        migrations.AddField(
            model_name="ledgerentry",
            name="created_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="ledger_entries_created",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="ledgerentry",
            name="organization",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="ledger_entries",
                to="accounts.organization",
            ),
        ),
        migrations.AddIndex(
            model_name="ledgerentry",
            index=models.Index(
                fields=["organization", "-created_at"],
                name="ledger_entr_organiz_d67402_idx",
            ),
        ),
    ]
