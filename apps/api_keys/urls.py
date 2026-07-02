from django.urls import path

from . import views

urlpatterns = [
    path("", views.ApiKeyListView.as_view(), name="api-key-list"),
    path("<uuid:pk>/", views.ApiKeyDetailView.as_view(), name="api-key-detail"),
]
