from django.urls import path

from .views import AgentAuthView, AgentReportView, AgentSignaturesView

urlpatterns = [
    path("auth/", AgentAuthView.as_view()),
    path("report/", AgentReportView.as_view()),
    path("signatures/", AgentSignaturesView.as_view()),
]
