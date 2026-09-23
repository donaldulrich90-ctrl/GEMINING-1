"""Connexion SQLite par tenant + schéma — porté depuis app.py (Streamlit).

Différence avec l'ancienne app : le tenant est passé en argument
(get_connection(tenant_id)) au lieu d'être lu dans st.session_state.
Le schéma et les fichiers .db restent 100 % compatibles.
"""
import os
import sqlite3
from contextlib import contextmanager

from . import storage


def init_database_at_path(db_path: str) -> None:
    """Initialise le schéma sur un fichier SQLite (sans ouvrir de connexion partagée)."""
    parent = os.path.dirname(db_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS machines (
                id TEXT PRIMARY KEY,
                model TEXT NOT NULL,
                type TEXT NOT NULL,
                capacity REAL DEFAULT 0,
                hourly_rate REAL DEFAULT 150,
                status TEXT DEFAULT 'Active',
                operator TEXT DEFAULT 'Non Assigné',
                engine_hours REAL DEFAULT 0,
                fuel_tank REAL DEFAULT 100,
                lat REAL DEFAULT 12.3,
                lon REAL DEFAULT -1.5,
                cycle INTEGER DEFAULT 0,
                production_tonnes REAL DEFAULT 0,
                breakdown_reason TEXT DEFAULT '',
                breakdown_time TEXT DEFAULT '',
                load_type TEXT DEFAULT 'N/A',
                load_time TEXT,
                destination TEXT DEFAULT '',
                alert_trigger INTEGER DEFAULT 0,
                h_jour REAL DEFAULT 0,
                h_semaine REAL DEFAULT 0,
                h_mois REAL DEFAULT 0,
                last_pm_hours REAL DEFAULT 0,
                next_pm_interval REAL DEFAULT 250,
                next_maintenance TEXT,
                cons_jour REAL DEFAULT 0,
                cons_mois REAL DEFAULT 0,
                cons_annee REAL DEFAULT 0,
                cons_total REAL DEFAULT 0,
                bucket_capacity_m3 REAL DEFAULT 0,
                blade_capacity_m3 REAL DEFAULT 0,
                operating_weight_t REAL DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS fuel_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                machine_id TEXT NOT NULL,
                date TEXT NOT NULL,
                litres REAL NOT NULL,
                price_per_liter_usd REAL NOT NULL,
                currency_used TEXT DEFAULT 'USD',
                original_price REAL DEFAULT 0,
                total_usd REAL NOT NULL,
                engine_hours_at_refuel REAL NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (machine_id) REFERENCES machines(id) ON DELETE CASCADE
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS maintenance_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                machine_id TEXT NOT NULL,
                maintenance_type TEXT NOT NULL,
                date_maintenance TEXT NOT NULL,
                mechanic_name TEXT,
                engine_hours_at_maintenance REAL DEFAULT 0,
                notes TEXT DEFAULT '',
                pieces_changed TEXT DEFAULT '[]',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (machine_id) REFERENCES machines(id) ON DELETE CASCADE
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS breakdowns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                machine_id TEXT NOT NULL,
                reason TEXT NOT NULL,
                breakdown_time TEXT NOT NULL,
                repair_time TEXT,
                mechanic_name TEXT,
                status TEXT DEFAULT 'En cours',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (machine_id) REFERENCES machines(id) ON DELETE CASCADE
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS manual_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                machine_id TEXT NOT NULL,
                shift TEXT NOT NULL,
                entry_date TEXT NOT NULL,
                hours_worked REAL DEFAULT 0,
                production_tonnes REAL DEFAULT 0,
                fuel_consumed REAL DEFAULT 0,
                fuel_price_usd REAL DEFAULT 1.5,
                update_period TEXT DEFAULT 'Journalière',
                revenue_jour REAL DEFAULT 0,
                revenue_hebdo REAL DEFAULT 0,
                revenue_mois REAL DEFAULT 0,
                cost_fuel REAL DEFAULT 0,
                profitability REAL DEFAULT 0,
                cycles_added REAL DEFAULT 0,
                cons_per_cycle REAL DEFAULT 0,
                cons_per_shift REAL DEFAULT 0,
                avg_cycle_time REAL DEFAULT 0,
                entered_by TEXT DEFAULT 'Système',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (machine_id) REFERENCES machines(id) ON DELETE CASCADE
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS part_life_tracking (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                machine_id TEXT NOT NULL,
                part_name TEXT NOT NULL,
                production_tonnes_at_pose REAL DEFAULT 0,
                engine_hours_at_pose REAL DEFAULT 0,
                pose_date TEXT NOT NULL,
                maintenance_ref TEXT DEFAULT '',
                notes TEXT DEFAULT '',
                created_by TEXT DEFAULT 'Système',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (machine_id) REFERENCES machines(id) ON DELETE CASCADE
            )
        """)
        for stmt in (
            "CREATE INDEX IF NOT EXISTS idx_fuel_machine ON fuel_logs(machine_id)",
            "CREATE INDEX IF NOT EXISTS idx_fuel_date ON fuel_logs(date)",
            "CREATE INDEX IF NOT EXISTS idx_maintenance_machine ON maintenance_logs(machine_id)",
            "CREATE INDEX IF NOT EXISTS idx_maintenance_date ON maintenance_logs(date_maintenance)",
            "CREATE INDEX IF NOT EXISTS idx_breakdown_machine ON breakdowns(machine_id)",
            "CREATE INDEX IF NOT EXISTS idx_manual_machine ON manual_entries(machine_id)",
            "CREATE INDEX IF NOT EXISTS idx_manual_date ON manual_entries(entry_date)",
            "CREATE INDEX IF NOT EXISTS idx_manual_shift ON manual_entries(shift)",
            "CREATE INDEX IF NOT EXISTS idx_plt_machine ON part_life_tracking(machine_id)",
            "CREATE INDEX IF NOT EXISTS idx_plt_part ON part_life_tracking(part_name)",
        ):
            cur.execute(stmt)
        conn.commit()
    finally:
        conn.close()


def _ensure_machines_extra_columns(conn) -> None:
    """Migrations progressives (colonnes ajoutées sans recréer la base)."""
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(machines)")
        have = {row[1] for row in cur.fetchall()}
        for col, stmt in (
            ("bucket_capacity_m3", "ALTER TABLE machines ADD COLUMN bucket_capacity_m3 REAL DEFAULT 0"),
            ("blade_capacity_m3", "ALTER TABLE machines ADD COLUMN blade_capacity_m3 REAL DEFAULT 0"),
            ("operating_weight_t", "ALTER TABLE machines ADD COLUMN operating_weight_t REAL DEFAULT 0"),
        ):
            if col not in have:
                cur.execute(stmt)
    except Exception:
        pass


def _ensure_shift_incidents_table(conn) -> None:
    """Crée la table des pannes/arrêts par shift (ingénierie) si absente.

    Table dédiée au suivi ingénierie : distincte de `breakdowns` (maintenance).
    Idempotent : exécuté à chaque connexion, y compris sur les bases existantes.
    """
    try:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS shift_incidents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                machine_id TEXT NOT NULL,
                entry_date TEXT NOT NULL,
                shift TEXT NOT NULL,
                incident_type TEXT DEFAULT 'Panne',
                start_time TEXT DEFAULT '',
                end_time TEXT DEFAULT '',
                duration_hours REAL DEFAULT 0,
                production_impact TEXT DEFAULT '',
                measures_next_shift TEXT DEFAULT '',
                entered_by TEXT DEFAULT 'Syst\u00e8me',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (machine_id) REFERENCES machines(id) ON DELETE CASCADE
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_incident_machine ON shift_incidents(machine_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_incident_date ON shift_incidents(entry_date)")
    except Exception:
        pass


@contextmanager
def get_connection(tenant_id: str):
    """Connexion SQLite du tenant. Crée le fichier + le schéma si absent."""
    db_path = storage.effective_db_path(tenant_id)
    parent = os.path.dirname(db_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    if not os.path.exists(db_path) or os.path.getsize(db_path) == 0:
        init_database_at_path(db_path)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
    except Exception:
        pass
    _ensure_machines_extra_columns(conn)
    _ensure_shift_incidents_table(conn)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
