from django.db import models
from django.db.models import Q

from apps.core.models import BaseModel


class MalwareSignature(BaseModel):
    signature_id = models.CharField(max_length=20, unique=True, db_index=True)
    name = models.CharField(max_length=200, unique=True)
    layer = models.CharField(
        max_length=10,
        choices=[("static", "Static"), ("browser", "Browser"), ("server", "Server")],
        db_index=True,
    )
    pattern = models.TextField()
    severity = models.CharField(
        max_length=10,
        choices=[
            ("critical", "Critical"),
            ("high", "High"),
            ("medium", "Medium"),
            ("low", "Low"),
        ],
        db_index=True,
    )
    type = models.CharField(max_length=50, db_index=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    auto_updated = models.BooleanField(default=False)

    class Meta:
        db_table = "malware_signatures"
        ordering = ["signature_id"]
        constraints = [
            models.CheckConstraint(
                check=Q(layer__in=["static", "browser", "server"]),
                name="signature_layer_valid",
            ),
            models.CheckConstraint(
                check=Q(severity__in=["critical", "high", "medium", "low"]),
                name="signature_severity_valid",
            ),
        ]

    def __str__(self):
        return f"{self.signature_id}: {self.name}"


class Scan(BaseModel):
    organization = models.ForeignKey(
        "accounts.Organization",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="scans",
        db_index=True,
    )
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="scans",
    )
    updated_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="scans_updated",
    )
    url = models.CharField(max_length=2000)
    domain = models.CharField(max_length=500, db_index=True)
    status = models.CharField(
        max_length=20,
        choices=[
            ("queued", "Queued"),
            ("scanning", "Scanning"),
            ("completed", "Completed"),
            ("failed", "Failed"),
        ],
        default="queued",
        db_index=True,
    )
    is_public = models.BooleanField(default=False, db_index=True)
    overall_rating = models.CharField(max_length=1, blank=True, default="", db_index=True)
    malware_detected = models.BooleanField(default=False, db_index=True)
    blacklisted = models.BooleanField(default=False, db_index=True)

    sucuri_raw = models.JSONField(null=True, blank=True)

    site_info = models.JSONField(null=True, blank=True)
    tls_info = models.JSONField(null=True, blank=True)
    tls_direct_info = models.JSONField(null=True, blank=True)
    whois_info = models.JSONField(null=True, blank=True)
    recommendations = models.JSONField(null=True, blank=True)
    blacklist_info = models.JSONField(null=True, blank=True)
    links_info = models.JSONField(null=True, blank=True)
    ratings_info = models.JSONField(null=True, blank=True)
    software_info = models.JSONField(null=True, blank=True)

    malware_info = models.JSONField(null=True, blank=True)
    browser_scan_info = models.JSONField(null=True, blank=True)

    scan_duration_ms = models.IntegerField(null=True, blank=True)
    notify_email = models.BooleanField(default=True)
    was_cached = models.BooleanField(default=False)
    cache_source_id = models.UUIDField(null=True, blank=True)
    parent_scan_id = models.UUIDField(null=True, blank=True)

    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "scans"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["organization", "status"]),
            models.Index(fields=["organization", "domain"]),
            models.Index(fields=["organization", "created_at"]),
            models.Index(fields=["organization", "overall_rating"]),
        ]
        constraints = [
            models.CheckConstraint(
                check=Q(status__in=["queued", "scanning", "completed", "failed"]),
                name="scan_status_valid",
            ),
        ]

    def __str__(self):
        return f"Scan({self.domain}, {self.status})"
