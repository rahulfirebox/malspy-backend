from django.urls import path

from .views import AgentDetailView, AgentListView, AgentScanListView

urlpatterns = [
    path("", AgentListView.as_view()),
    path("<uuid:pk>/", AgentDetailView.as_view()),
    path("<uuid:pk>/scans/", AgentScanListView.as_view()),
]
