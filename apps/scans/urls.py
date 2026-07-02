from django.urls import path

from . import views

urlpatterns = [
    path("scan/public/", views.PublicScanView.as_view(), name="public_scan"),
    path("scan/<uuid:pk>/status/", views.ScanStatusView.as_view(), name="scan_status"),
    path(
        "scan/public/<uuid:pk>/",
        views.PublicScanDetailView.as_view(),
        name="public_scan_detail",
    ),
    path("scan/", views.ScanListView.as_view(), name="scan_list"),
    path("scan/<uuid:pk>/", views.ScanDetailView.as_view(), name="scan_detail"),
    path("scan/<uuid:pk>/rescan/", views.ScanRescanView.as_view(), name="scan_rescan"),
    path("scan/<uuid:pk>/report/pdf/", views.ScanPDFView.as_view(), name="scan_pdf"),
]
