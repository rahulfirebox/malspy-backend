from rest_framework import serializers

from .models import Alert


class AlertReadSerializer(serializers.ModelSerializer):
    scan_domain = serializers.CharField(source="scan.domain", read_only=True)
    domain = serializers.CharField(source="domain.domain", read_only=True, default=None)
    resolved_by_email = serializers.CharField(source="resolved_by.email", read_only=True)

    class Meta:
        model = Alert
        fields = [
            "id",
            "type",
            "severity",
            "title",
            "description",
            "is_resolved",
            "resolved_by_email",
            "resolved_note",
            "resolved_at",
            "scan_domain",
            "domain",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "type",
            "severity",
            "title",
            "description",
            "is_resolved",
            "resolved_by_email",
            "resolved_note",
            "resolved_at",
            "scan_domain",
            "domain",
            "created_at",
        ]


class AlertWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Alert
        fields = [
            "title",
            "description",
            "severity",
        ]

    def validate_severity(self, value):
        allowed = {"critical", "high", "medium", "low"}
        if value not in allowed:
            raise serializers.ValidationError(
                {"severity": f"Must be one of: {', '.join(sorted(allowed))}."}
            )
        return value


AlertSerializer = AlertReadSerializer


class ResolveAlertSerializer(serializers.Serializer):
    resolved_note = serializers.CharField(required=False, allow_blank=True)


class BulkResolveSerializer(serializers.Serializer):
    ids = serializers.ListField(
        child=serializers.UUIDField(),
        min_length=1,
        max_length=100,
    )
