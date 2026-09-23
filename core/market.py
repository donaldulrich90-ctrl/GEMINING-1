"""Taux de change et prix de l'or — porté depuis app.py.

Cache mémoire simple (TTL) + valeurs de repli si pas d'accès Internet.
"""
import time
from datetime import datetime

try:
    import requests
except Exception:  # requests absent → uniquement les valeurs de repli
    requests = None

_CACHE = {}


def _cached(key, ttl, producer):
    now = time.time()
    hit = _CACHE.get(key)
    if hit and now - hit[0] < ttl:
        return hit[1]
    val = producer()
    _CACHE[key] = (now, val)
    return val


# Repli hors-ligne : taux approximatifs 1 USD = X (mis à jour au besoin).
_FALLBACK_ALL = {
    "USD": 1.0, "EUR": 0.92, "XOF": 610.0, "GBP": 0.79, "CAD": 1.36, "AUD": 1.52,
    "CHF": 0.88, "CNY": 7.24, "JPY": 156.0, "INR": 83.3, "NGN": 1480.0, "GHS": 15.3,
    "ZAR": 18.2, "MAD": 9.9, "DZD": 134.0, "TND": 3.13, "EGP": 48.0, "KES": 129.0,
    "AED": 3.67, "SAR": 3.75, "BRL": 5.4, "RUB": 92.0, "TRY": 34.0, "MXN": 18.0,
    "XAF": 610.0, "SEK": 10.6, "NOK": 10.8, "DKK": 6.9, "SGD": 1.34, "HKD": 7.8,
    "KRW": 1370.0, "GNF": 8600.0, "MLI": 610.0, "SLL": 22000.0, "LRD": 190.0,
}

# Noms lisibles pour les devises les plus courantes (le reste : code seul).
CURRENCY_NAMES = {
    "USD": "Dollar US", "EUR": "Euro", "XOF": "Franc CFA (UEMOA)",
    "XAF": "Franc CFA (CEMAC)", "GBP": "Livre sterling", "CAD": "Dollar canadien",
    "AUD": "Dollar australien", "CHF": "Franc suisse", "CNY": "Yuan chinois",
    "JPY": "Yen japonais", "INR": "Roupie indienne", "NGN": "Naira nigérian",
    "GHS": "Cedi ghanéen", "ZAR": "Rand sud-africain", "MAD": "Dirham marocain",
    "DZD": "Dinar algérien", "TND": "Dinar tunisien", "EGP": "Livre égyptienne",
    "KES": "Shilling kényan", "AED": "Dirham EAU", "SAR": "Riyal saoudien",
    "BRL": "Réal brésilien", "RUB": "Rouble russe", "TRY": "Livre turque",
    "MXN": "Peso mexicain", "SEK": "Couronne suédoise", "NOK": "Couronne norvégienne",
    "DKK": "Couronne danoise", "SGD": "Dollar de Singapour", "HKD": "Dollar de Hong Kong",
    "KRW": "Won sud-coréen", "GNF": "Franc guinéen",
}


def _fetch_all_rates():
    """Toutes les devises (1 USD = X). Ajoute l'alias CFA = XOF."""
    if requests is not None:
        try:
            r = requests.get("https://open.er-api.com/v6/latest/USD", timeout=6)
            data = r.json()
            if data.get("result") == "success" and isinstance(data.get("rates"), dict):
                rates = {k: float(v) for k, v in data["rates"].items()
                         if isinstance(v, (int, float))}
                rates["USD"] = 1.0
                rates.setdefault("XOF", 610.0)
                rates["CFA"] = rates["XOF"]  # alias pratique
                return rates
        except Exception:
            pass
    out = dict(_FALLBACK_ALL)
    out["CFA"] = out["XOF"]
    return out


def get_all_rates():
    """Dictionnaire complet {code_devise: taux pour 1 USD}. En cache 15 min."""
    return _cached("rates_all", 900, _fetch_all_rates)


def get_exchange_rates():
    """Sous-ensemble USD/EUR/CFA (compatibilité). Repli : 1 USD = 0,92 EUR = 610 CFA."""
    allr = get_all_rates()
    return {"USD": 1.0, "EUR": allr.get("EUR", 0.92), "CFA": allr.get("CFA", allr.get("XOF", 610.0))}


def _fetch_gold():
    if requests is not None:
        try:
            r = requests.get("https://api.metals.live/v1/spot/gold", timeout=5)
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, dict) and "price" in data:
                    return {"price_per_ounce_usd": float(data["price"]), "currency": "USD",
                            "unit": "once troy", "timestamp": datetime.now()}
        except Exception:
            pass
    return {"price_per_ounce_usd": 2000.0, "currency": "USD", "unit": "once troy", "timestamp": datetime.now()}


def get_gold_price():
    return _cached("gold", 300, _fetch_gold)
