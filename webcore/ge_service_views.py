"""ADAPTATEUR MINE (GEMINING-1) — API de service pour le portail.

Routes publiques pour le middleware (préfixe /api/service dans
_PUBLIC_PREFIXES) ; la sécurité est assurée par la clé de service
SERVICE_API_KEY (en-tête X-Service-Key) :

  GET  /api/service/metrics/?tenant=..&start=YYYY-MM-DD&end=YYYY-MM-DD
       -> métriques mine de l'entreprise sur la période (réutilise
          core.engineering.get_period_report).
  POST /api/service/module-state/   { tenant, active }
       -> active / désactive le tenant (case « module Mine » du portail).
  POST /api/service/user/           { tenant, username, password, role }
       -> crée le compte, ou le met à jour s'il appartient DÉJÀ à ce tenant.
          Un identifiant pris par un autre tenant ou par le compte plateforme
          est refusé (409) : jamais d'écrasement. Rôle « Gestionnaire » interdit.
"""
import hmac
import json
import logging
import os

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from core import storage
from core.auth import DEFAULT_PERMISSIONS, get_user_manager
from core.engineering import get_period_report

log = logging.getLogger(__name__)

SERVICE_API_KEY = os.environ.get("SERVICE_API_KEY", "")

# Rôles qu'un client peut recevoir (le rôle plateforme est exclu).
ROLES_CLIENT = [r for r in DEFAULT_PERMISSIONS if r != "Gestionnaire"]


def _cle_ok(request):
    given = request.headers.get("X-Service-Key", "")
    return bool(SERVICE_API_KEY) and hmac.compare_digest(given.encode(), SERVICE_API_KEY.encode())


def _tenant_existe(tenant):
    return tenant == "default" or tenant in storage.get_tenants_registry()


def _inconnu(tenant):
    return JsonResponse({"error": f"Tenant Mine « {tenant} » introuvable"}, status=404)


def plan(request):
    """Plan de planification + réel par date (tonnes) pour le suivi consolidé portail."""
    if not _cle_ok(request):
        return JsonResponse({"error": "Clé de service invalide"}, status=401)
    tenant = storage.safe_tenant_id(request.GET.get("tenant") or "default")
    if not _tenant_existe(tenant):
        return _inconnu(tenant)
    plan_data = storage.load_tenant_json(tenant, "planification", None)
    actuals = {}
    if plan_data:
        try:
            from core.db import get_connection
            with get_connection(tenant) as conn:
                cur = conn.execute(
                    "SELECT entry_date, COALESCE(SUM(production_tonnes),0) AS t "
                    "FROM manual_entries GROUP BY entry_date"
                )
                for row in cur.fetchall():
                    d = str(row["entry_date"] or "")[:10]
                    if d:
                        actuals[d] = actuals.get(d, 0) + (row["t"] or 0)
        except Exception:  # noqa: BLE001
            actuals = {}
    return JsonResponse({"module": "mine", "plan": plan_data, "actualsByDate": actuals})


def metrics(request):
    if not _cle_ok(request):
        return JsonResponse({"error": "Clé de service invalide"}, status=401)
    tenant = storage.safe_tenant_id(request.GET.get("tenant") or "default")
    start = request.GET.get("start", "")
    end = request.GET.get("end", "")
    if not start or not end:
        return JsonResponse({"error": "start et end requis"}, status=400)
    if not _tenant_existe(tenant):
        # Sinon get_connection créerait une base vide pour un tenant mal saisi.
        return _inconnu(tenant)

    try:
        rows, tot = get_period_report(tenant, start, end)
    except Exception as e:  # noqa: BLE001
        log.exception("metrics Mine KO pour %s", tenant)
        return JsonResponse({"error": f"lecture des données impossible : {e}"}, status=500)

    # Arrêts (incidents de shift) et maintenance sur la période.
    arrets_h_par_engin = {}
    arrets_par_motif = {}
    arrets_detail = []
    maintenance = []
    try:
        from core.db import get_connection
        with get_connection(tenant) as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT machine_id, incident_type, COALESCE(SUM(duration_hours),0) h, COUNT(*) n "
                "FROM shift_incidents WHERE entry_date >= ? AND entry_date <= ? "
                "GROUP BY machine_id, incident_type", (start, end))
            for r in cur.fetchall():
                d = dict(r)
                eng = d.get("machine_id")
                motif = d.get("incident_type") or "Autre"
                h = round(d.get("h") or 0, 1)
                arrets_h_par_engin[eng] = round(arrets_h_par_engin.get(eng, 0) + h, 1)
                m = arrets_par_motif.setdefault(motif, {"motif": motif, "heures": 0, "count": 0})
                m["heures"] = round(m["heures"] + h, 1)
                m["count"] += int(d.get("n") or 0)
            cur.execute(
                "SELECT machine_id, entry_date, shift, incident_type, duration_hours, "
                "production_impact, measures_next_shift FROM shift_incidents "
                "WHERE entry_date >= ? AND entry_date <= ? ORDER BY entry_date DESC LIMIT 200",
                (start, end))
            for r in cur.fetchall():
                d = dict(r)
                arrets_detail.append({
                    "engin": d.get("machine_id"), "date": d.get("entry_date"),
                    "shift": d.get("shift"), "motif": d.get("incident_type") or "Autre",
                    "heures": round(d.get("duration_hours") or 0, 1),
                    "impact": d.get("production_impact") or "",
                    "mesures": d.get("measures_next_shift") or "",
                })
            cur.execute(
                "SELECT machine_id, date_maintenance, maintenance_type, mechanic_name, notes "
                "FROM maintenance_logs WHERE date_maintenance >= ? AND date_maintenance <= ? "
                "ORDER BY date_maintenance DESC LIMIT 200", (start, end))
            for r in cur.fetchall():
                d = dict(r)
                maintenance.append({
                    "engin": d.get("machine_id"), "date": d.get("date_maintenance"),
                    "type": d.get("maintenance_type") or "", "technician": d.get("mechanic_name") or "",
                    "description": d.get("notes") or "",
                })
    except Exception:  # noqa: BLE001
        log.exception("metrics Mine — arrêts/maintenance KO pour %s", tenant)

    par_engin = [{
        "engin": r.get("machine_id"),
        "production": round(r.get("prod", 0), 1),
        "heures": round(r.get("h", 0), 1),
        "carburant": round(r.get("fuel", 0), 1),
        "cycles": int(r.get("cyc", 0)),
        "tph": r.get("tph", 0),
        "lpt": r.get("lpt", 0),
        "arrets_h": arrets_h_par_engin.get(r.get("machine_id"), 0),
    } for r in rows]

    # Effectif actif, lu directement dans staff.json. On n'instancie pas
    # StaffManager : sans fichier, il créerait du personnel de démonstration
    # chez le client (un rapport ne doit rien écrire).
    effectif = 0
    try:
        raw = storage.load_tenant_json(tenant, "staff.json", None) or []
        effectif = sum(1 for d in raw if isinstance(d, dict) and d.get("statut") == "Actif")
    except Exception:  # noqa: BLE001
        pass

    return JsonResponse({
        "module": "mine",
        "periode": {"start": start, "end": end},
        "par_engin": par_engin,
        "production_total": tot.get("prod", 0),
        "carburant_litres": tot.get("fuel", 0),
        "arrets_h_total": round(sum(arrets_h_par_engin.values()), 1),
        "arrets_par_motif": sorted(arrets_par_motif.values(), key=lambda x: -x["heures"]),
        "arrets_detail": arrets_detail,
        "maintenance": maintenance,
        # Le coût d'exploitation détaillé vit dans le module finance ; on le
        # laisse à 0 ici pour rester léger (à relier plus tard si besoin).
        "cout_total": 0,
        "effectif": effectif,
    })


def _json_body(request):
    try:
        body = json.loads(request.body or b"{}")
    except ValueError:
        return None
    return body if isinstance(body, dict) else None


@csrf_exempt
def module_state(request):
    if not _cle_ok(request):
        return JsonResponse({"error": "Clé de service invalide"}, status=401)
    if request.method != "POST":
        return JsonResponse({"error": "POST requis"}, status=405)
    body = _json_body(request)
    if body is None:
        return JsonResponse({"error": "JSON invalide"}, status=400)

    tenant = storage.safe_tenant_id(body.get("tenant") or "") if body.get("tenant") else ""
    active = bool(body.get("active"))
    if not tenant:
        return JsonResponse({"error": "tenant requis"}, status=400)
    if not _tenant_existe(tenant):
        return _inconnu(tenant)

    storage.set_tenant_active(tenant, active)
    return JsonResponse({"ok": True, "tenant": tenant, "active": active})


@csrf_exempt
def create_enterprise(request):
    """Crée (ou retrouve) le tenant d'une entreprise Mine, piloté par le portail."""
    if not _cle_ok(request):
        return JsonResponse({"error": "Clé de service invalide"}, status=401)
    if request.method != "POST":
        return JsonResponse({"error": "POST requis"}, status=405)
    body = _json_body(request)
    if body is None:
        return JsonResponse({"error": "JSON invalide"}, status=400)

    name = str(body.get("name") or "").strip()
    if not name:
        return JsonResponse({"error": "name requis"}, status=400)
    tenant = body.get("tenant") or ""
    tid = (storage.safe_tenant_id(tenant) if tenant
           else storage.safe_tenant_id(storage.slugify_tenant_name(name)))
    plan = body.get("plan") or "standard"

    if _tenant_existe(tid):
        return JsonResponse({"ok": True, "existing": True, "tenant": tid})
    cree = storage.create_tenant(name, tid=tid, plan=plan)
    if not cree:
        return JsonResponse({"error": f"Création tenant impossible ({tid})"}, status=500)
    return JsonResponse({"ok": True, "created": True, "tenant": cree})


@csrf_exempt
def create_user(request):
    """Crée (ou met à jour) un compte Mine, piloté par le portail."""
    if not _cle_ok(request):
        return JsonResponse({"error": "Clé de service invalide"}, status=401)
    if request.method != "POST":
        return JsonResponse({"error": "POST requis"}, status=405)
    body = _json_body(request)
    if body is None:
        return JsonResponse({"error": "JSON invalide"}, status=400)

    username = str(body.get("username") or "").strip()
    password = str(body.get("password") or "")
    role = str(body.get("role") or "Invite").strip()
    if not body.get("tenant"):
        return JsonResponse({"error": "tenant requis"}, status=400)
    tenant = storage.safe_tenant_id(body.get("tenant"))
    if not username or not password:
        return JsonResponse({"error": "username et password requis"}, status=400)
    if role not in ROLES_CLIENT:
        return JsonResponse({"error": f"Rôle Mine non autorisé : « {role} ». "
                                      f"Rôles possibles : {', '.join(ROLES_CLIENT)}"}, status=400)
    if not _tenant_existe(tenant):
        return _inconnu(tenant)

    mgr = get_user_manager()
    existant = mgr.get_user(username)
    if existant:
        autre_tenant = storage.safe_tenant_id(existant.get("tenant_id") or "default") != tenant
        if existant.get("role") == "Gestionnaire" or autre_tenant:
            return JsonResponse({"error": f"L'identifiant « {username} » est déjà utilisé dans Mine "
                                          f"par un autre compte. Choisis un autre identifiant."}, status=409)
        # Rôle inchangé -> on ne réinitialise pas les permissions personnalisées.
        nouveau_role = role if role != existant.get("role") else None
        mgr.update_user(username, password=password, role=nouveau_role)
        return JsonResponse({"ok": True, "updated": True, "username": username})

    mgr.add_user(username, password, role, tenant_id=tenant)
    return JsonResponse({"ok": True, "created": True, "username": username})
