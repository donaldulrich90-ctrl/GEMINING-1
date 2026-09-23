from django.urls import path
from django.views.generic import RedirectView

from webcore import views

urlpatterns = [
    path("", RedirectView.as_view(pattern_name="dashboard", permanent=False)),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("console/", views.console_view, name="console"),
    path("assistant/ask/", views.assistant_ask, name="assistant_ask"),
    path("assistant/teach/", views.assistant_teach, name="assistant_teach"),
    path("notifications/", views.notifications_view, name="notifications"),
    path("app/finance/invoice/<str:cid>/", views.invoice_view, name="invoice"),
    path("app/finance/facture-mensuelle/", views.facture_mensuelle_view, name="facture_mensuelle"),
    path("app/ingenierie/rapport/", views.rapport_view, name="rapport"),
    path("app/<slug:slug>/", views.tab_view, name="tab"),
    path("app/dashboard/", views.dashboard_view, name="dashboard"),
]
