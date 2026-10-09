from django.urls import path
from django.views.generic import RedirectView

from webcore import views
from webcore import ge_sso_views, ge_service_views

urlpatterns = [
    path("", RedirectView.as_view(pattern_name="dashboard", permanent=False)),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),

    # Portail GOOD ENGINEERS : connexion unique et API de métriques.
    path("sso/", ge_sso_views.sso_login, name="sso"),
    path("api/service/metrics/", ge_service_views.metrics, name="svc_metrics"),
    path("api/service/plan/", ge_service_views.plan, name="svc_plan"),
    path("api/service/besoins/", ge_service_views.besoins, name="svc_besoins"),
    path("api/service/module-state/", ge_service_views.module_state, name="svc_module_state"),
    path("api/service/enterprise/", ge_service_views.create_enterprise, name="svc_create_enterprise"),
    path("api/service/user/", ge_service_views.create_user, name="svc_create_user"),
    path("console/", views.console_view, name="console"),
    path("assistant/ask/", views.assistant_ask, name="assistant_ask"),
    path("assistant/teach/", views.assistant_teach, name="assistant_teach"),
    path("notifications/", views.notifications_view, name="notifications"),
    path("app/finance/invoice/<str:cid>/", views.invoice_view, name="invoice"),
    path("app/finance/facture-mensuelle/", views.facture_mensuelle_view, name="facture_mensuelle"),
    path("app/ingenierie/rapport/", views.rapport_view, name="rapport"),
    path("app/besoins/file/<int:bid>/<int:idx>/", views.besoins_file_view, name="besoins_file"),
    path("app/<slug:slug>/", views.tab_view, name="tab"),
    path("app/dashboard/", views.dashboard_view, name="dashboard"),
]
