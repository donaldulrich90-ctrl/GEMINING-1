"""Contexte partagé par tous les templates : navigation, taux, alertes, identité."""
import json

from django.utils.safestring import mark_safe

from core import storage
from core.permissions import authorized_tabs


# Devises courantes affichées en tête de liste du convertisseur.
_COMMON_CCY = ["USD", "EUR", "CFA", "XOF", "XAF", "GBP", "CAD", "CNY", "GNF", "GHS", "NGN"]


def navigation(request):
    user = getattr(request, "ge_user", None)
    if not user:
        return {}
    tabs = authorized_tabs(user)
    current_slug = request.resolver_match.kwargs.get("slug") if request.resolver_match else None
    if request.resolver_match and request.resolver_match.url_name == "dashboard":
        current_slug = "dashboard"
    tid = getattr(request, "ge_tenant", "default")
    me = user.get("user", "")
    role = user.get("role", "")

    marquee = []
    unread = 0
    if tid != "__platform__":
        try:
            from core.messaging import get_marquee, unread_count
            marquee = get_marquee(tid)
            unread = unread_count(tid, me)
        except Exception:
            pass
    if not marquee:
        marquee = ["Centre de contrôle GOOD ENGINEERS — Production • Sécurité • Performance"]

    # Expressions de besoin ouvertes (badge de navigation)
    besoins_open = 0
    if tid != "__platform__":
        try:
            besoins_open = sum(
                1 for b in (storage.load_tenant_json(tid, "besoins", []) or [])
                if b.get("statut") not in ("valide", "rejete")
            )
        except Exception:
            besoins_open = 0

    # Taux de change (toutes devises) + prix de l'or « live » — en cache 15/5 min.
    rates = {"CFA": 610.0, "EUR": 0.92}
    all_rates = {"USD": 1.0, "EUR": 0.92, "CFA": 610.0, "XOF": 610.0}
    names = {}
    gold_oz = 2000.0
    try:
        from core.market import get_exchange_rates, get_gold_price, get_all_rates, CURRENCY_NAMES
        rates = get_exchange_rates()
        all_rates = get_all_rates()
        names = CURRENCY_NAMES
        gold_oz = get_gold_price().get("price_per_ounce_usd", 2000.0)
    except Exception:
        pass
    gold_gram_usd = gold_oz / 31.1035

    # Options du convertisseur : courantes d'abord, puis le reste alphabétique.
    codes = [c for c in all_rates.keys() if c != "CFA"]  # CFA = alias de XOF
    common = [c for c in _COMMON_CCY if c in all_rates and c != "CFA"]
    rest = sorted(c for c in codes if c not in common)
    options = []
    seen = set()
    for c in common + rest:
        if c in seen:
            continue
        seen.add(c)
        label = names.get(c, "")
        options.append({"code": c, "label": f"{c} — {label}" if label else c})

    is_admin = bool(user.get("permissions", {}).get("admin"))

    return {
        "nav_tabs": tabs,
        "besoins_open": besoins_open,
        "current_slug": current_slug,
        "ge_username": me,
        "ge_role": role,
        "ge_tenant_id": tid,
        "ge_tenant_name": storage.tenant_name(tid),
        "ge_marquee": marquee,
        "ge_rates": rates,
        "ge_rates_all_json": mark_safe(json.dumps(all_rates)),
        "ge_ccy_options": options,
        "ge_unread": unread,
        "ge_gold_oz_usd": round(gold_oz, 2),
        "ge_gold_oz_cfa": round(gold_oz * rates.get("CFA", 610.0)),
        "ge_gold_gram_cfa": round(gold_gram_usd * rates.get("CFA", 610.0)),
        "ge_is_admin": is_admin,
        # « administrateur général du compte client » = rôle Administrateur.
        "ge_is_general_admin": (role == "Administrateur"),
    }
