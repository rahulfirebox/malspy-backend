from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0004_passwordresettoken_token_hash_unique"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="organization",
            constraint=models.CheckConstraint(
                check=Q(scan_quota_used__gte=0),
                name="check_org_scan_quota_used_non_negative",
            ),
        ),
    ]
