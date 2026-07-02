from rest_framework import serializers

from .models import Organization, User

_ASSIGNABLE_ROLES = [
    c[0] for c in User._meta.get_field("role").choices if c[0] not in ("owner", "superadmin")
]


class OrganizationReadSerializer(serializers.ModelSerializer):
    plan = serializers.SerializerMethodField()
    scan_quota_limit = serializers.SerializerMethodField()

    class Meta:
        model = Organization
        fields = [
            "id",
            "name",
            "plan",
            "scan_quota_used",
            "scan_quota_limit",
            "quota_reset_at",
        ]
        read_only_fields = [
            "id",
            "name",
            "plan",
            "scan_quota_used",
            "scan_quota_limit",
            "quota_reset_at",
        ]

    def get_plan(self, obj):
        return obj.plan.slug if obj.plan else None

    def get_scan_quota_limit(self, obj):
        return obj.plan.scan_quota if obj.plan else 0


class OrganizationWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ["id", "name"]
        read_only_fields = ["id"]


OrganizationSerializer = OrganizationReadSerializer


class UserReadSerializer(serializers.ModelSerializer):
    organization = OrganizationReadSerializer(read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "name",
            "role",
            "organization",
            "is_email_verified",
            "notify_email",
            "timezone",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "email",
            "name",
            "role",
            "organization",
            "is_email_verified",
            "notify_email",
            "timezone",
            "created_at",
        ]


class UserWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "name", "notify_email", "timezone"]
        read_only_fields = ["id"]


UserSerializer = UserReadSerializer


class UserUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "name", "notify_email", "timezone"]
        read_only_fields = ["id"]


class OrgSettingsSerializer(serializers.ModelSerializer):
    plan_slug = serializers.CharField(source="plan.slug", read_only=True)
    plan_name = serializers.CharField(source="plan.name", read_only=True)
    scan_quota = serializers.IntegerField(source="plan.scan_quota", read_only=True)

    class Meta:
        model = Organization
        fields = [
            "id",
            "name",
            "slug",
            "plan_slug",
            "plan_name",
            "scan_quota",
            "scan_quota_used",
            "quota_reset_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "slug",
            "plan_slug",
            "plan_name",
            "scan_quota",
            "scan_quota_used",
            "quota_reset_at",
            "created_at",
            "updated_at",
        ]


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    name = serializers.CharField(max_length=200, min_length=1)
    password = serializers.CharField(min_length=8, write_only=True)
    org_name = serializers.CharField(max_length=200, required=False, allow_blank=True)
    organization_name = serializers.CharField(max_length=200, required=False, allow_blank=True)

    def validate_email(self, value):
        return value.strip().lower()

    def validate_password(self, value):
        if len(value) < 8:
            raise serializers.ValidationError(
                {"password": "Password must be at least 8 characters."}
            )
        return value


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate_email(self, value):
        return value.strip().lower()


class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        return value.strip().lower()


class ResetPasswordSerializer(serializers.Serializer):
    token = serializers.CharField()
    password = serializers.CharField(min_length=8, write_only=True)

    def validate_password(self, value):
        if len(value) < 8:
            raise serializers.ValidationError(
                {"password": "Password must be at least 8 characters."}
            )
        return value


class VerifyEmailSerializer(serializers.Serializer):
    token = serializers.CharField()


class AddOrgMemberSerializer(serializers.Serializer):
    email = serializers.EmailField()
    role = serializers.ChoiceField(choices=_ASSIGNABLE_ROLES)
