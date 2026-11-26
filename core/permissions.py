"""Onglets de navigation et permissions — porté depuis app.py.

Chaque onglet a une clé de permission (dans le dict `permissions` de
l'utilisateur), un libellé avec icône, et un slug d'URL. Les onglets
affichés sont calculés depuis les permissions du compte (modifiables par
l'admin), comme dans l'ancienne application.
"""

# (clé, libellé affiché, clé de permission, slug d'URL)
TABS = [
    ("DASHBOARD",            "📊 DASHBOARD",   "dashboard",            "dashboard"),
    ("PLANIFICATION",        "🗓️ PLAN.",       "dashboard",            "planification"),
    ("EXPRESSION DE BESOIN", "📝 BESOINS",     "dashboard",            "besoins"),
    ("CYCLES",               "🔄 CYCLES",      "cycles",               "cycles"),
    ("EXPLOITATION SOUT.",   "⛏ SOUTERRAIN",  "cycles",               "souterrain"),
    ("CARRIÈRE",             "🏔 CARRIÈRE",    "cycles",               "carriere"),
    ("CARBURANT",            "⛽ CARBURANT",   "carburant",            "carburant"),
    ("MAINT.",               "🔧 MAINT.",      "maintenance",          "maintenance"),
    ("GESTION STOCK",        "📦 STOCK",       "stock",                "stock"),
    ("CARTE",                "🗺️ CARTE",       "carte",                "carte"),
    ("FINANCE",              "💰 FINANCE",     "finance",              "finance"),
    ("SOUS-TRAITANTS",       "⚒ S-TRAIT.",     "finance",              "soustraitants"),
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


# ---------------------------------------------------------------------------
# Type de mine — environnements cloisonnés par entreprise
# ---------------------------------------------------------------------------
# Chaque entreprise a un type de mine. Les onglets métier ci-dessous ne sont
# visibles que pour le type correspondant ; les autres onglets sont communs.
# Une entreprise « ciel ouvert » ne verra jamais le souterrain ni la carrière,
# et réciproquement.
MINE_TYPES = ("ciel_ouvert", "souterrain", "carriere")
MINE_TYPE_LABELS = {
    "ciel_ouvert": "Mine à ciel ouvert",
    "souterrain": "Mine souterraine",
    "carriere": "Carrière",
}
# slug d'onglet -> type de mine qui seul y a droit.
TYPE_SPECIFIC_SLUGS = {
    "cycles": "ciel_ouvert",     # cycles de production fosse (ciel ouvert)
    "souterrain": "souterrain",  # exploitation souterraine
    "carriere": "carriere",      # carrière de granulats
}


def normalize_mine_type(t):
    """Renvoie un type de mine valide, ou '' si inconnu / non typé."""
    t = (t or "").strip()
    return t if t in MINE_TYPES else ""


def authorized_tabs(user: dict, mine_type=None):
    """Liste ordonnée des onglets visibles pour ce compte.

    mine_type : type de mine de l'entreprise. Si fourni, les onglets réservés
    à un autre type sont masqués (cloisonnement des environnements). Si vide /
    non typé, aucun filtrage par type (rétro-compatibilité).
    """
    role = (user or {}).get("role", "Invite")
    perms = (user or {}).get("permissions", {}) or {}

    if role == "Operateur":
        return [TAB_BY_KEY["VALIDATION OPÉRATEUR"]]

    mt = normalize_mine_type(mine_type)
    result = []
    for key, label, perm, slug in TABS:
        req_type = TYPE_SPECIFIC_SLUGS.get(slug)
        if req_type and mt and req_type != mt:
            continue  # onglet d'un autre type de mine -> masqué
        if key == "MARCHÉ OR":
            result.append(TAB_BY_KEY[key])          # toujours visible (hors opérateur)
        elif perm and perms.get(perm):
            result.append(TAB_BY_KEY[key])
    if not result:
        result = [TAB_BY_KEY["DASHBOARD"], TAB_BY_KEY["MARCHÉ OR"]]
    return result


def can_access(user: dict, slug: str, mine_type=None) -> bool:
    tab = TAB_BY_SLUG.get(slug)
    if not tab:
        return False
    return any(t["slug"] == slug for t in authorized_tabs(user, mine_type))
