

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("alerts", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("accounts", "0002_initial"),
        ("domains", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="alert",
            name="domain",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="alerts",
                to="domains.domain",
            ),
        ),
        migrations.AddField(
            model_name="alert",
            name="organization",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="alerts",
                to="accounts.organization",
            ),
        ),
        migrations.AddField(
            model_name="alert",
            name="resolved_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="resolved_alerts",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
