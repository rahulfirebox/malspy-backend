import logging

from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from apps.accounts.services import consume_password_reset_token as confirm_password_reset
from apps.accounts.services import create_password_reset_token as request_password_reset
from apps.core.pagination import StandardCursorPagination
from apps.core.permissions import IsAdmin, RequiresOrg
from apps.core.throttling import (
    EmailVerifyThrottle,
    LoginRateThrottle,
    PasswordResetThrottle,
    RegistrationRateThrottle,
)

from . import services
from .serializers import (
    ForgotPasswordSerializer,
    LoginSerializer,
    OrgSettingsSerializer,
    RegisterSerializer,
    ResetPasswordSerializer,
    UserReadSerializer,
    UserUpdateSerializer,
    VerifyEmailSerializer,
)

logger = logging.getLogger(__name__)


class RegisterView(GenericAPIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [RegistrationRateThrottle]
    serializer_class = RegisterSerializer

    def post(self, request):
        ser = RegisterSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        user, org = services.register(ser.validated_data)
        return Response(
            {"user": UserReadSerializer(user).data},
            status=status.HTTP_201_CREATED,
        )


class LoginView(GenericAPIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [LoginRateThrottle]
    serializer_class = LoginSerializer

    def post(self, request):
        ser = LoginSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        tokens = services.login(
            email=ser.validated_data["email"],
            password=ser.validated_data["password"],
            request=request,
        )
        return Response(tokens)


class LogoutView(GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = None

    def post(self, request):
        refresh_token = request.data.get("refresh", "")
        services.logout(refresh_token)
        return Response({"detail": "Logged out successfully."})


class MeView(GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = UserReadSerializer

    def get(self, request):
        return Response(UserReadSerializer(request.user).data)

    def patch(self, request):
        ser = UserUpdateSerializer(request.user, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        user = services.update_profile(request.user, ser.validated_data)
        return Response(UserReadSerializer(user).data)


class ForgotPasswordView(GenericAPIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [PasswordResetThrottle]
    serializer_class = ForgotPasswordSerializer

    def post(self, request):
        ser = ForgotPasswordSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        raw_token = request_password_reset(ser.validated_data["email"])

        if raw_token:
            logger.info(
                "Password reset token created for email: %s",
                ser.validated_data["email"],
                extra={"email": ser.validated_data["email"]},
            )

        return Response({"detail": "If your email is registered, you will receive a reset link."})


class ResetPasswordView(GenericAPIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [PasswordResetThrottle]
    serializer_class = ResetPasswordSerializer

    def post(self, request):
        ser = ResetPasswordSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        confirm_password_reset(
            raw_token=ser.validated_data["token"],
            new_password=ser.validated_data["password"],
        )
        return Response({"detail": "Password updated successfully."})


class VerifyEmailView(GenericAPIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [EmailVerifyThrottle]
    serializer_class = VerifyEmailSerializer

    def post(self, request):
        ser = VerifyEmailSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        services.verify_email(ser.validated_data["token"])
        return Response({"detail": "Email verified successfully."})


class OrgMemberListView(GenericAPIView):
    permission_classes = [IsAuthenticated, RequiresOrg, IsAdmin]
    pagination_class = StandardCursorPagination
    serializer_class = UserReadSerializer

    def get(self, request):
        q = request.query_params.get("q")
        qs = services.list_org_members(request.user.organization, q=q)
        paginator = StandardCursorPagination()
        page = paginator.paginate_queryset(qs, request)
        ser = UserReadSerializer(page, many=True)
        return paginator.get_paginated_response(ser.data)

    def post(self, request):
        from .serializers import AddOrgMemberSerializer

        ser = AddOrgMemberSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        member = services.add_org_member(
            org=request.user.organization,
            email=ser.validated_data["email"],
            role=ser.validated_data["role"],
            requesting_user=request.user,
        )
        return Response(UserReadSerializer(member).data, status=status.HTTP_201_CREATED)


class OrgMemberDetailView(GenericAPIView):
    permission_classes = [IsAuthenticated, RequiresOrg, IsAdmin]
    serializer_class = None

    def delete(self, request, pk):
        services.remove_org_member(
            org=request.user.organization,
            member_id=pk,
            requesting_user=request.user,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class OrgSettingsView(GenericAPIView):
    permission_classes = [IsAuthenticated, RequiresOrg, IsAdmin]
    serializer_class = OrgSettingsSerializer

    def get(self, request):
        org = request.user.organization
        ser = OrgSettingsSerializer(org)
        return Response(ser.data)

    def patch(self, request):
        org = request.user.organization
        ser = OrgSettingsSerializer(org, data=request.data, partial=True)

        ser.is_valid(raise_exception=True)
        updated_org = services.update_org_settings(org, ser.validated_data, user=request.user)
        return Response(OrgSettingsSerializer(updated_org).data)


class GdprEraseView(GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = None

    def post(self, request):
        if not request.data.get("confirm"):
            raise ValidationError(
                {"confirm": ["You must send confirm=true to erase your account."]}
            )
        services.gdpr_erase_user(user=request.user, requesting_user=request.user)
        return Response({"detail": "Account data erased."}, status=status.HTTP_200_OK)
