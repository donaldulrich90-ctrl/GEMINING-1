"""Validation opérateur — chaîne chargement → déchargement (porté depuis app.py).

L'opérateur de chargement valide un chargement, ce qui crée une notification
pour les opérateurs de déchargement, qui l'acquittent (« Vous pouvez bouger »).
Persisté dans tenant_data/<tid>/operator_notifications.json.
"""
from datetime import datetime

from . import storage

MINERAL_TYPES = ["Minerai (ROM)", "Stérile (Waste)", "Haute teneur", "Basse teneur", "Latérite"]
GRADES = ["Haute", "Moyenne", "Basse", "N/A"]


def _load(tid):
    return storage.load_tenant_json(tid, "operator_notifications.json", [])


def _save(tid, data):
    storage.save_tenant_json(tid, "operator_notifications.json", data)


def load_notifications(tid):
    data = _load(tid)
    return data if isinstance(data, list) else []


def add_loading(tid, operator, truck, mineral_type, grade, destination=""):
    notifs = load_notifications(tid)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    notifs.append({
        "id": f"notif_{datetime.now().strftime('%Y%m%d%H%M%S')}_{truck}",
        "from_operator": operator, "to_operator": "all_dumpers", "truck": truck,
        "message": f"Chargement terminé pour {truck}. Vous pouvez bouger !",
        "mineral_type": mineral_type, "grade": grade, "destination": destination,
        "timestamp": ts, "status": "pending", "type": "loading_complete",
    })
    _save(tid, notifs)


def acknowledge(tid, notif_id, who=""):
    notifs = load_notifications(tid)
    for n in notifs:
        if n.get("id") == notif_id and n.get("status") == "pending":
            n["status"] = "acknowledged"
            n["acknowledged_by"] = who
            n["acknowledged_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            _save(tid, notifs)
            return True
    return False


def pending(tid):
    return [n for n in load_notifications(tid) if n.get("status") == "pending"]


def recent(tid, limit=50):
    return list(reversed(load_notifications(tid)))[:limit]
