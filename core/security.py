"""Hachage et normalisation des secrets — porté depuis app.py (Streamlit).

Identique à l'ancienne app : SHA-256 après normalisation NFKC, pour que les
mots de passe déjà stockés dans app_database.json restent valides.
"""
import hashlib
import unicodedata

# Tirets « spéciaux » remplacés par un tiret ASCII (copier-coller depuis Word, etc.)
_DASH_CHARS = (
    "‐", "‑", "‒", "–", "—",
    "−", "－", "­",
)


def normalize_login_secret(value) -> str:
    """Mot de passe identique même avec tirets spéciaux ou espaces superflus."""
    if value is None:
        return ""
    s = unicodedata.normalize("NFKC", str(value)).strip()
    for ch in _DASH_CHARS:
        s = s.replace(ch, "-")
    return s


def hash_password(raw_password: str) -> str:
    """SHA-256 du mot de passe normalisé (compatible avec l'ancienne base)."""
    normalized = normalize_login_secret(raw_password)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def is_hashed(value: str) -> bool:
    """True si la valeur ressemble à un hash SHA-256 (64 caractères hexa)."""
    v = (value or "").strip()
    return len(v) == 64 and all(c in "0123456789abcdef" for c in v.lower())
