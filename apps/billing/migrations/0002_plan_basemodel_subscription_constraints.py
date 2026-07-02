from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0001_initial"),
    ]

    operations = [

        migrations.AddField(
            model_name="plan",
            name="updated_at",
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.AddField(
            model_name="plan",
            name="deleted_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),

        migrations.AlterField(
            model_name="subscription",
            name="stripe_subscription_id",
            field=models.CharField(
                blank=True, db_index=True, max_length=255, null=True
            ),
        ),

        migrations.AddConstraint(
            model_name="subscription",
            constraint=models.UniqueConstraint(
                condition=models.Q(status="active", deleted_at__isnull=True),
                fields=["organization"],
                name="unique_active_subscription_per_org",
            ),
        ),
    ]
