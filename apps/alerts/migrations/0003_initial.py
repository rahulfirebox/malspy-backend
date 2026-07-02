

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("alerts", "0002_initial"),
        ("scans", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="alert",
            name="scan",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="alerts",
                to="scans.scan",
            ),
        ),
        migrations.AddIndex(
            model_name="alert",
            index=models.Index(
                fields=["organization", "is_resolved"], name="alerts_organiz_45f3e7_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="alert",
            index=models.Index(
                fields=["organization", "severity"], name="alerts_organiz_355fb8_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="alert",
            index=models.Index(
                fields=["organization", "type"], name="alerts_organiz_19ac9a_idx"
            ),
        ),
    ]
