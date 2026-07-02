from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0004_seed_default_plans"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="plan",
            constraint=models.CheckConstraint(
                check=Q(scan_quota__gte=-1)
                & Q(domain_quota__gte=-1)
                & Q(agent_quota__gte=-1),
                name="check_plan_quota_fields_valid",
            ),
        ),
    ]
