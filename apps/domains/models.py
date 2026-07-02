from django.db import models
from django.db.models import Q

from apps.core.models import BaseModel


class Domain(BaseModel):
    organization = models.ForeignKey(
        "accounts.Organization",
        on_delete=models.CASCADE,
        related_name="domains",
        db_index=True,
    )
    domain = models.CharField(max_length=500, db_index=True)
    frequency = models.CharField(
        max_length=10,
        choices=[("daily", "Daily"), ("weekly", "Weekly"), ("monthly", "Monthly")],
        default="daily",
        db_index=True,
    )
    is_active = models.BooleanField(default=True, db_index=True)
    last_scan = models.ForeignKey(
        "scans.Scan",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="monitored_domain_last_scan",
    )
    last_status = models.CharField(
        max_length=20,
        choices=[
            ("clean", "Clean"),
            ("infected", "Infected"),
            ("blacklisted", "Blacklisted"),
            ("unknown", "Unknown"),
        ],
        default="unknown",
        db_index=True,
    )
    slack_webhook_url = models.CharField(max_length=500, blank=True, default="")
    notify_email = models.BooleanField(default=True)
    next_scan_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="domains_created",
    )
    updated_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="domains_updated",
    )

    class Meta:
        db_table = "domains"
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "domain"],
                condition=Q(deleted_at__isnull=True),
                name="unique_active_domain_per_org",
            ),
            models.CheckConstraint(
                check=Q(frequency__in=["daily", "weekly", "monthly"]),
                name="domain_frequency_valid",
            ),
            models.CheckConstraint(
                check=Q(last_status__in=["clean", "infected", "blacklisted", "unknown"]),
                name="domain_last_status_valid",
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "last_status"]),
            models.Index(fields=["organization", "is_active"]),
        ]

    def __str__(self):
        return self.domain
