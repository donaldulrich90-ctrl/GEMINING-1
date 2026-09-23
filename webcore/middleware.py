"""Authentification par session + isolation multi-tenant.

Reproduit la logique de l'ancienne app :
  - non authentifié -> page de connexion
  - Gestionnaire (rôle plateforme) -> console plateforme (à venir)
  - sinon : tenant réel du compte, vérifié pour l'abonnement.
"""
from django.shortcuts import redirect
from django.urls import reverse

from core import storage

# Chemins accessibles sans authentification
_PUBLIC_PREFIXES = ("/login", "/static", "/favicon.ico")


class AuthTenantMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path

        # Contexte utilisateur depuis la session (cookie signé)
        request.ge_user = request.session.get("ge_user")
        request.ge_tenant = request.session.get("ge_tenant", "default")

        if any(path.startswith(p) for p in _PUBLIC_PREFIXES):
            return self.get_response(request)

        if not request.ge_user:
            return redirect(f"{reverse('login')}?next={path}")

        # Le Gestionnaire (plateforme) est dirigé vers sa console
        if request.ge_user.get("role") == "Gestionnaire" and not path.startswith("/console"):
            return redirect(reverse("console"))

        # Abonnement entreprise expiré / inactif
        tid = request.ge_tenant
        if tid not in ("__platform__",) and not storage.is_tenant_billing_ok(tid):
            request.ge_billing_blocked = True

        return self.get_response(request)
