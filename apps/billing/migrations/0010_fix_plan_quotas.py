from django.db import migrations


def fix_plan_quotas(apps, schema_editor):
    Plan = apps.get_model("billing", "Plan")
    Plan.objects.filter(slug="free").update(scan_quota=5, domain_quota=1, agent_quota=0)
    Plan.objects.filter(slug="pro").update(
        scan_quota=100, domain_quota=10, agent_quota=5
    )
    Plan.objects.filter(slug="enterprise").update(
        scan_quota=-1, domain_quota=-1, agent_quota=-1
    )


def reverse_fix_plan_quotas(apps, schema_editor):
    Plan = apps.get_model("billing", "Plan")
    Plan.objects.filter(slug="free").update(
        scan_quota=10, domain_quota=1, agent_quota=0
    )
    Plan.objects.filter(slug="pro").update(
        scan_quota=100, domain_quota=5, agent_quota=3
    )
    Plan.objects.filter(slug="enterprise").update(
        scan_quota=1000, domain_quota=50, agent_quota=-1
    )


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0009_subscription_plan_expires_at_and_more"),
    ]

    operations = [
        migrations.RunPython(fix_plan_quotas, reverse_code=reverse_fix_plan_quotas),
    ]
