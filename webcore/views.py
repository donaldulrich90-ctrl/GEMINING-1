"""Vues — connexion, déconnexion, dashboard, et onglets (à venir)."""
import json
from datetime import date

from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.safestring import mark_safe

from core.auth import get_user_manager
from core.fleet import FleetManager, statut_count, col_sum_int, col_mean
from core.permissions import TAB_BY_SLUG, authorized_tabs, can_access
from core import storage


# ---------------------------------------------------------------------------
# Authentification
# ---------------------------------------------------------------------------
def login_view(request):
    if request.session.get("ge_user"):
        return redirect("dashboard")

    error = None
    if request.method == "POST":
        username = request.POST.get("username", "")
        password = request.POST.get("password", "")
        user_mgr = get_user_manager()
        user = user_mgr.verify_login(username, password)
        if user:
            tid = user.get("tenant_id") or "default"
            # Le Gestionnaire reste sur la plateforme ; les autres sur leur tenant réel
            if user.get("role") != "Gestionnaire" and tid == "__platform__":
                tid = "default"
            request.session["ge_user"] = user
            request.session["ge_tenant"] = storage.safe_tenant_id(tid) if tid != "__platform__" else "__platform__"
            if user.get("role") == "Gestionnaire":
                return redirect("console")
            nxt = request.GET.get("next") or reverse("dashboard")
            return redirect(nxt)
        error = "Identifiant ou mot de passe incorrect"

    return render(request, "login.html", {"error": error})


def logout_view(request):
    request.session.flush()
    return redirect("login")


# ---------------------------------------------------------------------------
# Dashboard (module démo — données réelles)
# ---------------------------------------------------------------------------
def dashboard_view(request):
    user = request.ge_user
    if not can_access(user, "dashboard"):
        return _forbidden(request, "dashboard")

    tenant_id = request.ge_tenant if request.ge_tenant != "__platform__" else "default"
    manager = FleetManager(tenant_id)
    rows = manager.get_summary_rows()

    total_machines = len(rows)
    machines_actives = statut_count(rows, "Active")
    machines_pannes = statut_count(rows, "Panne")
    disponibilite = round(machines_actives / total_machines * 100, 1) if total_machines else 0
    production_totale = col_sum_int(rows, "Production (T)")
    cycles_totaux = col_sum_int(rows, "Cycles")
    total_heures = col_sum_int(rows, "H. Total")
    heures_jour = col_sum_int(rows, "H. Run Jour")
    revenu_jour = col_sum_int(rows, "Rev. Jour ($)")
    rentabilite_totale = col_sum_int(rows, "Rentabilité ($)")
    avg_cycle = col_mean(rows, "Tps Cycle Moy (min)")
    fuel_avg = col_mean(rows, "Carburant (%)") if rows else None

    idle_count = statut_count(rows, "Idle")

    # Maintenances planifiées : dérivées de next_maintenance (persisté en base)
    active_alerts = [
        {"machine_id": m.id,
         "maintenance_type": "Préventive" + (f" • {m.next_maintenance.strftime('%d/%m')}" if m.next_maintenance else "")}
        for m in manager.machines if m.next_maintenance
    ]
    nb_alertes = len(active_alerts)
    from core.stock import StockStore
    low_stock_items = StockStore(tenant_id).get_low_stock_items()
    nb_stock_bas = len(low_stock_items)

    # Données graphiques (Plotly côté client, mêmes couleurs qu'avant)
    status_counts = {}
    for r in rows:
        status_counts[r["Statut"]] = status_counts.get(r["Statut"], 0) + 1
    prod_sorted = sorted(rows, key=lambda r: r["Production (T)"], reverse=True)[:10]
    prod_chart = {
        "ids": [r["ID"] for r in prod_sorted],
        "values": [r["Production (T)"] for r in prod_sorted],
    }

    fleet_table = [
        {
            "id": r["ID"], "type": r["Type"], "statut": r["Statut"],
            "operateur": r["Opérateur"], "production": r["Production (T)"],
            "cycles": r["Cycles"], "h_jour": r["H. Run Jour"],
            "pm": r["Prochaine PM"], "carburant": r["Carburant (%)"],
        }
        for r in rows
    ]

    context = {
        "today_str": date.today().strftime("%d/%m/%Y"),
        "kpi": {
            "total_machines": total_machines, "machines_actives": machines_actives,
            "machines_pannes": machines_pannes, "disponibilite": disponibilite,
            "production_totale": production_totale, "cycles_totaux": cycles_totaux,
            "total_heures": total_heures, "heures_jour": heures_jour,
            "revenu_jour": revenu_jour, "rentabilite_totale": rentabilite_totale,
            "avg_cycle": avg_cycle, "fuel_avg": fuel_avg, "idle_count": idle_count,
            "nb_alertes": nb_alertes, "nb_stock_bas": nb_stock_bas,
        },
        "active_alerts": active_alerts[:5],
        "low_stock_items": low_stock_items[:5],
        "panne_machines": [r["ID"] for r in rows if r["Statut"] == "Panne"],
        "fleet_table": fleet_table,
        "status_counts_json": mark_safe(json.dumps(status_counts)),
        "prod_chart_json": mark_safe(json.dumps(prod_chart)),
    }
    return render(request, "dashboard.html", context)


def _tenant(request):
    return request.ge_tenant if request.ge_tenant != "__platform__" else "default"


# ---------------------------------------------------------------------------
# CYCLES — analyse de performance de la flotte
# ---------------------------------------------------------------------------
def cycles_view(request):
    manager = FleetManager(_tenant(request))
    rows = manager.get_summary_rows()
    perf = []
    for r in rows:
        hj = r["H. Run Jour"] or 0
        tph = round(r["Production (T)"] / hj, 2) if hj > 0 else 0
        cph = round(r["Cycles"] / hj, 2) if hj > 0 else 0
        eff = round(hj / 24 * 100, 1) if hj > 0 else 0
        perf.append({"id": r["ID"], "type": r["Type"], "operateur": r["Opérateur"],
                     "statut": r["Statut"], "cycles": r["Cycles"], "production": r["Production (T)"],
                     "tps_cycle": r["Tps Cycle Moy (min)"], "h_jour": round(hj, 1),
                     "tph": tph, "cph": cph, "eff": eff})
    perf.sort(key=lambda x: x["tph"], reverse=True)
    for i, p in enumerate(perf, 1):
        p["rang"] = i
    tph_vals = [p["tph"] for p in perf]
    avg_tph = round(sum(tph_vals) / len(tph_vals), 2) if tph_vals else 0
    cph_vals = [p["cph"] for p in perf]
    avg_cph = round(sum(cph_vals) / len(cph_vals), 2) if cph_vals else 0
    best = perf[0] if perf else None
    top = perf[:10]

    # Performance par opérateur (via StaffManager)
    from core.staff import StaffManager
    sm = StaffManager(_tenant(request))
    operateurs = [e for e in sm.get_active_staff() if e.role == "Operateur"]
    op_perf = []
    for op in operateurs:
        machines_op = [r for r in rows if r["Opérateur"] == op.name]
        prod = sum(r["Production (T)"] for r in machines_op) or op.production_tonnes
        cyc = sum(r["Cycles"] for r in machines_op)
        hrs = sum(r["H. Run Jour"] for r in machines_op)
        tph = round(prod / hrs, 2) if hrs > 0 else 0
        op_perf.append({"nom": op.name, "matricule": op.matricule, "equipe": op.team,
                        "nb_machines": len(machines_op),
                        "machines": ", ".join(r["ID"] for r in machines_op) or "Aucune",
                        "cycles": int(cyc), "production": int(prod), "heures": round(hrs, 1), "tph": tph})
    op_perf.sort(key=lambda x: x["production"], reverse=True)
    for i, o in enumerate(op_perf, 1):
        o["rang"] = i

    ctx = {
        "perf": perf,
        "kpi": {"avg_tph": avg_tph, "avg_cph": avg_cph,
                "best_id": best["id"] if best else "—", "best_tph": best["tph"] if best else 0,
                "total_prod": sum(p["production"] for p in perf)},
        "bar_json": mark_safe(json.dumps({"ids": [p["id"] for p in top], "values": [p["tph"] for p in top]})),
        "op_perf": op_perf,
    }
    return render(request, "cycles.html", ctx)


# ---------------------------------------------------------------------------
# CARBURANT — consommation, coûts, saisie de plein (multi-devise)
# ---------------------------------------------------------------------------
def carburant_view(request):
    from core.market import get_exchange_rates
    tid = _tenant(request)
    manager = FleetManager(tid)
    rates = get_exchange_rates()
    message = None

    if request.method == "POST" and request.ge_user.get("permissions", {}).get("can_modify_data", False) is not False:
        mid = request.POST.get("machine_id")
        try:
            q = float(request.POST.get("litres", 0))
            devise = request.POST.get("devise", "USD")
            p_input = float(request.POST.get("prix", 0))
        except (TypeError, ValueError):
            q, devise, p_input = 0, "USD", 0
        if devise == "CFA":
            p_usd = p_input / rates["CFA"] if rates["CFA"] else p_input
        elif devise == "EUR":
            p_usd = p_input / rates["EUR"] if rates["EUR"] else p_input
        else:
            p_usd = p_input
        m = manager.get(mid)
        if m and q > 0:
            m.add_fuel(q, p_usd, devise, p_input)
            message = f"Plein ajouté à {mid} — {q:.0f} L (converti : {p_usd:.3f} $/L)."
            manager = FleetManager(tid)  # recharger

    rows = manager.get_summary_rows()
    total_conso = col_sum_int(rows, "Conso. Jour (L)")
    total_renta = col_sum_int(rows, "Rentabilité ($)")
    fuel_rows = [{"id": r["ID"], "type": r["Type"], "voyage": r["Conso. Voyage (L)"],
                  "shift": r["Conso. Shift (L)"], "jour": r["Conso. Jour (L)"], "mois": r["Conso. Mois (L)"],
                  "rev": r["Rev. Jour ($)"], "cout": r["Coût Fuel ($)"], "renta": r["Rentabilité ($)"]}
                 for r in rows]
    ctx = {
        "message": message, "rates": rates,
        "total_conso": total_conso, "total_renta": total_renta,
        "fuel_rows": fuel_rows, "machine_ids": [r["ID"] for r in rows],
    }
    return render(request, "carburant.html", ctx)


# ---------------------------------------------------------------------------
# MAINTENANCE — santé du parc, planification, pannes, historique
# ---------------------------------------------------------------------------
def maintenance_view(request):
    from datetime import date, datetime
    tid = _tenant(request)
    manager = FleetManager(tid)
    message = None
    can_edit = request.ge_user.get("permissions", {}).get("can_modify_data", False) is not False

    if request.method == "POST" and can_edit:
        action = request.POST.get("action")
        mid = request.POST.get("machine_id")
        who = request.ge_user.get("user", "Système")
        if action == "plan":
            d = request.POST.get("date")
            try:
                dobj = datetime.strptime(d, "%Y-%m-%d").date()
                manager.set_maintenance_date(mid, dobj, request.POST.get("type", "Maintenance préventive"), who)
                message = f"Maintenance planifiée pour {mid} le {d}."
            except (TypeError, ValueError):
                message = "Date invalide."
        elif action == "breakdown":
            manager.report_breakdown(mid, request.POST.get("reason", "Non précisé"))
            message = f"Panne signalée sur {mid}."
        elif action == "repair":
            manager.repair_machine(mid, who, request.POST.get("notes", ""))
            message = f"{mid} réparée et remise en service."
        elif action == "pm":
            manager.do_maintenance_pm(mid, request.POST.get("type", "PM 250h"), who, request.POST.get("notes", ""))
            message = f"Maintenance préventive enregistrée pour {mid}."
        elif action == "add_machine":
            newid = (request.POST.get("new_id") or "").strip()
            try:
                cap = float(request.POST.get("capacity", 0) or 0)
                rate = float(request.POST.get("hourly_rate", 150) or 150)
            except (TypeError, ValueError):
                cap, rate = 0, 150
            if newid and manager.add_machine(newid, (request.POST.get("model") or "").strip(),
                                             (request.POST.get("mtype") or "Camion").strip(), cap, rate):
                message = f"Engin {newid} ajouté à la flotte."
            else:
                message = "Échec : identifiant déjà utilisé ou champ manquant."
        elif action == "remove_machine":
            manager.remove_machine(mid)
            message = f"Engin {mid} retiré de la flotte."
        manager = FleetManager(tid)

    today = date.today()
    health = []
    for m in manager.machines:
        h_rest = m.get_maintenance_status()
        nm = None
        if m.next_maintenance:
            delta = (m.next_maintenance - today).days
            nm = {"date": m.next_maintenance.strftime("%d/%m/%Y"), "delta": delta}
        health.append({"id": m.id, "type": m.type, "model": m.model, "operator": m.operator,
                       "capacity": m.capacity, "hourly_rate": m.hourly_rate, "statut": m.status,
                       "engine_hours": int(m.engine_hours), "h_restantes": int(h_rest),
                       "due": h_rest <= 0, "next_maint": nm, "breakdown_reason": m.breakdown_reason})
    scheduled = [h for h in health if h["next_maint"]]
    en_panne = [h for h in health if h["statut"] == "Panne"]
    pm_due = [h for h in health if h["due"]]
    history = manager.get_maintenance_history(limit=100)
    for h in history:
        try:
            h["date_fmt"] = datetime.strptime(h["date_maintenance"], "%Y-%m-%d").strftime("%d/%m/%Y")
        except (TypeError, ValueError):
            h["date_fmt"] = h["date_maintenance"]
    ctx = {
        "message": message, "can_edit": can_edit, "health": health,
        "machine_ids": [m.id for m in manager.machines],
        "nb_scheduled": len(scheduled), "nb_panne": len(en_panne), "nb_due": len(pm_due),
        "scheduled": scheduled, "history": history, "today": today.strftime("%Y-%m-%d"),
    }
    return render(request, "maintenance.html", ctx)


# ---------------------------------------------------------------------------
# MARCHÉ OR — cours de l'or + taux de change
# ---------------------------------------------------------------------------
def marche_or_view(request):
    from core.market import get_exchange_rates, get_gold_price
    rates = get_exchange_rates()
    gold = get_gold_price()
    oz = gold["price_per_ounce_usd"]
    gram = oz / 31.1035
    ctx = {"rates": rates, "oz_usd": round(oz, 2), "gram_usd": round(gram, 2),
           "gram_cfa": round(gram * rates["CFA"], 0), "oz_cfa": round(oz * rates["CFA"], 0),
           "ts": gold["timestamp"].strftime("%d/%m/%Y %H:%M")}
    return render(request, "marche_or.html", ctx)


# ---------------------------------------------------------------------------
# ADMIN — gestion des utilisateurs (CRUD)
# ---------------------------------------------------------------------------
ROLES = ["Administrateur", "Ingenieur", "RH", "Invite", "Superviseur Production",
         "Superviseur Mecanicien", "Operateur"]
PERM_TABS = [("dashboard", "Dashboard"), ("cycles", "Cycles"), ("carburant", "Carburant"),
             ("maintenance", "Maintenance"), ("stock", "Stock"), ("carte", "Carte"),
             ("finance", "Finance"), ("rh", "RH"), ("admin", "Admin"),
             ("donnees_ingenierie", "Ingénierie"), ("validation_operateur", "Validation"),
             ("messagerie", "Messagerie"), ("sst", "SST")]


def admin_view(request):
    user = request.ge_user
    tid = _tenant(request)
    if not user.get("permissions", {}).get("can_add_users") and user.get("role") != "Administrateur":
        return _forbidden(request, "admin")
    um = get_user_manager()
    message = None
    if request.method == "POST":
        action = request.POST.get("action")
        uname = (request.POST.get("username") or "").strip()
        if action == "add":
            role = request.POST.get("role", "Invite")
            perms = None
            if request.POST.get("custom_perms"):
                base = um.default_permissions.get(role, um.default_permissions["Invite"]).copy()
                for key, _ in PERM_TABS:
                    base[key] = request.POST.get("perm_" + key) == "on"
                perms = base
            ok = um.add_user(uname, request.POST.get("password", ""), role, perms, tid)
            message = f"Utilisateur « {uname} » créé." if ok else f"Échec : « {uname} » existe déjà ou champ manquant."
        elif action == "edit":
            ok = um.update_user(uname, password=request.POST.get("password") or None,
                                role=request.POST.get("role") or None)
            message = f"Utilisateur « {uname} » mis à jour." if ok else "Utilisateur introuvable."
        elif action == "delete":
            ok = um.delete_user(uname)
            message = f"Utilisateur « {uname} » supprimé." if ok else "Suppression impossible (compte protégé)."
        um = get_user_manager()

    users = [u for u in um.users_db if storage.safe_tenant_id(u.get("tenant_id", "default")) == tid]
    roles_count = {}
    for u in users:
        roles_count[u.get("role")] = roles_count.get(u.get("role"), 0) + 1
    ctx = {"message": message, "users": users, "roles": ROLES, "perm_tabs": PERM_TABS,
           "roles_count": roles_count, "total_users": len(users)}
    return render(request, "admin.html", ctx)


# ---------------------------------------------------------------------------
# RH — gestion du personnel
# ---------------------------------------------------------------------------
def rh_view(request):
    from core.staff import StaffManager, ROLES_RH, SHIFTS
    from datetime import datetime
    tid = _tenant(request)
    sm = StaffManager(tid)
    message = None
    can_edit = request.ge_user.get("permissions", {}).get("can_modify_data", False) is not False

    if request.method == "POST" and can_edit:
        action = request.POST.get("action")
        mat = request.POST.get("matricule")
        if action == "add":
            name = (request.POST.get("name") or "").strip()
            da = None
            try:
                if request.POST.get("date_arrivee"):
                    da = datetime.strptime(request.POST["date_arrivee"], "%Y-%m-%d").date()
            except ValueError:
                da = None
            if name:
                sm.add_employee(name, request.POST.get("role", "Operateur"),
                                request.POST.get("team", "A"), request.POST.get("shift", "Standard"),
                                date_arrivee=da)
                message = f"Employé « {name} » ajouté."
        elif action == "deactivate":
            sm.desactiver_employee(mat); message = "Employé désactivé."
        elif action == "reactivate":
            sm.reactiver_employee(mat); message = "Employé réactivé."
        elif action == "delete":
            sm.remove_employee(mat); message = "Employé supprimé."
        elif action == "presence":
            st = request.POST.get("statut", "present")
            sm.enregistrer_presence(mat, st, retard=(st == "retard"))
            message = "Présence enregistrée."
        sm = StaffManager(tid)

    active = sm.get_active_staff()
    ctx = {
        "message": message, "can_edit": can_edit,
        "active": active, "inactive": sm.get_inactive_staff(),
        "teams": sm.teams(), "roles": ROLES_RH, "shifts": SHIFTS,
        "rank_anc": sm.get_classement_anciennete()[:10],
        "rank_prod": sm.get_classement_production()[:10],
        "rank_assi": sm.get_classement_assiduite()[:10],
        "nb_active": len(active), "nb_operateurs": len([e for e in active if e.role == "Operateur"]),
        "today": date.today().strftime("%Y-%m-%d"),
    }
    return render(request, "rh.html", ctx)


# ---------------------------------------------------------------------------
# STOCK — pièces de rechange
# ---------------------------------------------------------------------------
def stock_view(request):
    from core.stock import StockStore, catalog_names
    tid = _tenant(request)
    store = StockStore(tid)
    message = None
    can_edit = request.ge_user.get("permissions", {}).get("can_modify_data", False) is not False

    if request.method == "POST" and can_edit:
        action = request.POST.get("action")
        part = request.POST.get("piece")
        who = request.ge_user.get("user", "Système")
        try:
            qty = float(request.POST.get("quantite", 0))
        except (TypeError, ValueError):
            qty = 0
        if action == "entry" and part and qty > 0:
            store.add_entry(part, qty, request.POST.get("reference", ""), request.POST.get("notes", ""), who)
            message = f"Entrée : +{qty:.0f} × {part}."
        elif action == "exit" and part and qty > 0:
            ok = store.remove_entry(part, qty, request.POST.get("reference", ""), request.POST.get("notes", ""), who)
            message = f"Sortie : -{qty:.0f} × {part}." if ok else "Stock insuffisant."
        elif action == "config" and part:
            try:
                seuil = float(request.POST.get("seuil_min", 5))
            except (TypeError, ValueError):
                seuil = 5
            store.set_level(part, qty, seuil, request.POST.get("unite", "unité"))
            message = f"Stock configuré : {part}."
        store = StockStore(tid)

    rows = store.rows()
    ctx = {
        "message": message, "can_edit": can_edit, "rows": rows,
        "low": store.get_low_stock_items(), "movements": store.movements[:100],
        "catalog": catalog_names(), "known_parts": [r["nom"] for r in rows],
        "nb_refs": len(rows), "nb_low": len(store.get_low_stock_items()),
        "total_units": sum(r["quantite"] for r in rows),
    }
    return render(request, "stock.html", ctx)


# ---------------------------------------------------------------------------
# FINANCE — contrats miniers, revenus, profil entreprise, factures
# ---------------------------------------------------------------------------
def finance_view(request):
    from core.finance import ContractManager, collect_fuel_expenses, _COMPANY_FIELDS
    from datetime import date, datetime
    tid = _tenant(request)
    cm = ContractManager(tid)
    message = None
    can_edit = request.ge_user.get("permissions", {}).get("can_modify_data", False) is not False

    if request.method == "POST" and can_edit:
        action = request.POST.get("action")
        if action == "add_contract":
            try:
                somme = float(request.POST.get("somme") or 0) or None
            except ValueError:
                somme = None
            try:
                rate = float(request.POST.get("rate", 0))
            except ValueError:
                rate = 0
            ok = cm.add_contract(request.POST.get("contract_id", "").strip(),
                                 request.POST.get("name", "").strip(),
                                 request.POST.get("contract_type", "BCM"),
                                 rate, request.POST.get("currency", "USD"),
                                 somme, request.POST.get("client", "").strip())
            message = "Contrat ajouté." if ok else "Échec : ID déjà utilisé ou champ manquant."
        elif action == "update_rate":
            try:
                rate = float(request.POST.get("rate", 0))
            except ValueError:
                rate = 0
            cm.update_rate(request.POST.get("contract_id"), rate, request.POST.get("currency", "USD"))
            message = "Taux mis à jour."
        elif action == "toggle":
            cm.toggle_active(request.POST.get("contract_id")); message = "Statut du contrat modifié."
        elif action == "company":
            for f in _COMPANY_FIELDS:
                setattr(cm.company_info, f, request.POST.get(f, "") or "")
            from core.finance import save_company
            save_company(cm.company_info, tid)
            message = "Fiche entreprise enregistrée."
        cm = ContractManager(tid)

    manager = FleetManager(tid)
    cm.update_from_fleet(manager)
    summary = cm.revenue_summary()

    # Dépenses carburant : mois en cours par défaut
    today = date.today()
    try:
        sd = datetime.strptime(request.GET.get("start", ""), "%Y-%m-%d").date()
    except ValueError:
        sd = today.replace(day=1)
    try:
        ed = datetime.strptime(request.GET.get("end", ""), "%Y-%m-%d").date()
    except ValueError:
        ed = today
    fuel_total, fuel_rows = collect_fuel_expenses(tid, sd, ed)

    contracts = []
    for c in cm.contracts:
        contracts.append({
            "id": c.contract_id, "name": c.name, "client": c.client_name or "—",
            "type": "BCM" if c.contract_type == "BCM" else "Horaire",
            "rate": f"{c.original_rate:,.2f} {c.rate_currency}", "rate_usd": round(c.rate, 2),
            "somme": c.somme_negociee, "active": c.active,
            "vol_jour": round(c.volume_jour, 1), "vol_mois": round(c.volume_mois, 1),
            "h_jour": round(c.heures_jour, 1), "h_mois": round(c.heures_mois, 1),
            "rev_jour": round(c.revenu_jour), "rev_mois": round(c.revenu_mois),
            "rev_annee": round(c.revenu_annee), "is_bcm": c.contract_type == "BCM",
        })
    net = summary["mois"] - fuel_total
    ctx = {
        "message": message, "can_edit": can_edit, "summary": summary,
        "contracts": contracts, "company": cm.company_info,
        "fuel_total": round(fuel_total), "fuel_rows": fuel_rows,
        "period_start": sd.strftime("%Y-%m-%d"), "period_end": ed.strftime("%Y-%m-%d"),
        "net_mois": round(net),
    }
    return render(request, "finance.html", ctx)


def invoice_view(request, cid):
    from core.finance import ContractManager
    from datetime import datetime
    tid = _tenant(request)
    cm = ContractManager(tid)
    cm.update_from_fleet(FleetManager(tid))
    c = cm.get_contract(cid)
    if not c:
        return _forbidden(request, "finance")
    period = request.GET.get("period", "mois")
    if c.contract_type == "BCM":
        qty, unit = {"jour": c.volume_jour, "semaine": c.volume_semaine,
                     "mois": c.volume_mois, "annee": c.volume_annee}.get(period, c.volume_mois), "BCM"
    else:
        qty, unit = {"jour": c.heures_jour, "semaine": c.heures_semaine,
                     "mois": c.heures_mois, "annee": c.heures_annee}.get(period, c.heures_mois), "heures"
    amount = {"jour": c.revenu_jour, "semaine": c.revenu_semaine,
              "mois": c.revenu_mois, "annee": c.revenu_annee}.get(period, c.revenu_mois)
    ctx = {"c": c, "ci": cm.company_info, "period": period, "qty": round(qty, 2),
           "unit": unit, "amount": round(amount, 2), "today": datetime.now().strftime("%d/%m/%Y"),
           "num": f"FAC-{c.contract_id}-{datetime.now().strftime('%Y%m')}"}
    return render(request, "invoice.html", ctx)


# ---------------------------------------------------------------------------
# RAPPORT INGÉNIERIE — production sur une période (imprimable → PDF)
# ---------------------------------------------------------------------------
def rapport_view(request):
    """Rapport de production par engin sur une période. Accessible aux ingénieurs."""
    from core.engineering import get_period_report
    from core.finance import load_company
    from datetime import date, datetime
    import calendar
    user = request.ge_user
    perms = user.get("permissions", {})
    if not (perms.get("donnees_ingenierie") or perms.get("dashboard")):
        return _forbidden(request, "ingenierie")
    tid = _tenant(request)

    today = date.today()
    first = today.replace(day=1)
    try:
        start = datetime.strptime(request.GET.get("start", ""), "%Y-%m-%d").date()
    except ValueError:
        start = first
    try:
        end = datetime.strptime(request.GET.get("end", ""), "%Y-%m-%d").date()
    except ValueError:
        end = today
    if end < start:
        start, end = end, start

    rows, tot = get_period_report(tid, start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
    ci = load_company(tid)
    ctx = {
        "rows": rows, "tot": tot, "ci": ci,
        "start": start.strftime("%Y-%m-%d"), "end": end.strftime("%Y-%m-%d"),
        "start_fr": start.strftime("%d/%m/%Y"), "end_fr": end.strftime("%d/%m/%Y"),
        "today": today.strftime("%d/%m/%Y"),
        "generated_by": user.get("user", ""),
        "num": f"RAP-{start.strftime('%Y%m%d')}-{end.strftime('%Y%m%d')}",
        "print": request.GET.get("print") == "1",
    }
    return render(request, "rapport.html", ctx)


# ---------------------------------------------------------------------------
# FACTURE MENSUELLE — consolidée pour la mine (fin de mois, admin)
# ---------------------------------------------------------------------------
def facture_mensuelle_view(request):
    """Facture mensuelle consolidée (tous contrats actifs). Réservée à l'admin."""
    from core.finance import ContractManager
    from datetime import datetime
    if not request.ge_user.get("permissions", {}).get("admin"):
        return _forbidden(request, "finance")
    tid = _tenant(request)
    cm = ContractManager(tid)
    cm.update_from_fleet(FleetManager(tid))

    month = request.GET.get("month") or datetime.now().strftime("%Y-%m")
    client_filter = (request.GET.get("client") or "").strip()

    lines = []
    for c in cm.contracts:
        if not c.active:
            continue
        if client_filter and (c.client_name or "") != client_filter:
            continue
        if c.contract_type == "BCM":
            qty, unit = round(c.volume_mois, 2), "BCM"
        else:
            qty, unit = round(c.heures_mois, 2), "heures"
        amount = round(c.revenu_mois, 2)
        lines.append({"contract_id": c.contract_id, "name": c.name,
                      "client": c.client_name or "—", "type": c.contract_type,
                      "qty": qty, "unit": unit, "rate": round(c.rate, 2), "amount": amount})
    total = round(sum(x["amount"] for x in lines), 2)
    clients = sorted({(c.client_name or "—") for c in cm.contracts if c.active})
    try:
        month_fr = datetime.strptime(month, "%Y-%m").strftime("%m/%Y")
    except ValueError:
        month_fr = month
    ctx = {
        "lines": lines, "total": total, "ci": cm.company_info,
        "month": month, "month_fr": month_fr, "clients": clients,
        "client_filter": client_filter,
        "today": datetime.now().strftime("%d/%m/%Y"),
        "num": f"FACM-{month.replace('-', '')}" + (f"-{client_filter}" if client_filter else ""),
        "generated_by": request.ge_user.get("user", ""),
        "print": request.GET.get("print") == "1",
    }
    return render(request, "facture_mensuelle.html", ctx)


# ---------------------------------------------------------------------------
# CARTE — positions GPS des engins
# ---------------------------------------------------------------------------
def carte_view(request):
    manager = FleetManager(_tenant(request))
    machines = []
    for m in manager.machines:
        machines.append({"id": m.id, "type": m.type, "statut": m.status,
                         "lat": m.lat, "lon": m.lon, "operateur": m.operator,
                         "production": int(m.production_tonnes)})
    center_lat = sum(m["lat"] for m in machines) / len(machines) if machines else 12.37
    center_lon = sum(m["lon"] for m in machines) / len(machines) if machines else -1.53
    ctx = {
        "machines_json": mark_safe(json.dumps(machines)),
        "machines": machines,
        "center": mark_safe(json.dumps({"lat": center_lat, "lon": center_lon})),
        "nb": len(machines),
        "nb_active": sum(1 for m in machines if m["statut"] == "Active"),
        "nb_panne": sum(1 for m in machines if m["statut"] == "Panne"),
    }
    return render(request, "carte.html", ctx)


# ---------------------------------------------------------------------------
# DONNÉES INGÉNIERIE — saisie manuelle production / heures / carburant
# ---------------------------------------------------------------------------
def ingenierie_view(request):
    from core.engineering import apply_manual_entry, get_manual_entries_history, get_daily_summary
    from datetime import date, datetime
    tid = _tenant(request)
    manager = FleetManager(tid)
    message = None
    computed = None
    can_edit = request.ge_user.get("permissions", {}).get("can_modify_data", False) is not False

    if request.method == "POST" and can_edit:
        m = manager.get(request.POST.get("machine_id"))
        if m:
            def _f(name):
                try:
                    return float(request.POST.get(name, 0) or 0)
                except (TypeError, ValueError):
                    return 0
            ok, message, computed = apply_manual_entry(
                m, request.POST.get("shift", "Jour"),
                request.POST.get("entry_date") or date.today().strftime("%Y-%m-%d"),
                _f("h_debut"), _f("h_fin"), _f("production"), _f("fuel"),
                request.POST.get("period", "Journalière"), _f("fuel_price") or 1.5,
                request.ge_user.get("user", "Système"),
                voyages=_f("voyages"), facteur=_f("facteur"))
            manager = FleetManager(tid)

    try:
        rep = datetime.strptime(request.GET.get("date", ""), "%Y-%m-%d").date()
    except ValueError:
        rep = date.today()
    by_shift, tot = get_daily_summary(tid, rep.strftime("%Y-%m-%d"))
    history = get_manual_entries_history(tid, limit=60)
    machines = [{"id": m.id, "model": m.model, "type": m.type, "engine_hours": int(m.engine_hours),
                 "production": int(m.production_tonnes), "cons_jour": int(m.cons_jour)}
                for m in manager.machines]
    ctx = {"message": message, "computed": computed, "can_edit": can_edit,
           "machines": machines, "machine_ids": [m["id"] for m in machines],
           "by_shift": by_shift, "tot": tot, "history": history,
           "report_date": rep.strftime("%Y-%m-%d"), "today": date.today().strftime("%Y-%m-%d")}
    return render(request, "ingenierie.html", ctx)


# ---------------------------------------------------------------------------
# SST — santé & sécurité au travail
# ---------------------------------------------------------------------------
def sst_view(request):
    from core import sst as sstmod
    from core.staff import StaffManager
    from datetime import date
    tid = _tenant(request)
    message = None
    can_edit = request.ge_user.get("permissions", {}).get("can_modify_data", False) is not False

    if request.method == "POST" and can_edit:
        action = request.POST.get("action")
        who = request.ge_user.get("user", "Système")
        if action == "entry":
            desc = (request.POST.get("description") or "").strip()
            if desc:
                sstmod.add_entry(tid, request.POST.get("type", "Autre"),
                                 request.POST.get("date") or date.today().isoformat(),
                                 (request.POST.get("lieu") or "").strip(),
                                 request.POST.get("gravite", "Faible"), desc, who)
                message = "Fiche SST enregistrée."
        elif action == "check":
            cond = (request.POST.get("conducteur") or "").strip()
            veh = (request.POST.get("vehicule") or "").strip()
            insp = request.POST.get("insp") == "on"
            t5 = request.POST.get("take5") == "on"
            fr = request.POST.get("frein") == "on"
            if cond and veh and (insp or t5 or fr):
                sstmod.add_check(tid, cond, request.POST.get("matricule") or None, veh,
                                 insp, t5, fr, (request.POST.get("notes") or "").strip(),
                                 request.POST.get("date") or date.today().isoformat(), who)
                message = f"Contrôles enregistrés pour {cond}."
            else:
                message = "Indiquez le conducteur, le véhicule et au moins un contrôle."

    entries = sstmod.load_entries(tid)
    checks = sstmod.load_checks(tid)
    staff = StaffManager(tid).get_active_staff()
    ctx = {
        "message": message, "can_edit": can_edit,
        "types": sstmod.TYPES, "gravites": sstmod.GRAVITES,
        "entries": entries[:50], "checks": checks[:50],
        "checks_summary": sstmod.checks_summary(checks),
        "staff": [{"name": e.name, "matricule": e.matricule, "machine": e.assigned_machine} for e in staff],
        "nb_fiches": len(entries), "nb_checks": len(checks),
        "nb_incidents": sum(1 for e in entries if "incident" in (e.get("type") or "").lower() or "accident" in (e.get("type") or "").lower()),
        "nb_recent": sstmod.count_recent(checks, ["date_controle", "ts"], 30),
        "today": date.today().isoformat(),
    }
    return render(request, "sst.html", ctx)


# ---------------------------------------------------------------------------
# MESSAGERIE — messages, communiqués, bandeau
# ---------------------------------------------------------------------------
def messagerie_view(request):
    from core import messaging
    tid = _tenant(request)
    me = request.ge_user.get("user", "")
    is_admin = bool(request.ge_user.get("permissions", {}).get("admin"))
    message = None

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "send":
            body = (request.POST.get("body") or "").strip()
            to = request.POST.get("dest") or "__team__"
            if body:
                messaging.add_message(tid, me, to, body, "message")
                message = "Message envoyé."
        elif action == "communique" and is_admin:
            title = (request.POST.get("title") or "").strip()
            body = (request.POST.get("body") or "").strip()
            if body:
                block = (f"**{title}**\n\n" if title else "") + body
                messaging.add_message(tid, me, "__all__", block, "communique")
                message = "Communiqué publié."
        elif action == "banner" and is_admin:
            messaging.save_banner(tid, request.POST.get("banner_text", ""),
                                  request.POST.get("banner_active") == "on")
            message = "Bandeau mis à jour."

    all_msgs = messaging.load_messages(tid)
    visible = [m for m in all_msgs if messaging.visible_for_user(m, me)]
    visible.sort(key=lambda x: x.get("ts", ""), reverse=True)
    from core.auth import get_user_manager
    users = [u["user"] for u in get_user_manager().users_in_tenant(tid) if u["user"] != me]
    for m in visible:
        m["ts_fmt"] = m.get("ts", "")[:16].replace("T", " ")
        m["to_lbl"] = "Salon équipe" if m.get("to") == "__team__" else ("Toute l'entreprise" if m.get("to") == "__all__" else m.get("to"))
    ctx = {
        "message": message, "is_admin": is_admin, "me": me, "users": users,
        "communiques": [m for m in visible if m.get("kind") == "communique"][:15],
        "thread": [m for m in visible if m.get("kind") != "communique"][:40],
        "banner": messaging.load_banner(tid),
    }
    # La consultation de la messagerie remet le compteur d'alertes à zéro.
    try:
        messaging.mark_read(tid, me)
    except Exception:
        pass
    return render(request, "messagerie.html", ctx)


# ---------------------------------------------------------------------------
# VALIDATION OPÉRATEUR — chargement → déchargement
# ---------------------------------------------------------------------------
def validation_view(request):
    from core import operators
    tid = _tenant(request)
    me = request.ge_user.get("user", "")
    message = None

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "load":
            truck = request.POST.get("truck")
            if truck:
                operators.add_loading(tid, me, truck, request.POST.get("mineral_type", ""),
                                      request.POST.get("grade", ""), request.POST.get("destination", ""))
                message = f"Chargement validé pour {truck} — notification envoyée."
        elif action == "ack":
            if operators.acknowledge(tid, request.POST.get("notif_id"), me):
                message = "Ordre de déchargement acquitté."

    manager = FleetManager(tid)
    ctx = {
        "message": message,
        "trucks": [m.id for m in manager.machines if m.type in ("Dumper", "Camion")] or [m.id for m in manager.machines],
        "mineral_types": operators.MINERAL_TYPES, "grades": operators.GRADES,
        "pending": operators.pending(tid), "recent": operators.recent(tid, 40),
        "nb_pending": len(operators.pending(tid)),
    }
    return render(request, "validation.html", ctx)


# ---------------------------------------------------------------------------
# CONSOLE GESTIONNAIRE — plateforme SaaS (multi-entreprises)
# ---------------------------------------------------------------------------
def console_view(request):
    from core.auth import get_user_manager
    from datetime import date
    if request.ge_user.get("role") != "Gestionnaire":
        return _forbidden(request, "console")
    um = get_user_manager()
    message = None

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "create_client":
            name = (request.POST.get("name") or "").strip()
            adm_u = (request.POST.get("admin_user") or "").strip()
            adm_p = (request.POST.get("admin_pass") or "").strip()
            if not name or not adm_u or not adm_p:
                message = "Nom d'entreprise, identifiant et mot de passe admin requis."
            elif um.get_user(adm_u):
                message = "Cet identifiant admin existe déjà."
            else:
                tid = storage.create_tenant(name, request.POST.get("tid") or None,
                                            request.POST.get("plan", "standard"),
                                            request.POST.get("subscription_end", ""),
                                            address=request.POST.get("address", ""),
                                            phone=request.POST.get("phone", ""),
                                            email=request.POST.get("email", ""),
                                            tax_id=request.POST.get("tax_id", ""),
                                            rccm=request.POST.get("rccm", ""))
                if not tid:
                    message = "Identifiant d'entreprise déjà utilisé ou invalide."
                else:
                    um.add_user(adm_u, adm_p, "Administrateur", tenant_id=tid)
                    message = f"Espace client « {tid} » créé — l'admin {adm_u} peut se connecter."
                    um = get_user_manager()
        elif action == "toggle_active":
            reg = storage.get_tenants_registry()
            t = storage.safe_tenant_id(request.POST.get("tid"))
            storage.set_tenant_active(t, not reg.get(t, {}).get("active", True))
            message = f"Statut de « {t} » modifié."
        elif action == "update":
            storage.update_tenant(request.POST.get("tid"), {
                "name": request.POST.get("name"), "plan": request.POST.get("plan"),
                "subscription_end": request.POST.get("subscription_end"),
                "email": request.POST.get("email"), "phone": request.POST.get("phone"),
                "rccm": request.POST.get("rccm"), "tax_id": request.POST.get("tax_id"),
            })
            message = "Fiche entreprise mise à jour."
        elif action == "delete":
            if (request.POST.get("confirm") or "").strip() == request.POST.get("tid"):
                ok, message = storage.delete_tenant_and_data(request.POST.get("tid"), um)
                um = get_user_manager()
            else:
                message = "La confirmation ne correspond pas à l'identifiant."

    reg = storage.get_tenants_registry()
    counts = {}
    for u in um.users_db:
        if u.get("role") == "Gestionnaire":
            continue
        t = storage.safe_tenant_id(u.get("tenant_id", "default"))
        counts[t] = counts.get(t, 0) + 1
    tenants = []
    for tid, meta in reg.items():
        if tid == "__platform__":
            continue
        tenants.append({"id": tid, "name": meta.get("name", ""), "plan": meta.get("plan", ""),
                        "end": meta.get("subscription_end", "") or "—", "active": meta.get("active", True),
                        "rccm": meta.get("rccm", "") or "—", "email": meta.get("email", "") or meta.get("phone", "") or "—",
                        "users": counts.get(tid, 0)})
    ctx = {"message": message, "me": request.ge_user.get("user"), "tenants": tenants,
           "editable": [t for t in tenants if t["id"] != "default"],
           "deletable": [t for t in tenants if t["id"] != "default"],
           "today": date.today().isoformat(), "year_end": date.today().replace(month=12, day=31).isoformat()}
    return render(request, "console.html", ctx)


# ---------------------------------------------------------------------------
# ASSISTANT — bot d'aide sur la plateforme (apprenable)
# ---------------------------------------------------------------------------
def assistant_ask(request):
    from django.http import JsonResponse
    from core.assistant import answer
    q = (request.POST.get("q") or "").strip()
    tid = _tenant(request)
    return JsonResponse({"answer": answer(tid, q)})


def assistant_teach(request):
    from django.http import JsonResponse
    from core.assistant import add_kb
    # Réservé à l'administrateur général du compte client (rôle Administrateur).
    if request.ge_user.get("role") != "Administrateur":
        return JsonResponse({"ok": False, "msg": "Réservé à l'administrateur général du compte."})
    q = (request.POST.get("q") or "").strip()
    a = (request.POST.get("a") or "").strip()
    if not q or not a:
        return JsonResponse({"ok": False, "msg": "Question et réponse requises."})
    add_kb(_tenant(request), q, a)
    return JsonResponse({"ok": True, "msg": "Merci, c'est appris ✔"})


# ---------------------------------------------------------------------------
# NOTIFICATIONS — PM dus, pannes, stock critique, messages (pour badge + voix)
# ---------------------------------------------------------------------------
def notifications_view(request):
    from django.http import JsonResponse
    tid = _tenant(request)
    me = request.ge_user.get("user", "")
    items = []
    if tid == "__platform__":
        return JsonResponse({"items": items, "count": 0})

    # Maintenance préventive (PM) — heures restantes avant prochaine PM
    try:
        for m in FleetManager(tid).machines:
            if str(m.status) == "Panne":
                items.append({"type": "panne", "level": "danger",
                              "text": f"Engin {m.id} en panne."})
                continue
            try:
                remaining = m.get_maintenance_status()
            except Exception:
                remaining = None
            if remaining is None:
                continue
            if remaining <= 0:
                items.append({"type": "pm", "level": "danger",
                              "text": f"Maintenance PM DÉPASSÉE pour {m.id} ({abs(int(remaining))} h de retard)."})
            elif remaining <= 25:
                items.append({"type": "pm", "level": "warning",
                              "text": f"Maintenance PM bientôt due pour {m.id} (dans {int(remaining)} h)."})
    except Exception:
        pass

    # Stock critique
    try:
        from core.stock import StockStore
        for it in StockStore(tid).get_low_stock_items():
            items.append({"type": "stock", "level": "warning",
                          "text": f"Stock bas : {it['nom']} ({it['quantite']} {it.get('unite','')} ≤ seuil {it['seuil_min']})."})
    except Exception:
        pass

    # Messages non-lus
    try:
        from core.messaging import unread_count
        n = unread_count(tid, me)
        if n:
            items.append({"type": "message", "level": "info",
                          "text": f"{n} nouveau(x) message(s) dans la messagerie."})
    except Exception:
        pass

    return JsonResponse({"items": items, "count": len(items)})


# ---------------------------------------------------------------------------
# Routage des onglets
# ---------------------------------------------------------------------------
_VIEW_BY_SLUG = {
    "dashboard": dashboard_view,
    "cycles": cycles_view,
    "carburant": carburant_view,
    "maintenance": maintenance_view,
    "stock": stock_view,
    "finance": finance_view,
    "carte": carte_view,
    "ingenierie": ingenierie_view,
    "sst": sst_view,
    "messagerie": messagerie_view,
    "validation": validation_view,
    "rh": rh_view,
    "marche-or": marche_or_view,
    "admin": admin_view,
}


def tab_view(request, slug):
    user = request.ge_user
    tab = TAB_BY_SLUG.get(slug)
    if not tab or not can_access(user, slug):
        return _forbidden(request, slug)
    view = _VIEW_BY_SLUG.get(slug)
    if view:
        return view(request)
    return render(request, "placeholder.html", {"tab": tab})


def _forbidden(request, slug):
    user = getattr(request, "ge_user", None)
    tabs = authorized_tabs(user) if user else []
    return render(request, "forbidden.html", {"slug": slug, "nav_tabs": tabs}, status=403)
