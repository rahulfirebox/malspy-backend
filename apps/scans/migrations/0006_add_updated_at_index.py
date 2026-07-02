

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("scans", "0005_malwaresignature_name_unique"),
    ]

    operations = [
        migrations.AlterField(
            model_name="malwaresignature",
            name="updated_at",
            field=models.DateTimeField(auto_now=True, db_index=True),
        ),
        migrations.AlterField(
            model_name="scan",
            name="overall_rating",
            field=models.CharField(blank=True, db_index=True, default="", max_length=1),
        ),
        migrations.AlterField(
            model_name="scan",
            name="updated_at",
            field=models.DateTimeField(auto_now=True, db_index=True),
        ),
        migrations.AddConstraint(
            model_name="malwaresignature",
            constraint=models.CheckConstraint(
                check=models.Q(("layer__in", ["static", "browser", "server"])),
                name="signature_layer_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="malwaresignature",
            constraint=models.CheckConstraint(
                check=models.Q(("severity__in", ["critical", "high", "medium", "low"])),
                name="signature_severity_valid",
            ),
        ),
    ]
