"""Santé & sécurité au travail (SST) — porté depuis app.py.

Deux jeux de données persistés dans tenant_data/<tid>/collaboration/ (mêmes
fichiers que l'ancienne app → données reprises) :
  - sst_records.json      : fiches SST (incidents, near-miss, Take 5, inspections…)
  - sst_driver_checks.json: contrôles conducteurs (inspection véhicule, Take 5, frein)
"""
import json
import os
import uuid
from datetime import date, datetime, timedelta

from . import storage

TYPES = [
    "Take 5 — contrôle avant tâche",
    "JHA — analyse des dangers du travail",
    "PTO / Inspection véhicule",
    "Inspection SST",
    "Incident / accident",
    "Presqu'accident (near miss)",
    "Formation / sensibilisation",
    "Arrêt sécurité",
    "Autre",
]
GRAVITES = ["Faible", "Moyenne", "Élevée", "Critique"]


def _collab_dir(tid):
    d = os.path.join(storage.tenant_dir(tid), "collaboration")
    os.makedirs(d, exist_ok=True)
    return d


def _load(tid, name, key):
    p = os.path.join(_collab_dir(tid), name)
    if not os.path.isfile(p):
        return {key: []}
    try:
        with open(p, "r", encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) and key in d else {key: []}
    except (OSError, ValueError):
        return {key: []}


def _save(tid, name, data):
    p = os.path.join(_collab_dir(tid), name)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# --- Fiches SST ------------------------------------------------------------
def load_entries(tid):
    return _load(tid, "sst_records.json", "entries")["entries"]


def add_entry(tid, type_, date_iso, lieu, gravite, description, auteur):
    data = _load(tid, "sst_records.json", "entries")
    data["entries"].insert(0, {
        "id": uuid.uuid4().hex, "ts": datetime.now().isoformat(),
        "type": type_, "date": date_iso, "lieu": lieu, "gravite": gravite,
        "description": description, "auteur": auteur,
    })
    _save(tid, "sst_records.json", data)


# --- Contrôles conducteurs -------------------------------------------------
def load_checks(tid):
    return _load(tid, "sst_driver_checks.json", "records")["records"]


def add_check(tid, conducteur, matricule, vehicule, insp, take5, frein, notes, date_iso, reporter):
    data = _load(tid, "sst_driver_checks.json", "records")
    data["records"].insert(0, {
        "id": uuid.uuid4().hex, "ts": datetime.now().isoformat(), "date_controle": date_iso,
        "matricule": matricule, "conducteur_nom": conducteur, "vehicule": vehicule,
        "inspection_vehicule": bool(insp), "take5": bool(take5), "test_frein": bool(frein),
        "notes": notes, "reporter": reporter,
    })
    _save(tid, "sst_driver_checks.json", data)


def checks_summary(records):
    """Agrégat par conducteur : passages + comptes par type de contrôle."""
    agg = {}
    for r in records:
        nom = r.get("conducteur_nom") or "—"
        a = agg.setdefault(nom, {"conducteur": nom, "passages": 0, "insp": 0, "take5": 0, "frein": 0})
        a["passages"] += 1
        a["insp"] += 1 if r.get("inspection_vehicule") else 0
        a["take5"] += 1 if r.get("take5") else 0
        a["frein"] += 1 if r.get("test_frein") else 0
    return sorted(agg.values(), key=lambda x: x["passages"], reverse=True)


def count_recent(items, date_keys, ndays):
    if ndays is None:
        return len(items)
    cutoff = date.today() - timedelta(days=ndays)
    n = 0
    for e in items:
        raw = None
        for k in date_keys:
            if e.get(k):
                raw = str(e.get(k))[:10]
                break
        if not raw:
            continue
        try:
            if date.fromisoformat(raw) >= cutoff:
                n += 1
        except ValueError:
            continue
    return n
