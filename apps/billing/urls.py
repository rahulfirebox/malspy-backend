from django.urls import path

from . import views

urlpatterns = [
    path("plans/", views.PlansListView.as_view(), name="billing_plans_list"),
    path("plan/", views.BillingPlanView.as_view(), name="billing_plan"),
    path("invoices/", views.InvoiceListView.as_view(), name="invoices"),
    path("upgrade/", views.UpgradePlanView.as_view(), name="upgrade_plan"),
    path("cancel/", views.CancelSubscriptionView.as_view(), name="billing_cancel"),
    path("webhook/stripe/", views.StripeWebhookView.as_view(), name="stripe_webhook"),
    path("create-order/", views.CreateOrderView.as_view(), name="create_order"),
    path("verify-payment/", views.VerifyPaymentView.as_view(), name="verify_payment"),
    path(
        "webhook/cashfree/",
        views.CashfreeWebhookView.as_view(),
        name="cashfree_webhook",
    ),
]
