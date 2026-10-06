"""ADAPTATEUR MINE (GEMINING-1) — connexion unique (SSO) depuis le portail.

Route GET /sso/?token=... (publique pour le middleware, voir _PUBLIC_PREFIXES) :
  - vérifie le jeton signé par le portail (secret PARTAGÉ SSO_SHARED_SECRET),
  - contrôle qu'il est destiné à "mine" et qu'il n'a jamais servi (usage
    unique, partagé entre les workers gunicorn),
  - charge le compte depuis le gestionnaire d'utilisateurs de la Mine et
    vérifie qu'il appartient bien au tenant du jeton (jamais de compte
    plateforme « Gestionnaire » via le portail),
  - ouvre une session neuve (ge_user, ge_tenant) comme login_view,
  - mémorise la config de la barre de bascule (ge_switchbar),
  - redirige vers le tableau de bord.

L'ancienne page /login/ reste disponible comme secours.
"""
import os
import tempfile
import time

import jwt
from django.core.cache.backends.filebased import FileBasedCache
from django.http import HttpResponseForbidden
from django.shortcuts import redirect
from django.urls import reverse

from core import storage
from core.auth import get_user_manager

SSO_SHARED_SECRET = os.environ.get("SSO_SHARED_SECRET", "")

# Anti-rejeu : cache fichier partagé par les 3 workers gunicorn du conteneur
# (le cache mémoire par défaut de Django est propre à chaque worker).
_JTI_CACHE = FileBasedCache(
    os.path.join(tempfile.gettempdir(), "ge_sso_jti"),
    {"TIMEOUT": 300, "OPTIONS": {"MAX_ENTRIES": 5000}},
)


def sso_login(request):
    token = request.GET.get("token", "")
    if not token:
        return _refus("jeton manquant.")
    if not SSO_SHARED_SECRET:
        return _refus("SSO non configuré (SSO_SHARED_SECRET).")

    try:
        payload = jwt.decode(
            token, SSO_SHARED_SECRET, algorithms=["HS256"],
            audience="mine", issuer="portail-ge",
            options={"require": ["exp", "aud", "iss", "jti", "sub"]},
        )
    except jwt.PyJWTError:
        return _refus("jeton invalide ou expiré.")

    jti = str(payload.get("jti") or "")
    ttl = max(1, int(payload.get("exp", 0) - time.time()) + 5)
    # add() échoue si la clé existe déjà : usage unique.
    if not jti or not _JTI_CACHE.add(f"ge_sso_jti_{jti}", 1, ttl):
        return _refus("jeton déjà utilisé.")

    username = str(payload.get("sub") or "").strip()
    ent = str(payload.get("ent") or "").strip()
    if not username or not ent:
        return _refus("jeton incomplet.")
    tenant = storage.safe_tenant_id(ent)

    user = get_user_manager().get_user(username)
    if not user:
        return _refus("compte Mine introuvable.")
    if user.get("role") == "Gestionnaire":
        return _refus("compte plateforme non autorisé via le portail.")
    if storage.safe_tenant_id(user.get("tenant_id") or "default") != tenant:
        return _refus("ce compte n'appartient pas à cette entreprise dans Mine.")

    # Session neuve (évite de garder l'état d'une session précédente).
    request.session.flush()
    request.session["ge_user"] = user
    request.session["ge_tenant"] = tenant

    # Config de la barre de bascule (lue par base.html).
    mods = [m for m in (payload.get("mods") or []) if m in ("forage", "mine")]
    request.session["ge_switchbar"] = {
        "portal": str(payload.get("portal") or ""),
        "current": "mine",
        "modules": mods or ["mine"],
        "enterprise": storage.tenant_name(tenant),
    }
    return redirect(reverse("dashboard"))


def _refus(message):
    resp = HttpResponseForbidden(f"SSO refusé : {message}", content_type="text/plain; charset=utf-8")
    resp["Cache-Control"] = "no-store"
    return resp
