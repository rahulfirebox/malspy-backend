from rest_framework import serializers

from .models import Scan


class ScanReadSerializer(serializers.ModelSerializer):
    duration_seconds = serializers.SerializerMethodField()
    rating = serializers.CharField(source="overall_rating")
    organization = serializers.UUIDField(source="organization.id", read_only=True)
    created_by = serializers.UUIDField(source="created_by.id", read_only=True)

    class Meta:
        model = Scan
        fields = [
            "id",
            "url",
            "domain",
            "status",
            "rating",
            "malware_detected",
            "blacklisted",
            "was_cached",
            "notify_email",
            "organization",
            "created_by",
            "created_at",
            "completed_at",
            "duration_seconds",
        ]

    def get_duration_seconds(self, obj):
        if obj.scan_duration_ms is not None:
            return round(obj.scan_duration_ms / 1000, 1)
        return None


class ScanDetailSerializer(serializers.ModelSerializer):
    duration_seconds = serializers.SerializerMethodField()
    rating = serializers.CharField(source="overall_rating")
    organization = serializers.UUIDField(source="organization_id", allow_null=True)
    created_by = serializers.UUIDField(source="created_by_id", allow_null=True)
    created_by_email = serializers.CharField(source="created_by.email", read_only=True)

    site = serializers.JSONField(source="site_info")
    tls = serializers.JSONField(source="tls_info")
    tls_direct = serializers.JSONField(source="tls_direct_info")
    whois = serializers.JSONField(source="whois_info")
    malware = serializers.JSONField(source="malware_info")
    malware_findings_detail = serializers.SerializerMethodField()
    browser_scan = serializers.SerializerMethodField()
    blacklists = serializers.JSONField(source="blacklist_info")
    links = serializers.JSONField(source="links_info")
    our_scanner = serializers.SerializerMethodField()

    class Meta:
        model = Scan
        fields = [
            "id",
            "url",
            "domain",
            "status",
            "rating",
            "malware_detected",
            "blacklisted",
            "was_cached",
            "notify_email",
            "organization",
            "created_by",
            "created_at",
            "completed_at",
            "duration_seconds",
            "created_by_email",
            "site",
            "tls",
            "tls_direct",
            "whois",
            "recommendations",
            "malware",
            "malware_findings_detail",
            "browser_scan",
            "blacklists",
            "links",
            "our_scanner",
        ]

    def get_duration_seconds(self, obj):
        if obj.scan_duration_ms is not None:
            return round(obj.scan_duration_ms / 1000, 1)
        return None

    def get_malware_findings_detail(self, obj):
        return (obj.malware_info or {}).get("findings", [])

    def get_browser_scan(self, obj):
        if obj.browser_scan_info:
            return {
                "available": True,
                "plan_required": "pro",
                **obj.browser_scan_info,
            }
        return {
            "available": False,
            "plan_required": "pro",
            "detected": False,
            "note": "Browser scan requires Pro plan or higher.",
        }

    def get_our_scanner(self, obj):
        l1 = obj.malware_info or {}
        l2 = obj.browser_scan_info or {}
        l1_detected = l1.get("detected", False)
        l2_detected = l2.get("detected", False)
        l1_count = len(l1.get("findings", []))
        l2_count = len(l2.get("malicious_requests", []))
        return {
            "layer1_detected": l1_detected,
            "layer2_detected": l2_detected,
            "overall_detected": l1_detected or l2_detected,
            "layer1_findings_count": l1_count,
            "layer2_findings_count": l2_count,
            "note": "Our scanner catches new malware immediately. Blacklist providers may take days/weeks to update.",
        }


class ScanStatusSerializer(serializers.ModelSerializer):
    progress_percent = serializers.SerializerMethodField()
    estimated_seconds_remaining = serializers.SerializerMethodField()

    class Meta:
        model = Scan
        fields = ["id", "status", "progress_percent", "estimated_seconds_remaining"]

    def get_progress_percent(self, obj):
        progress_map = {
            "queued": 5,
            "scanning": 50,
            "completed": 100,
            "failed": 0,
        }
        return progress_map.get(obj.status, 0)

    def get_estimated_seconds_remaining(self, obj):
        if obj.status == "completed":
            return 0
        if obj.status == "scanning":
            return 15
        if obj.status == "queued":
            return 30
        return None


class CreateScanSerializer(serializers.Serializer):
    url = serializers.URLField(max_length=2000)
    notify_email = serializers.BooleanField(default=True, required=False)
    schedule = serializers.CharField(allow_null=True, required=False)

    def validate_url(self, value):
        value = value.strip()
        if not value.startswith(("http://", "https://")):
            raise serializers.ValidationError({"url": "URL must start with http:// or https://"})
        return value

    def validate_schedule(self, value):
        if value is not None:
            raise serializers.ValidationError(
                {"schedule": "Scheduled scans are not yet supported."}
            )
        return value


ScanSerializer = ScanDetailSerializer


class PublicScanSerializer(serializers.Serializer):
    url = serializers.URLField(max_length=2000)

    def validate_url(self, value):
        value = value.strip()
        if not value.startswith(("http://", "https://")):
            raise serializers.ValidationError({"url": "URL must start with http:// or https://"})
        return value
