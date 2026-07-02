from django.urls import path

from .views import DashboardAnalyticsView

urlpatterns = [
    path("", DashboardAnalyticsView.as_view(), name="scan_analytics"),
]
