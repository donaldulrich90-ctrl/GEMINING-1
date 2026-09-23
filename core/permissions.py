"""Onglets de navigation et permissions — porté depuis app.py.

Chaque onglet a une clé de permission (dans le dict `permissions` de
l'utilisateur), un libellé avec icône, et un slug d'URL. Les onglets
affichés sont calculés depuis les permissions du compte (modifiables par
l'admin), comme dans l'ancienne application.
"""

# (clé, libellé affiché, clé de permission, slug d'URL)
TABS = [
    ("DASHBOARD",            "📊 DASHBOARD",   "dashboard",            "dashboard"),
    ("CYCLES",               "🔄 CYCLES",      "cycles",               "cycles"),
    ("CARBURANT",            "⛽ CARBURANT",   "carburant",            "carburant"),
    ("MAINT.",               "🔧 MAINT.",      "maintenance",          "maintenance"),
    ("GESTION STOCK",        "📦 STOCK",       "stock",                "stock"),
    ("CARTE",                "🗺️ CARTE",       "carte",                "carte"),
    ("FINANCE",              "💰 FINANCE",     "finance",              "finance"),
    ("RH",                   "👥 RH",          "rh",                   "rh"),
    ("ADMIN",                "⚙️ ADMIN",       "admin",                "admin"),
    ("DONNÉES INGÉNIERIE",   "📐 ING.",        "donnees_ingenierie",   "ingenierie"),
    ("MESSAGERIE",           "💬 MESSAGERIE",  "messagerie",           "messagerie"),
    ("SST",                  "🦺 SST",         "sst",                  "sst"),
    ("MARCHÉ OR",            "🥇 OR",          None,                   "marche-or"),
    ("VALIDATION OPÉRATEUR", "✅ VALIDATION",  "validation_operateur", "validation"),
]

# Index rapides
TAB_BY_KEY = {t[0]: {"key": t[0], "label": t[1], "perm": t[2], "slug": t[3]} for t in TABS}
TAB_BY_SLUG = {t[3]: TAB_BY_KEY[t[0]] for t in TABS}


def authorized_tabs(user: dict):
    """Liste ordonnée des onglets visibles pour ce compte."""
    role = (user or {}).get("role", "Invite")
    perms = (user or {}).get("permissions", {}) or {}

    if role == "Operateur":
        return [TAB_BY_KEY["VALIDATION OPÉRATEUR"]]

    result = []
    for key, label, perm, slug in TABS:
        if key == "MARCHÉ OR":
            result.append(TAB_BY_KEY[key])          # toujours visible (hors opérateur)
        elif perm and perms.get(perm):
            result.append(TAB_BY_KEY[key])
    if not result:
        result = [TAB_BY_KEY["DASHBOARD"], TAB_BY_KEY["MARCHÉ OR"]]
    return result


def can_access(user: dict, slug: str) -> bool:
    tab = TAB_BY_SLUG.get(slug)
    if not tab:
        return False
    return any(t["slug"] == slug for t in authorized_tabs(user))
