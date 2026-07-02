from django.urls import path

from . import views

urlpatterns = [
    path("orgs/", views.SuperadminOrgListView.as_view(), name="superadmin_org_list"),
    path(
        "orgs/<uuid:pk>/",
        views.SuperadminOrgDetailView.as_view(),
        name="superadmin_org_detail",
    ),
    path("users/", views.SuperadminUserListView.as_view(), name="superadmin_user_list"),
    path(
        "users/<uuid:pk>/",
        views.SuperadminUserDetailView.as_view(),
        name="superadmin_user_detail",
    ),
    path("plans/", views.SuperadminPlanListView.as_view(), name="superadmin_plan_list"),
    path("stats/", views.SuperadminStatsView.as_view(), name="superadmin_stats"),
    path("refunds/", views.SuperadminRefundListView.as_view(), name="superadmin_refunds"),
    path(
        "refunds/initiate/",
        views.SuperadminRefundInitiateView.as_view(),
        name="superadmin_refund_initiate",
    ),
    path(
        "signatures/", views.SuperadminSignatureListView.as_view(), name="superadmin_signature_list"
    ),
    path(
        "signatures/<uuid:pk>/",
        views.SuperadminSignatureDetailView.as_view(),
        name="superadmin_signature_detail",
    ),
]
