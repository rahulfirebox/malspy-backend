

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("domains", "0004_domain_next_scan_at"),
    ]

    operations = [
        migrations.AlterField(
            model_name="domain",
            name="slack_webhook_url",
            field=models.CharField(blank=True, default="", max_length=500),
        ),
        migrations.AlterField(
            model_name="domain",
            name="updated_at",
            field=models.DateTimeField(auto_now=True, db_index=True),
        ),
        migrations.AddConstraint(
            model_name="domain",
            constraint=models.CheckConstraint(
                check=models.Q(("frequency__in", ["daily", "weekly", "monthly"])),
                name="domain_frequency_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="domain",
            constraint=models.CheckConstraint(
                check=models.Q(
                    ("last_status__in", ["clean", "infected", "blacklisted", "unknown"])
                ),
                name="domain_last_status_valid",
            ),
        ),
    ]
