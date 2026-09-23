"""Flotte, machines, stock et maintenance — porté depuis app.py (Streamlit).

Le tenant est passé à FleetManager(tenant_id) au lieu d'être lu dans la session.
Le récapitulatif flotte reproduit get_summary_dataframe() en listes de dicts
(pas de pandas), avec les mêmes clés de colonnes qu'avant.
"""
from datetime import date, datetime

from .db import get_connection


# ---------------------------------------------------------------------------
# Machine
# ---------------------------------------------------------------------------
class Machine:
    def __init__(self, id, model, m_type, capacity, hourly_rate=150, initial_hours=0, tenant_id="default"):
        self.tenant_id = tenant_id
        self.id = id
        self.model = model
        self.type = m_type
        self.capacity = capacity
        self.hourly_rate = hourly_rate
        self.status = "Active"
        self.operator = "Non Assigné"
        self.cycle = 0
        self.production_tonnes = 0
        self.breakdown_reason = ""
        self.breakdown_time = ""
        self.load_type = "N/A"
        self.load_time = None
        self.destination = ""
        self.alert_trigger = False
        self.engine_hours = initial_hours
        self.h_jour = 0
        self.h_semaine = 0
        self.h_mois = 0
        self.last_pm_hours = 0
        self.next_pm_interval = 250
        self.next_maintenance = None
        self.fuel_tank = 0
        self.fuel_logs = []
        self.cons_jour = 0
        self.cons_mois = 0
        self.cons_annee = 0
        self.cons_total = 0
        self.lat = 12.3
        self.lon = -1.5
        self.bucket_capacity_m3 = 0.0
        self.blade_capacity_m3 = 0.0
        self.operating_weight_t = 0.0

    def _apply_row_from_sqlite(self, row):
        self.model = row["model"]
        self.type = row["type"]
        self.capacity = row["capacity"]
        self.hourly_rate = row["hourly_rate"]
        self.status = row["status"]
        self.operator = row["operator"]
        self.engine_hours = row["engine_hours"]
        self.fuel_tank = row["fuel_tank"]
        self.lat = row["lat"]
        self.lon = row["lon"]
        self.cycle = row["cycle"]
        self.production_tonnes = row["production_tonnes"]
        self.breakdown_reason = row["breakdown_reason"]
        self.breakdown_time = row["breakdown_time"]
        self.load_type = row["load_type"]
        self.load_time = (
            datetime.strptime(row["load_time"], "%Y-%m-%d %H:%M:%S")
            if row["load_time"] else None
        )
        self.destination = row["destination"]
        self.alert_trigger = bool(row["alert_trigger"])
        self.h_jour = row["h_jour"]
        self.h_semaine = row["h_semaine"]
        self.h_mois = row["h_mois"]
        self.last_pm_hours = row["last_pm_hours"]
        self.next_pm_interval = row["next_pm_interval"]
        self.next_maintenance = (
            datetime.strptime(row["next_maintenance"], "%Y-%m-%d").date()
            if row["next_maintenance"] else None
        )
        self.cons_jour = row["cons_jour"]
        self.cons_mois = row["cons_mois"]
        self.cons_annee = row["cons_annee"]
        self.cons_total = row["cons_total"]
        rk = row.keys()
        self.bucket_capacity_m3 = float(row["bucket_capacity_m3"] or 0) if "bucket_capacity_m3" in rk else 0.0
        self.blade_capacity_m3 = float(row["blade_capacity_m3"] or 0) if "blade_capacity_m3" in rk else 0.0
        self.operating_weight_t = float(row["operating_weight_t"] or 0) if "operating_weight_t" in rk else 0.0

    def get_maintenance_status(self):
        return self.next_pm_interval - (self.engine_hours - self.last_pm_hours)

    # -- écritures SQLite (portées depuis app.py) --------------------------
    def save_to_db(self):
        from datetime import datetime as _dt
        with get_connection(self.tenant_id) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO machines
                (id, model, type, capacity, hourly_rate, status, operator, engine_hours, fuel_tank,
                 lat, lon, cycle, production_tonnes, breakdown_reason, breakdown_time, load_type,
                 load_time, destination, alert_trigger, h_jour, h_semaine, h_mois, last_pm_hours,
                 next_pm_interval, next_maintenance, cons_jour, cons_mois, cons_annee, cons_total,
                 bucket_capacity_m3, blade_capacity_m3, operating_weight_t, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                self.id, self.model, self.type, self.capacity, self.hourly_rate, self.status, self.operator,
                self.engine_hours, self.fuel_tank, self.lat, self.lon, self.cycle, self.production_tonnes,
                self.breakdown_reason, self.breakdown_time, self.load_type,
                str(self.load_time) if self.load_time else None, self.destination,
                1 if self.alert_trigger else 0, self.h_jour, self.h_semaine, self.h_mois,
                self.last_pm_hours, self.next_pm_interval,
                self.next_maintenance.strftime("%Y-%m-%d") if self.next_maintenance else None,
                self.cons_jour, self.cons_mois, self.cons_annee, self.cons_total,
                float(getattr(self, "bucket_capacity_m3", 0) or 0),
                float(getattr(self, "blade_capacity_m3", 0) or 0),
                float(getattr(self, "operating_weight_t", 0) or 0),
                _dt.now().strftime("%Y-%m-%d %H:%M:%S"),
            ))

    def add_fuel(self, liters, price_per_liter_usd, currency_used="USD", original_price=0):
        from datetime import datetime as _dt
        fuel_date = _dt.now().strftime("%Y-%m-%d %H:%M:%S")
        total_usd = liters * price_per_liter_usd
        with get_connection(self.tenant_id) as conn:
            conn.execute("""
                INSERT INTO fuel_logs
                (machine_id, date, litres, price_per_liter_usd, currency_used, original_price, total_usd, engine_hours_at_refuel)
                VALUES (?,?,?,?,?,?,?,?)
            """, (self.id, fuel_date, liters, price_per_liter_usd, currency_used, original_price, total_usd, self.engine_hours))
        self.fuel_tank = 100
        self.save_to_db()

    def get_fuel_logs_from_db(self):
        with get_connection(self.tenant_id) as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT date, litres, price_per_liter_usd, currency_used, original_price, total_usd, engine_hours_at_refuel
                FROM fuel_logs WHERE machine_id = ? ORDER BY date DESC
            """, (self.id,))
            return [dict(r) for r in cur.fetchall()]


# ---------------------------------------------------------------------------
# Stock & maintenance (en mémoire, comme dans l'ancienne app)
# ---------------------------------------------------------------------------
class StockManager:
    def __init__(self):
        self.stock_levels = {}
        self.movements = []

    def initialize_stock(self, part_name, initial_quantity=0, seuil_min=5, unite="unité"):
        if part_name not in self.stock_levels:
            self.stock_levels[part_name] = {
                "quantite": initial_quantity, "seuil_min": seuil_min, "unite": unite,
            }

    def set_stock_level(self, part_name, quantity, seuil_min=None):
        if part_name not in self.stock_levels:
            self.initialize_stock(part_name)
        self.stock_levels[part_name]["quantite"] = quantity
        if seuil_min is not None:
            self.stock_levels[part_name]["seuil_min"] = seuil_min

    def get_stock_level(self, part_name):
        return self.stock_levels.get(
            part_name, {"quantite": 0, "seuil_min": 5, "unite": "unité"}
        )

    def get_low_stock_items(self):
        low = []
        for name, info in self.stock_levels.items():
            if info["quantite"] <= info["seuil_min"]:
                low.append({
                    "nom": name, "quantite": info["quantite"],
                    "seuil_min": info["seuil_min"], "unite": info.get("unite", "unité"),
                })
        return low


class MaintenanceAlert:
    def __init__(self, machine_id, planned_date, maintenance_type, created_by):
        self.machine_id = machine_id
        self.planned_date = planned_date
        self.maintenance_type = maintenance_type
        self.created_by = created_by
        self.created_at = datetime.now()
        self.acknowledged_by = []
        self.status = "Planifiée"


class MaintenanceManager:
    def __init__(self):
        self.maintenance_records = []
        self.active_alerts = []
        self.stock_manager = StockManager()

    def create_maintenance_alert(self, machine_id, planned_date, maintenance_type, created_by):
        alert = MaintenanceAlert(machine_id, planned_date, maintenance_type, created_by)
        self.active_alerts.append(alert)
        return alert

    def get_all_active_alerts(self):
        return [a for a in self.active_alerts if a.status == "Planifiée"]


# ---------------------------------------------------------------------------
# FleetManager
# ---------------------------------------------------------------------------
class FleetManager:
    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id
        self.maintenance_manager = MaintenanceManager()
        self.machines = self.load_machines_from_db()

    def load_machines_from_db(self):
        machines = []
        with get_connection(self.tenant_id) as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM machines ORDER BY id")
            rows = cur.fetchall()
            if not rows:
                return []
            ids = [r["id"] for r in rows]
            fuel_by_mid = {mid: [] for mid in ids}
            placeholders = ",".join("?" * len(ids))
            cur.execute(
                f"""SELECT machine_id, date, litres, price_per_liter_usd, currency_used,
                           original_price, total_usd, engine_hours_at_refuel
                    FROM fuel_logs WHERE machine_id IN ({placeholders})
                    ORDER BY machine_id, date DESC""",
                ids,
            )
            for frow in cur.fetchall():
                fuel_by_mid.setdefault(frow["machine_id"], []).append({
                    "Date": frow["date"], "Litres": frow["litres"],
                    "Prix Unitaire ($)": frow["price_per_liter_usd"],
                    "Devise Origine": frow["currency_used"],
                    "Prix Origine": frow["original_price"],
                    "Total ($)": frow["total_usd"],
                    "H-Mètre": frow["engine_hours_at_refuel"],
                })
            for row in rows:
                m = Machine(row["id"], row["model"], row["type"], row["capacity"],
                            row["hourly_rate"], row["engine_hours"], tenant_id=self.tenant_id)
                m._apply_row_from_sqlite(row)
                m.fuel_logs = fuel_by_mid.get(row["id"], [])
                machines.append(m)
        return machines

    def get(self, machine_id):
        return next((m for m in self.machines if m.id == machine_id), None)

    # -- écritures flotte (portées depuis app.py) -------------------------
    def add_machine(self, id, model, m_type, capacity, hourly_rate=150):
        if any(m.id == id for m in self.machines):
            return False
        m = Machine(id, model, m_type, capacity, hourly_rate, tenant_id=self.tenant_id)
        m.save_to_db()
        self.machines.append(m)
        return True

    def remove_machine(self, id):
        with get_connection(self.tenant_id) as conn:
            conn.execute("DELETE FROM machines WHERE id = ?", (id,))
        self.machines = [m for m in self.machines if m.id != id]

    def report_breakdown(self, machine_id, reason):
        from datetime import datetime as _dt
        bt = _dt.now().strftime("%Y-%m-%d %H:%M:%S")
        m = self.get(machine_id)
        if not m:
            return False
        m.status = "Panne"
        m.breakdown_reason = reason
        m.breakdown_time = bt
        m.load_time = None
        m.save_to_db()
        with get_connection(self.tenant_id) as conn:
            conn.execute(
                "INSERT INTO breakdowns (machine_id, reason, breakdown_time, status) VALUES (?,?,?, 'En cours')",
                (machine_id, reason, bt),
            )
        return True

    def repair_machine(self, machine_id, mechanic_name=None, notes=""):
        from datetime import datetime as _dt, date as _date
        rt = _dt.now().strftime("%Y-%m-%d %H:%M:%S")
        m = self.get(machine_id)
        if not m:
            return False
        m.status = "Active"
        m.breakdown_reason = ""
        m.alert_trigger = False
        m.save_to_db()
        with get_connection(self.tenant_id) as conn:
            conn.execute("""
                UPDATE breakdowns SET status='Réparé', repair_time=?, mechanic_name=?
                WHERE id = (SELECT id FROM breakdowns WHERE machine_id=? AND status='En cours' ORDER BY id DESC LIMIT 1)
            """, (rt, mechanic_name, machine_id))
        if mechanic_name:
            self._save_maintenance_to_db(machine_id, "Réparation", _date.today(), mechanic_name, m.engine_hours, notes)
        return True

    def set_maintenance_date(self, machine_id, date_obj, maintenance_type="Maintenance préventive", created_by="Système"):
        m = self.get(machine_id)
        if not m:
            return False
        m.next_maintenance = date_obj
        m.save_to_db()
        self.maintenance_manager.create_maintenance_alert(machine_id, date_obj, maintenance_type, created_by)
        return True

    def do_maintenance_pm(self, machine_id, maintenance_type="PM 250h", mechanic_name=None, notes=""):
        from datetime import date as _date
        m = self.get(machine_id)
        if not m:
            return False
        m.last_pm_hours = m.engine_hours
        m.status = "Active"
        m.save_to_db()
        if mechanic_name:
            self._save_maintenance_to_db(machine_id, maintenance_type, _date.today(), mechanic_name, m.engine_hours, notes)
        return True

    def _save_maintenance_to_db(self, machine_id, mtype, dt, mechanic_name, engine_hours, notes):
        with get_connection(self.tenant_id) as conn:
            conn.execute("""
                INSERT INTO maintenance_logs
                (machine_id, maintenance_type, date_maintenance, mechanic_name, engine_hours_at_maintenance, notes, pieces_changed)
                VALUES (?,?,?,?,?,?, '[]')
            """, (machine_id, mtype, dt.strftime("%Y-%m-%d"), mechanic_name, engine_hours, notes))

    def get_maintenance_history(self, limit=100):
        with get_connection(self.tenant_id) as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT machine_id, maintenance_type, date_maintenance, mechanic_name,
                       engine_hours_at_maintenance, notes
                FROM maintenance_logs ORDER BY date_maintenance DESC, id DESC LIMIT ?
            """, (limit,))
            return [dict(r) for r in cur.fetchall()]

    def get_summary_rows(self):
        """Reproduit get_summary_dataframe() sous forme de liste de dicts."""
        data = []
        today = date.today()
        fuel_price_avg = 1.5
        for m in self.machines:
            alert_msg = "OK"
            if m.next_maintenance:
                delta = (m.next_maintenance - today).days
                if delta < 0:
                    alert_msg = "⚠️ RETARD"
                elif delta <= 7:
                    alert_msg = f"⚠️ J-{delta}"
                else:
                    alert_msg = f"Prévu: {m.next_maintenance}"

            h_restantes = m.get_maintenance_status()
            pm_status = f"OK ({int(h_restantes)}h)" if h_restantes > 0 else "⚠️ DUE"

            cons_par_cycle = m.cons_jour / m.cycle if m.cycle > 0 else 0
            cons_par_shift = m.cons_jour / 3
            revenu_total = m.h_jour * m.hourly_rate
            cout_total = m.cons_jour * fuel_price_avg
            rentabilite = revenu_total - cout_total
            revenu_hebdo = m.h_semaine * m.hourly_rate
            revenu_mensuel = m.h_mois * m.hourly_rate
            avg_cycle = round((m.h_jour * 60) / m.cycle, 1) if m.cycle > 0 else 0

            data.append({
                "ID": m.id, "Type": m.type, "Modèle": m.model, "Statut": m.status,
                "Opérateur": m.operator, "Production (T)": int(m.production_tonnes),
                "Cycles": m.cycle, "Tps Cycle Moy (min)": avg_cycle,
                "Prochaine PM": pm_status, "Maint. Date": alert_msg,
                "Carburant (%)": int(m.fuel_tank),
                "H. Total": int(m.engine_hours), "H. Run Jour": m.h_jour,
                "H. Run Hebdo": m.h_semaine, "H. Run Mois": m.h_mois,
                "Conso. Jour (L)": int(m.cons_jour), "Conso. Shift (L)": int(cons_par_shift),
                "Conso. Voyage (L)": round(cons_par_cycle, 1),
                "Conso. Mois (L)": int(m.cons_mois), "Conso. An (L)": int(m.cons_annee),
                "Rev. Jour ($)": int(revenu_total), "Rev. Hebdo ($)": int(revenu_hebdo),
                "Rev. Mensuel ($)": int(revenu_mensuel), "Coût Fuel ($)": int(cout_total),
                "Rentabilité ($)": int(rentabilite), "lat": m.lat, "lon": m.lon,
            })
        return data


# ---------------------------------------------------------------------------
# Agrégations dashboard (équivalents des helpers _fleet_* de l'ancienne app)
# ---------------------------------------------------------------------------
def statut_count(rows, statut):
    return sum(1 for r in rows if r.get("Statut") == statut)


def col_sum_int(rows, col):
    total = 0
    for r in rows:
        try:
            total += int(float(r.get(col, 0) or 0))
        except (TypeError, ValueError):
            pass
    return total


def col_mean(rows, col):
    vals = []
    for r in rows:
        try:
            vals.append(float(r.get(col, 0) or 0))
        except (TypeError, ValueError):
            pass
    return round(sum(vals) / len(vals), 1) if vals else 0
