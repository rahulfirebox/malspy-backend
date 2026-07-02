

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("alerts", "0009_alert_set_scan_nullable"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="alert",
            constraint=models.UniqueConstraint(
                condition=models.Q(("is_resolved", False)),
                fields=("organization", "domain", "type"),
                name="unique_active_alert_per_type",
            ),
        ),
    ]
