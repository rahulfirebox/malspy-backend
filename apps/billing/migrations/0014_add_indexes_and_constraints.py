

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0013_payment_planprice_processedwebhookevent_event_type_and_more"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="subscription",
            name="unique_active_subscription_per_org",
        ),
        migrations.AlterField(
            model_name="invoice",
            name="updated_at",
            field=models.DateTimeField(auto_now=True, db_index=True),
        ),
        migrations.AlterField(
            model_name="ledgerentry",
            name="updated_at",
            field=models.DateTimeField(auto_now=True, db_index=True),
        ),
        migrations.AlterField(
            model_name="payment",
            name="updated_at",
            field=models.DateTimeField(auto_now=True, db_index=True),
        ),
        migrations.AlterField(
            model_name="subscription",
            name="updated_at",
            field=models.DateTimeField(auto_now=True, db_index=True),
        ),
        migrations.AddConstraint(
            model_name="subscription",
            constraint=models.UniqueConstraint(
                condition=models.Q(
                    ("status__in", ["active", "trialing"]), ("deleted_at__isnull", True)
                ),
                fields=("organization",),
                name="unique_active_subscription_per_org",
            ),
        ),
    ]
