from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from . import views

urlpatterns = [
    path("register/", views.RegisterView.as_view(), name="register"),
    path("login/", views.LoginView.as_view(), name="login"),
    path("logout/", views.LogoutView.as_view(), name="logout"),
    path("refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("me/", views.MeView.as_view(), name="me"),
    path("forgot-password/", views.ForgotPasswordView.as_view(), name="forgot_password"),
    path("reset-password/", views.ResetPasswordView.as_view(), name="reset_password"),
    path("verify-email/", views.VerifyEmailView.as_view(), name="verify_email"),
    path(
        "organization/members/",
        views.OrgMemberListView.as_view(),
        name="org_member_list",
    ),
    path(
        "organization/members/<uuid:pk>/",
        views.OrgMemberDetailView.as_view(),
        name="org_member_detail",
    ),
    path("gdpr-erase/", views.GdprEraseView.as_view(), name="gdpr_erase"),
]
