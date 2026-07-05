from django.contrib import admin

from .models import Plan


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "slug",
        "price_monthly",
        "price_yearly",
        "domain_quota",
        "scan_quota",
        "agent_quota",
        "is_active",
        "created_at",
    )
    search_fields = ("name", "slug")
    list_filter = ("is_active",)
    readonly_fields = ("created_at",)
    fieldsets = (
        (None, {"fields": ("slug", "name", "is_active")}),
        ("Pricing", {"fields": ("price_monthly", "price_yearly")}),
        (
            "Quotas",
            {"fields": ("scan_quota", "domain_quota", "agent_quota")},
        ),
        (
            "Features",
            {
                "fields": (
                    "browser_scan_enabled",
                    "server_side_scan",
                    "pdf_report",
                    "api_access",
                    "scheduled_scans",
                    "slack_notifications",
                    "waf_enabled",
                    "db_scan_enabled",
                ),
            },
        ),
        ("Timestamps", {"fields": ("created_at",)}),
    )
