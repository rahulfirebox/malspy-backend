from django.urls import path

from . import views

urlpatterns = [
    path("", views.DomainListView.as_view(), name="domain_list"),
    path("<uuid:pk>/", views.DomainDetailView.as_view(), name="domain_detail"),
    path("<uuid:pk>/scan/", views.DomainScanView.as_view(), name="domain_scan"),
]
