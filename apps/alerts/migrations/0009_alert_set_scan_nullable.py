from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("alerts", "0008_alert_created_by_updated_by"),
        ("scans", "0001_initial"),
    ]

    operations = [


        migrations.RemoveConstraint(
            model_name="alert",
            name="unique_open_alert_per_scan_type",
        ),

        migrations.AlterField(
            model_name="alert",
            name="scan",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="alerts",
                to="scans.scan",
            ),
        ),
    ]
