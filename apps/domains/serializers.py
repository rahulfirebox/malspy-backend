import ipaddress
from urllib.parse import urlparse

from rest_framework import serializers

from .models import Domain


def _validate_ssrf_url(value: str) -> str:

    if not value:
        return value
    parsed = urlparse(value)
    if parsed.scheme not in ("https",):
        raise serializers.ValidationError("Only HTTPS webhook URLs are allowed.")
    hostname = (parsed.hostname or "").lower()
    blocked = {"localhost", "127.0.0.1", "0.0.0.0", "metadata.google.internal", "169.254.169.254"}
    if hostname in blocked:
        raise serializers.ValidationError("URL hostname is not allowed.")
    try:
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        ip = None
    if ip is not None and (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved):
        raise serializers.ValidationError("URL must point to a public host.")
    return value


class DomainReadSerializer(serializers.ModelSerializer):
    last_scan_id = serializers.UUIDField(source="last_scan.id", read_only=True)

    class Meta:
        model = Domain
        fields = [
            "id",
            "domain",
            "frequency",
            "is_active",
            "last_scan_id",
            "last_status",
            "notify_email",
            "slack_webhook_url",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class DomainWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Domain
        fields = [
            "domain",
            "frequency",
            "is_active",
            "notify_email",
        ]


DomainSerializer = DomainReadSerializer


class CreateDomainSerializer(serializers.Serializer):
    domain = serializers.CharField(max_length=500)
    frequency = serializers.ChoiceField(
        choices=["daily", "weekly", "monthly"],
        default="daily",
    )
    notify_email = serializers.BooleanField(default=True, required=False)
    slack_webhook_url = serializers.URLField(required=False, allow_null=True, allow_blank=True)

    def validate_domain(self, value):
        value = value.strip().lower()

        for prefix in ("https://", "http://", "www."):
            if value.startswith(prefix):
                value = value[len(prefix) :]
        return value.rstrip("/")

    def validate_slack_webhook_url(self, value):
        return _validate_ssrf_url(value)


class UpdateDomainSerializer(serializers.Serializer):
    frequency = serializers.ChoiceField(
        choices=["daily", "weekly", "monthly"],
        required=False,
    )
    is_active = serializers.BooleanField(required=False)
    notify_email = serializers.BooleanField(required=False)
    slack_webhook_url = serializers.URLField(required=False, allow_null=True, allow_blank=True)

    def validate_slack_webhook_url(self, value):
        return _validate_ssrf_url(value)
