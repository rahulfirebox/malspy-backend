from rest_framework import serializers

from .models import ServerAgent, ServerScanResult


class ServerAgentReadSerializer(serializers.ModelSerializer):
    type = serializers.CharField(source="agent_type", read_only=True)
    version = serializers.CharField(source="agent_version", read_only=True)
    domain = serializers.SerializerMethodField()
    revoked = serializers.SerializerMethodField()
    created_by = serializers.SerializerMethodField()

    class Meta:
        model = ServerAgent
        fields = [
            "id",
            "name",
            "type",
            "token_prefix",
            "domain",
            "status",
            "version",
            "last_seen_at",
            "last_scan_at",
            "revoked",
            "created_by",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "name",
            "type",
            "token_prefix",
            "domain",
            "status",
            "version",
            "last_seen_at",
            "last_scan_at",
            "revoked",
            "created_by",
            "created_at",
        ]

    def get_domain(self, obj):
        if obj.domain:
            return {"id": str(obj.domain.id), "domain": obj.domain.domain}
        return None

    def get_revoked(self, obj):
        return obj.status == "revoked"

    def get_created_by(self, obj):
        if obj.created_by:
            return {"id": str(obj.created_by.id), "email": obj.created_by.email}
        return None


ServerAgentSerializer = ServerAgentReadSerializer


class ServerAgentWriteSerializer(serializers.ModelSerializer):
    domain = serializers.UUIDField(required=False, allow_null=True)

    class Meta:
        model = ServerAgent
        fields = [
            "name",
            "agent_type",
            "domain",
        ]

    def validate_agent_type(self, value):
        allowed = {"wordpress_plugin", "php_script", "python_script"}
        if value not in allowed:
            raise serializers.ValidationError(
                f"agent_type must be one of: {', '.join(sorted(allowed))}."
            )
        return value


class ServerAgentCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    domain = serializers.UUIDField(required=False, allow_null=True)
    agent_type = serializers.ChoiceField(
        choices=["wordpress_plugin", "php_script", "python_script"],
        default="python_script",
    )

    def validate_name(self, value):
        from django.utils.html import strip_tags

        return strip_tags(value).strip()


class ServerScanResultReadSerializer(serializers.ModelSerializer):
    scan_duration_seconds = serializers.SerializerMethodField()

    class Meta:
        model = ServerScanResult
        fields = [
            "id",
            "files_scanned",
            "files_infected",
            "findings",
            "scan_duration_ms",
            "scan_duration_seconds",
            "malware_found",
            "agent_version",
            "status",
            "completed_at",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "files_scanned",
            "files_infected",
            "findings",
            "scan_duration_ms",
            "scan_duration_seconds",
            "malware_found",
            "agent_version",
            "status",
            "completed_at",
            "created_at",
        ]

    def get_scan_duration_seconds(self, obj):
        return round(obj.scan_duration_ms / 1000, 2) if obj.scan_duration_ms else None


ServerScanResultSerializer = ServerScanResultReadSerializer


class AgentFindingSerializer(serializers.Serializer):
    type = serializers.CharField(max_length=100)
    severity = serializers.CharField(max_length=50)
    file_path = serializers.CharField(max_length=1000)
    signature_id = serializers.CharField(max_length=200)
    description = serializers.CharField(max_length=1000, required=False, allow_blank=True)
    url = serializers.CharField(max_length=2000, required=False, allow_blank=True)
    matched_snippet = serializers.CharField(max_length=500, required=False, allow_blank=True)


class AgentReportSerializer(serializers.Serializer):
    agent_id = serializers.CharField(max_length=100, required=False, allow_blank=True)
    scan_started_at = serializers.DateTimeField(required=False, allow_null=True)
    scan_completed_at = serializers.DateTimeField(required=False, allow_null=True)
    server_path = serializers.CharField(max_length=500, required=False, allow_blank=True)
    files_infected = serializers.IntegerField(min_value=0, default=0)
    findings = serializers.ListField(
        child=AgentFindingSerializer(),
        default=list,
        max_length=100,
    )
    files_scanned = serializers.IntegerField(min_value=0)
    scan_duration_ms = serializers.IntegerField(min_value=0)
    agent_version = serializers.CharField(max_length=20, required=False, default="1.0.0")
