from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("alerts", "0003_initial"),
    ]

    operations = [

        migrations.AddConstraint(
            model_name="alert",
            constraint=models.UniqueConstraint(
                condition=models.Q(deleted_at__isnull=True),
                fields=["organization", "scan", "type"],
                name="unique_active_alert_per_scan_type",
            ),
        ),
    ]
