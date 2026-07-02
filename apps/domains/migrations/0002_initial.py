

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0002_initial"),
        ("scans", "0001_initial"),
        ("domains", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="domain",
            name="last_scan",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="monitored_domain_last_scan",
                to="scans.scan",
            ),
        ),
        migrations.AddField(
            model_name="domain",
            name="organization",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="domains",
                to="accounts.organization",
            ),
        ),
        migrations.AddIndex(
            model_name="domain",
            index=models.Index(
                fields=["organization", "last_status"],
                name="domains_organiz_75536b_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="domain",
            index=models.Index(
                fields=["organization", "is_active"], name="domains_organiz_64f243_idx"
            ),
        ),
        migrations.AddConstraint(
            model_name="domain",
            constraint=models.UniqueConstraint(
                condition=models.Q(("deleted_at__isnull", True)),
                fields=("organization", "domain"),
                name="unique_active_domain_per_org",
            ),
        ),
    ]
