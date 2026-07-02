from rest_framework import serializers

from .models import ApiKey


class ApiKeyReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = ApiKey
        fields = [
            "id",
            "name",
            "key_prefix",
            "revoked",
            "last_used_at",
            "expires_at",
            "created_at",
        ]
        read_only_fields = fields


class ApiKeyWriteSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200, min_length=1)
    expires_at = serializers.DateTimeField(required=False, allow_null=True)

    def validate_name(self, value):
        from django.utils.html import strip_tags

        return strip_tags(value).strip()


ApiKeySerializer = ApiKeyReadSerializer


class ApiKeyCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200, min_length=1)
    expires_at = serializers.DateTimeField(required=False, allow_null=True)

    def validate_name(self, value):
        from django.utils.html import strip_tags

        return strip_tags(value).strip()


class ApiKeyCreatedSerializer(serializers.ModelSerializer):
    raw_key = serializers.CharField(read_only=True)

    class Meta:
        model = ApiKey
        fields = [
            "id",
            "name",
            "key_prefix",
            "raw_key",
            "revoked",
            "expires_at",
            "created_at",
        ]
        read_only_fields = fields
