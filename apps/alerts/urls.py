from django.urls import path

from . import views

urlpatterns = [
    path("", views.AlertListView.as_view(), name="alert_list"),
    path("bulk-resolve/", views.AlertBulkResolveView.as_view(), name="alert_bulk_resolve"),
    path("<uuid:pk>/", views.AlertDetailView.as_view(), name="alert_detail"),
    path("<uuid:pk>/resolve/", views.AlertResolveView.as_view(), name="alert_resolve"),
]
