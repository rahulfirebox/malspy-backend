

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0008_invoice_period_start_period_end"),
    ]

    operations = [
        migrations.AddField(
            model_name="subscription",
            name="plan_expires_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="ledgerentry",
            name="entry_type",
            field=models.CharField(
                choices=[
                    ("payment", "Payment"),
                    ("refund", "Refund"),
                    ("credit", "Credit"),
                    ("debit", "Debit"),
                    ("subscription_activation", "Subscription Activation"),
                    ("subscription_cancellation", "Subscription Cancellation"),
                    ("checkout_completed", "Checkout Completed"),
                ],
                db_index=True,
                max_length=32,
            ),
        ),
        migrations.AlterField(
            model_name="subscription",
            name="status",
            field=models.CharField(
                choices=[
                    ("active", "Active"),
                    ("cancelled", "Cancelled"),
                    ("past_due", "Past Due"),
                    ("trialing", "Trialing"),
                    ("unpaid", "Unpaid"),
                ],
                db_index=True,
                default="active",
                max_length=20,
            ),
        ),
    ]
