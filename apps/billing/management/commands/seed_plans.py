from django.core.management.base import BaseCommand

from apps.billing.models import Plan

PLANS = [
    {
        "slug": "free",
        "name": "Free",
        "price_monthly": "0.00",
        "scan_quota": 5,
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
    },
    {
        "slug": "pro",
        "name": "Pro",
        "price_monthly": "19.99",
        "scan_quota": 100,
        "domain_quota": 10,
        "agent_quota": 5,
        "browser_scan_enabled": True,
        "server_side_scan": True,
        "pdf_report": True,
        "api_access": False,
        "scheduled_scans": True,
        "slack_notifications": True,
        "waf_enabled": False,
        "db_scan_enabled": False,
    },
    {
        "slug": "enterprise",
        "name": "Enterprise",
        "price_monthly": "99.00",
        "scan_quota": -1,
        "domain_quota": -1,
        "agent_quota": -1,
        "browser_scan_enabled": True,
        "server_side_scan": True,
        "pdf_report": True,
        "api_access": True,
        "scheduled_scans": True,
        "slack_notifications": True,
        "waf_enabled": True,
        "db_scan_enabled": True,
    },
]


class Command(BaseCommand):
    help = "Seed the plans table with default plans (free, pro, enterprise)."

    def handle(self, *args, **options):
        for plan_data in PLANS:
            plan, created = Plan.objects.update_or_create(
                slug=plan_data["slug"],
                defaults=plan_data,
            )
            action = "Created" if created else "Updated"
            self.stdout.write(self.style.SUCCESS(f"{action} plan: {plan.name}"))

        self.stdout.write(self.style.SUCCESS("Plans seeded successfully."))
