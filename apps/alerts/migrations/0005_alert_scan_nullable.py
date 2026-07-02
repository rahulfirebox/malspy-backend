from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("alerts", "0004_alert_unique_constraint"),
        ("scans", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="alert",
            name="scan",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="alerts",
                to="scans.scan",
            ),
        ),
    ]
