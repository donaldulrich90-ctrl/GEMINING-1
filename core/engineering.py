"""Données ingénierie — saisie manuelle production/heures/carburant par shift.

Porté depuis app.py. La saisie met à jour les agrégats de la machine
(engine_hours, production, cycles, conso) et enregistre un manual_entry.
C'est la source de données qui alimente Dashboard, Cycles et Finance.
"""
from .db import get_connection

FUEL_PRICE_AVG = 1.5


def apply_manual_entry(machine, shift, entry_date, h_debut, h_fin, production,
                       fuel, period, fuel_price, entered_by, voyages=0, facteur=0):
    """Applique une saisie : met à jour la machine + enregistre l'entrée.

    Deux façons d'obtenir le tonnage :
      - pesée directe : renseigner `production` (tonnes) ;
      - calcul : renseigner `voyages` (nombre de voyages) et, au choix,
        `facteur` (tonnes par voyage). Sans facteur, la capacité de l'engin
        sert de tonnage par voyage. Le tonnage = voyages × (facteur ou capacité).

    Retourne (ok, message, computed) — computed contient les valeurs calculées.
    """
    # Heures = H-mètre fin − début
    if h_debut == 0 and h_fin == 0:
        hours = 0.0
    elif h_debut > 0 and h_fin > h_debut:
        hours = h_fin - h_debut
    else:
        return False, "H-mètre invalide : fin doit être > début (ou les deux à 0).", None

    # Tonnage calculé à partir des voyages si renseignés (sinon pesée directe)
    if voyages and voyages > 0:
        tonnes_par_voyage = facteur if (facteur and facteur > 0) else (machine.capacity or 0)
        production = voyages * tonnes_par_voyage
        cycles_added = voyages
    else:
        cycles_added = (production / machine.capacity) if machine.capacity > 0 else 0

    if hours == 0 and production == 0 and fuel == 0:
        return False, "Saisir au moins une valeur (heures, tonnage/voyages ou litres).", None
    new_h_jour = machine.h_jour + hours
    new_h_semaine = machine.h_semaine + hours
    new_h_mois = machine.h_mois + hours
    new_cons_jour = machine.cons_jour + fuel
    new_cycles = machine.cycle + cycles_added

    revenu_jour = new_h_jour * machine.hourly_rate
    revenu_hebdo = new_h_semaine * machine.hourly_rate
    revenu_mois = new_h_mois * machine.hourly_rate
    cout_fuel = new_cons_jour * FUEL_PRICE_AVG
    rentabilite = revenu_jour - cout_fuel
    cons_par_cycle = new_cons_jour / new_cycles if new_cycles > 0 else 0
    cons_par_shift = new_cons_jour / 3
    avg_cycle_time = (new_h_jour * 60) / new_cycles if new_cycles > 0 else 0

    # -- mise à jour de la machine (mêmes règles que l'ancienne app) --------
    if hours > 0:
        machine.engine_hours += hours
        machine.h_jour += hours
        if period in ("Hebdomadaire", "Mensuelle", "Toutes"):
            machine.h_semaine += hours
        if period in ("Mensuelle", "Toutes"):
            machine.h_mois += hours
    if production > 0:
        machine.production_tonnes += production
        machine.cycle += cycles_added
    if fuel > 0:
        machine.cons_jour += fuel
        if period in ("Hebdomadaire", "Mensuelle", "Toutes"):
            machine.cons_mois += fuel
        if period in ("Mensuelle", "Toutes"):
            machine.cons_annee += fuel
        machine.cons_total += fuel
        machine.fuel_tank = min(100, machine.fuel_tank + (fuel / 1000) * 100)
    machine.save_to_db()

    save_manual_entry(machine.tenant_id, machine.id, shift, entry_date, hours, production,
                      fuel, fuel_price, period, revenu_jour, revenu_hebdo, revenu_mois,
                      cout_fuel, rentabilite, cycles_added, cons_par_cycle, cons_par_shift,
                      avg_cycle_time, entered_by)

    return True, f"Saisie enregistrée pour {machine.id} ({shift}).", {
        "hours": hours, "cycles_added": round(cycles_added, 2),
        "production": round(production, 1), "voyages": round(voyages or 0, 1),
        "revenu_jour": round(revenu_jour), "cout_fuel": round(cout_fuel),
        "rentabilite": round(rentabilite), "avg_cycle_time": round(avg_cycle_time, 1),
    }


def save_manual_entry(tenant_id, machine_id, shift, entry_date, hours, production, fuel,
                      fuel_price, period, rev_jour, rev_hebdo, rev_mois, cost_fuel,
                      profitability, cycles_added, cons_per_cycle, cons_per_shift,
                      avg_cycle_time, entered_by):
    with get_connection(tenant_id) as conn:
        conn.execute("""
            INSERT INTO manual_entries (
                machine_id, shift, entry_date, hours_worked, production_tonnes,
                fuel_consumed, fuel_price_usd, update_period, revenue_jour, revenue_hebdo,
                revenue_mois, cost_fuel, profitability, cycles_added, cons_per_cycle,
                cons_per_shift, avg_cycle_time, entered_by
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (machine_id, shift, entry_date, hours, production, fuel, fuel_price, period,
              rev_jour, rev_hebdo, rev_mois, cost_fuel, profitability, cycles_added,
              cons_per_cycle, cons_per_shift, avg_cycle_time, entered_by))


def get_manual_entries_history(tenant_id, machine_id=None, shift=None, start=None, end=None, limit=100):
    with get_connection(tenant_id) as conn:
        cur = conn.cursor()
        q = "SELECT * FROM manual_entries WHERE 1=1"
        p = []
        if machine_id:
            q += " AND machine_id = ?"; p.append(machine_id)
        if shift and shift != "Tous":
            q += " AND shift = ?"; p.append(shift)
        if start:
            q += " AND entry_date >= ?"; p.append(start)
        if end:
            q += " AND entry_date <= ?"; p.append(end)
        q += " ORDER BY entry_date DESC, created_at DESC LIMIT ?"; p.append(limit)
        cur.execute(q, p)
        return [dict(r) for r in cur.fetchall()]


def get_daily_summary(tenant_id, day_str):
    """Synthèse d'un jour : par shift + totaux."""
    with get_connection(tenant_id) as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT shift, COUNT(*) n, COALESCE(SUM(hours_worked),0) h,
                   COALESCE(SUM(production_tonnes),0) prod, COALESCE(SUM(fuel_consumed),0) fuel,
                   COALESCE(SUM(cycles_added),0) cyc
            FROM manual_entries WHERE entry_date = ? GROUP BY shift ORDER BY shift
        """, (day_str,))
        by_shift = [dict(r) for r in cur.fetchall()]
    tot = {"n": sum(s["n"] for s in by_shift), "h": sum(s["h"] for s in by_shift),
           "prod": sum(s["prod"] for s in by_shift), "fuel": sum(s["fuel"] for s in by_shift),
           "cyc": sum(s["cyc"] for s in by_shift)}
    tot["tph"] = round(tot["prod"] / tot["h"], 2) if tot["h"] > 0 else 0
    tot["lpt"] = round(tot["fuel"] / tot["prod"], 2) if tot["prod"] > 0 else 0
    return by_shift, tot


def get_period_report(tenant_id, start, end):
    """Rapport agrégé par engin sur une période [start, end] (dates 'YYYY-MM-DD').

    Renvoie (par_engin, totaux). Chaque ligne : machine_id, jours, heures,
    production, carburant, cycles, tonnes/heure, litres/tonne.
    """
    with get_connection(tenant_id) as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT machine_id,
                   COUNT(DISTINCT entry_date) jours,
                   COALESCE(SUM(hours_worked),0) h,
                   COALESCE(SUM(production_tonnes),0) prod,
                   COALESCE(SUM(fuel_consumed),0) fuel,
                   COALESCE(SUM(cycles_added),0) cyc,
                   COUNT(*) n
            FROM manual_entries
            WHERE entry_date >= ? AND entry_date <= ?
            GROUP BY machine_id ORDER BY prod DESC
        """, (start, end))
        rows = [dict(r) for r in cur.fetchall()]
    for r in rows:
        r["tph"] = round(r["prod"] / r["h"], 2) if r["h"] > 0 else 0
        r["lpt"] = round(r["fuel"] / r["prod"], 3) if r["prod"] > 0 else 0
    tot = {
        "h": round(sum(r["h"] for r in rows), 1),
        "prod": round(sum(r["prod"] for r in rows), 1),
        "fuel": round(sum(r["fuel"] for r in rows), 1),
        "cyc": int(sum(r["cyc"] for r in rows)),
        "n": sum(r["n"] for r in rows),
        "engins": len(rows),
    }
    tot["tph"] = round(tot["prod"] / tot["h"], 2) if tot["h"] > 0 else 0
    tot["lpt"] = round(tot["fuel"] / tot["prod"], 3) if tot["prod"] > 0 else 0
    return rows, tot


# ---------------------------------------------------------------------------
# Pannes & arrêts par shift (suivi ingénierie)
# ---------------------------------------------------------------------------

def _incident_duration(start_time, end_time, duration_hours):
    """Durée d'impact en heures. Priorité à la valeur saisie ; sinon calcul HH:MM.

    Gère le passage minuit (shift de nuit) : si fin < début, on ajoute 24 h.
    """
    try:
        if duration_hours and float(duration_hours) > 0:
            return round(float(duration_hours), 2)
    except (TypeError, ValueError):
        pass
    from datetime import datetime
    try:
        t1 = datetime.strptime((start_time or "").strip(), "%H:%M")
        t2 = datetime.strptime((end_time or "").strip(), "%H:%M")
        diff = (t2 - t1).total_seconds() / 3600.0
        if diff < 0:
            diff += 24
        return round(diff, 2)
    except (ValueError, TypeError):
        return 0.0


def save_shift_incident(tenant_id, machine_id, entry_date, shift, incident_type,
                        start_time, end_time, duration_hours,
                        production_impact, measures_next_shift, entered_by):
    """Enregistre une panne / un arrêt survenu pendant un shift.

    Retourne (ok, message, computed). `computed` contient la durée retenue.
    """
    if not machine_id:
        return False, "S\u00e9lectionnez un engin.", None
    dur = _incident_duration(start_time, end_time, duration_hours)
    impact = (production_impact or "").strip()
    if dur == 0 and not impact:
        return False, "Indiquez au moins la dur\u00e9e (ou les heures d\u00e9but/fin) et les d\u00e9tails de l'impact.", None
    with get_connection(tenant_id) as conn:
        conn.execute("""
            INSERT INTO shift_incidents (
                machine_id, entry_date, shift, incident_type, start_time, end_time,
                duration_hours, production_impact, measures_next_shift, entered_by
            ) VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (machine_id, entry_date, shift, incident_type or "Panne",
              (start_time or "").strip(), (end_time or "").strip(), dur, impact,
              (measures_next_shift or "").strip(), entered_by))
    return True, f"Panne/arr\u00eat enregistr\u00e9 pour {machine_id} ({shift}) \u2014 {dur} h d'impact.", {"duration_hours": dur}


def get_shift_incidents(tenant_id, machine_id=None, day=None, shift=None, limit=100):
    """Historique des pannes/arrêts, du plus récent au plus ancien."""
    with get_connection(tenant_id) as conn:
        cur = conn.cursor()
        q = "SELECT * FROM shift_incidents WHERE 1=1"
        p = []
        if machine_id:
            q += " AND machine_id = ?"; p.append(machine_id)
        if day:
            q += " AND entry_date = ?"; p.append(day)
        if shift and shift != "Tous":
            q += " AND shift = ?"; p.append(shift)
        q += " ORDER BY entry_date DESC, created_at DESC LIMIT ?"; p.append(limit)
        cur.execute(q, p)
        return [dict(r) for r in cur.fetchall()]


def get_incidents_daily_downtime(tenant_id, day_str):
    """Synthèse des arrêts d'un jour : nombre d'incidents + heures d'impact cumulées."""
    with get_connection(tenant_id) as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) n, COALESCE(SUM(duration_hours),0) h FROM shift_incidents WHERE entry_date = ?",
            (day_str,))
        r = cur.fetchone()
        return {"n": r["n"], "h": round(r["h"], 1)}
