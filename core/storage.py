"""Accès aux données partagées — porté depuis app.py (Streamlit).

Réutilise TELS QUELS les fichiers de l'ancienne application :
  - app_database.json   (utilisateurs, tenants, réglages, logos)
  - geo_data.db          (tenant « default »)
  - tenant_data/<tid>/geo_data.db  (autres entreprises)

Le dossier racine des données (DATA_ROOT) est configurable :
  - variable d'environnement GE_DATA_ROOT, sinon
  - le dossier parent du projet Django (là où vit l'ancienne app).
"""
import json
import os
import re
import shutil
import tempfile
from datetime import date, datetime

from django.conf import settings

APP_DB_FILE = "app_database.json"
LEGACY_DB_FILE = "geo_data.db"
TENANT_DATA_DIRNAME = "tenant_data"


def data_root() -> str:
    return str(settings.GE_DATA_ROOT)


def app_db_path() -> str:
    return os.path.join(data_root(), APP_DB_FILE)


def tenant_data_dir() -> str:
    d = os.path.join(data_root(), TENANT_DATA_DIRNAME)
    os.makedirs(d, exist_ok=True)
    return d


def safe_tenant_id(tid) -> str:
    """Nettoie un identifiant de tenant (évite les traversées de dossier)."""
    tid = str(tid or "default").strip()
    if not tid:
        return "default"
    tid = re.sub(r"[^A-Za-z0-9_\-]", "-", tid)
    return tid or "default"


def effective_db_path(tenant_id: str) -> str:
    """Fichier SQLite du tenant. Défaut = geo_data.db (racine, comme avant)."""
    tid = safe_tenant_id(tenant_id)
    if tid == "default":
        return os.path.abspath(os.path.join(data_root(), LEGACY_DB_FILE))
    d = os.path.join(tenant_data_dir(), tid)
    os.makedirs(d, exist_ok=True)
    return os.path.abspath(os.path.join(d, LEGACY_DB_FILE))


def tenant_dir(tenant_id: str) -> str:
    """Dossier de données du tenant (créé si absent). 'default' → tenant_data/default."""
    d = os.path.join(tenant_data_dir(), safe_tenant_id(tenant_id))
    os.makedirs(d, exist_ok=True)
    return d


def load_tenant_json(tenant_id: str, name: str, default):
    """Lit un fichier JSON du tenant (ex: staff.json, stock.json)."""
    path = os.path.join(tenant_dir(tenant_id), name)
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def save_tenant_json(tenant_id: str, name: str, data) -> None:
    """Écriture atomique d'un fichier JSON du tenant."""
    path = os.path.join(tenant_dir(tenant_id), name)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix="." + name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        shutil.move(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


# ---------------------------------------------------------------------------
# app_database.json
# ---------------------------------------------------------------------------
def _empty_database() -> dict:
    return {
        "images_metadata": {},
        "settings": {},
        "backup_info": {"last_backup": None, "backup_count": 0},
        "version": "1.0",
        "logo_metadata": {},
        "users_list": [],
        "tenants": {},
    }


def get_database() -> dict:
    path = app_db_path()
    if not os.path.exists(path):
        return _empty_database()
    # Deux tentatives : évite qu'une erreur transitoire de lecture n'entraîne,
    # via une réécriture ultérieure, la perte des tenants / réglages existants.
    import time
    last_err = None
    for attempt in range(2):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except (OSError, ValueError) as e:
            last_err = e
            time.sleep(0.15)
    # Fichier présent mais illisible : on sauvegarde une copie et on repart à vide.
    try:
        if last_err is not None and os.path.getsize(path) > 0:
            import shutil as _sh
            _sh.copy2(path, path + ".corrupt.bak")
    except OSError:
        pass
    return _empty_database()


def save_database(db: dict) -> None:
    """Écriture atomique (réduit les fichiers corrompus / logins impossibles)."""
    path = app_db_path()
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fd, tmp = tempfile.mkstemp(
        dir=os.path.dirname(path) or ".", prefix=".app_db_", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(db, f, ensure_ascii=False, indent=2)
        shutil.move(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


# ---------------------------------------------------------------------------
# Registre des entreprises (tenants)
# ---------------------------------------------------------------------------
def get_tenants_registry() -> dict:
    db = get_database()
    t = db.get("tenants")
    if isinstance(t, dict) and t:
        return t
    # Toujours au moins l'entreprise « default » (sans écriture pendant la lecture).
    return {"default": {"name": "Entreprise par défaut", "plan": "standard",
                        "subscription_end": "", "active": True}}


def get_tenant_record(tenant_id: str) -> dict:
    return get_tenants_registry().get(safe_tenant_id(tenant_id), {})


def tenant_name(tenant_id: str) -> str:
    rec = get_tenant_record(tenant_id)
    return rec.get("name") or safe_tenant_id(tenant_id)


def save_tenants_registry(tenants: dict) -> None:
    db = get_database()
    db["tenants"] = tenants
    save_database(db)


def slugify_tenant_name(name: str) -> str:
    s = "".join(c.lower() if c.isalnum() else "-" for c in (name or "").strip())
    parts = [x for x in s.split("-") if x]
    return "-".join(parts)[:48] if parts else "societe"


def set_tenant_active(tenant_id: str, active: bool) -> None:
    reg = get_tenants_registry().copy()
    tid = safe_tenant_id(tenant_id)
    if tid in reg:
        reg[tid]["active"] = bool(active)
        save_tenants_registry(reg)


def update_tenant(tenant_id: str, fields: dict) -> None:
    reg = get_tenants_registry().copy()
    tid = safe_tenant_id(tenant_id)
    if tid in reg:
        rec = dict(reg[tid])
        rec.update({k: v for k, v in fields.items() if v is not None})
        reg[tid] = rec
        save_tenants_registry(reg)


def create_tenant(name, tid=None, plan="standard", subscription_end="", **extra) -> str:
    """Crée l'entrée SaaS + initialise la base SQLite du tenant. Retourne l'id."""
    from .db import init_database_at_path
    tid = safe_tenant_id(tid) if tid else safe_tenant_id(slugify_tenant_name(name))
    reg = get_tenants_registry().copy()
    if tid == "default" or tid in reg:
        return ""
    reg[tid] = {"name": (name or "").strip(), "plan": plan,
                "subscription_end": subscription_end or "", "active": True,
                "address": extra.get("address", ""), "phone": extra.get("phone", ""),
                "email": extra.get("email", ""), "tax_id": extra.get("tax_id", ""),
                "rccm": extra.get("rccm", ""), "bank_info": extra.get("bank_info", "")}
    save_tenants_registry(reg)
    init_database_at_path(effective_db_path(tid))
    return tid


def delete_tenant_and_data(tenant_id: str, user_mgr) -> tuple:
    """Retire l'entreprise du registre, ses comptes (hors Gestionnaire) et son dossier."""
    tid = safe_tenant_id(tenant_id)
    if tid in ("default", "__platform__"):
        return False, "Identifiant réservé — suppression interdite."
    reg = get_tenants_registry().copy()
    if tid not in reg:
        return False, f"Aucune entreprise « {tid} »."
    removed = 0
    kept = []
    for u in user_mgr.users_db:
        if u.get("role") == "Gestionnaire":
            kept.append(u); continue
        if safe_tenant_id(u.get("tenant_id", "default")) == tid:
            removed += 1; continue
        kept.append(u)
    user_mgr.users_db = kept
    user_mgr.persist_users()
    del reg[tid]
    save_tenants_registry(reg)
    d = os.path.join(tenant_data_dir(), tid)
    if os.path.isdir(d):
        try:
            shutil.rmtree(d)
        except OSError as e:
            return True, f"Entreprise « {tid} » retirée ; {removed} compte(s) supprimé(s). Dossier : {e}"
    return True, f"Entreprise « {tid} » supprimée ; {removed} compte(s) retiré(s)."


def is_tenant_billing_ok(tenant_id: str) -> bool:
    """Compte actif et abonnement non expiré (défaut = actif)."""
    tid = safe_tenant_id(tenant_id)
    if tid == "default":
        return True
    rec = get_tenant_record(tid)
    if not rec:
        return True  # tenant inconnu → tolérant (comme l'ancienne app)
    if rec.get("active") is False:
        return False
    end = str(rec.get("subscription_end") or "").strip()
    if end:
        try:
            return datetime.strptime(end, "%Y-%m-%d").date() >= date.today()
        except ValueError:
            return True
    return True
