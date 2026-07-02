

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("scans", "0003_basemodel_inheritance"),
    ]

    operations = [
        migrations.AddField(
            model_name="scan",
            name="updated_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="scans_updated",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name="malwaresignature",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True, db_index=True),
        ),
        migrations.AddConstraint(
            model_name="scan",
            constraint=models.CheckConstraint(
                check=models.Q(
                    ("status__in", ["queued", "scanning", "completed", "failed"])
                ),
                name="scan_status_valid",
            ),
        ),
    ]
