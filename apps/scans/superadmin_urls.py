from django.urls import path

from .views import SuperadminSignatureDetailView, SuperadminSignatureListView

urlpatterns = [
    path("signatures/", SuperadminSignatureListView.as_view()),
    path("signatures/<uuid:pk>/", SuperadminSignatureDetailView.as_view()),
]
