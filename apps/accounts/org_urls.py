from django.urls import path

from . import views

urlpatterns = [
    path("settings/", views.OrgSettingsView.as_view(), name="org_settings"),
]
