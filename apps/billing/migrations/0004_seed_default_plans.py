from django.db import migrations


def seed_plans(apps, schema_editor):
    Plan = apps.get_model("billing", "Plan")
    plans = [
        {
            "slug": "free",
            "name": "Free",
            "price_monthly": "0.00",
            "scan_quota": 10,
            "domain_quota": 1,
            "agent_quota": 0,
            "browser_scan_enabled": False,
            "server_side_scan": False,
            "pdf_report": False,
            "api_access": False,
            "scheduled_scans": False,
            "slack_notifications": False,
            "waf_enabled": False,
            "db_scan_enabled": False,
            "is_active": True,
        },
        {
            "slug": "pro",
            "name": "Pro",
            "price_monthly": "29.00",
            "scan_quota": 100,
            "domain_quota": 5,
            "agent_quota": 3,
            "browser_scan_enabled": True,
            "server_side_scan": True,
            "pdf_report": True,
            "api_access": True,
            "scheduled_scans": True,
            "slack_notifications": True,
            "waf_enabled": False,
            "db_scan_enabled": False,
            "is_active": True,
        },
        {
            "slug": "enterprise",
            "name": "Enterprise",
            "price_monthly": "99.00",
            "scan_quota": 1000,
            "domain_quota": 50,
            "agent_quota": -1,
            "browser_scan_enabled": True,
            "server_side_scan": True,
            "pdf_report": True,
            "api_access": True,
            "scheduled_scans": True,
            "slack_notifications": True,
            "waf_enabled": True,
            "db_scan_enabled": True,
            "is_active": True,
        },
    ]
    for plan_data in plans:
        slug = plan_data.pop("slug")
        Plan.objects.get_or_create(slug=slug, defaults=plan_data)


def reverse_seed_plans(apps, schema_editor):
    Plan = apps.get_model("billing", "Plan")
    Plan.objects.filter(slug__in=["free", "pro", "enterprise"]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0003_processedwebhookevent"),
    ]

    operations = [
        migrations.RunPython(seed_plans, reverse_code=reverse_seed_plans),
    ]
