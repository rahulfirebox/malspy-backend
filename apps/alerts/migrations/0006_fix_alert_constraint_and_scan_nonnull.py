from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("alerts", "0005_alert_scan_nullable"),
        ("scans", "0001_initial"),
    ]

    operations = [

        migrations.RemoveConstraint(
            model_name="alert",
            name="unique_active_alert_per_scan_type",
        ),

        migrations.AlterField(
            model_name="alert",
            name="scan",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="alerts",
                to="scans.scan",
            ),
        ),

        migrations.AddConstraint(
            model_name="alert",
            constraint=models.UniqueConstraint(
                fields=["organization", "scan", "type"],
                condition=models.Q(is_resolved=False),
                name="unique_open_alert_per_scan_type",
            ),
        ),
    ]
