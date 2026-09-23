"""Gestion financière — contrats miniers, revenus, profil entreprise, factures.

Porté depuis app.py. Améliorations :
  - les contrats sont persistés (tenant_data/<tid>/finance_contracts.json) —
    l'ancienne app les gardait en mémoire ;
  - le profil entreprise réutilise le MÊME fichier que l'ancienne app
    (tenant_data/<tid>/branding/finance_company_profile.json) → compatible.
"""
import json
import os
from datetime import date, datetime

from . import storage
from .db import get_connection
from .market import get_exchange_rates

TONNES_TO_BCM = 0.7

_COMPANY_FIELDS = ["company_name", "address", "phone", "email", "tax_id", "rccm",
                   "bank_info", "signatory_title", "signatory_name", "document_stamp_legend"]


class CompanyInfo:
    def __init__(self):
        self.company_name = "GOOD ENGINEERS"
        self.address = ""
        self.phone = ""
        self.email = ""
        self.tax_id = ""
        self.rccm = ""
        self.bank_info = ""
        self.signatory_title = ""
        self.signatory_name = ""
        self.document_stamp_legend = ""
        self.logo_base64 = None
        self.logo_mime = "image/png"


def _company_profile_path(tid):
    return os.path.join(storage.tenant_dir(tid), "branding", "finance_company_profile.json")


def load_company(tid):
    ci = CompanyInfo()
    p = _company_profile_path(tid)
    if os.path.isfile(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                d = json.load(f)
            for k in _COMPANY_FIELDS + ["logo_base64", "logo_mime"]:
                if d.get(k) is not None:
                    setattr(ci, k, d[k])
        except (OSError, ValueError):
            pass
    return ci


def save_company(ci, tid):
    p = _company_profile_path(tid)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    d = {k: getattr(ci, k, "") for k in _COMPANY_FIELDS}
    d["logo_base64"] = ci.logo_base64
    d["logo_mime"] = ci.logo_mime
    with open(p, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)


class MiningContract:
    def __init__(self, contract_id, name, contract_type, rate, somme_negociee=None,
                 client_name=None, rate_currency="USD", original_rate=None, active=True,
                 machines_ids=None):
        self.contract_id = contract_id
        self.name = name
        self.contract_type = contract_type  # "BCM" | "HOURLY"
        self.rate = rate                     # taux USD (calculs internes)
        self.rate_currency = rate_currency
        self.original_rate = original_rate if original_rate is not None else rate
        self.somme_negociee = somme_negociee
        self.client_name = client_name
        self.active = active
        self.machines_ids = machines_ids or []
        self.tonnes_to_bcm_factor = TONNES_TO_BCM
        for a in ("volume_jour", "volume_semaine", "volume_mois", "volume_annee",
                  "heures_jour", "heures_semaine", "heures_mois", "heures_annee",
                  "revenu_jour", "revenu_semaine", "revenu_mois", "revenu_annee"):
            setattr(self, a, 0)

    def recalculate_revenue(self):
        if self.contract_type == "BCM":
            self.revenu_jour = self.volume_jour * self.rate
            self.revenu_semaine = self.volume_semaine * self.rate
            self.revenu_mois = self.volume_mois * self.rate
            self.revenu_annee = self.volume_annee * self.rate
        else:
            self.revenu_jour = self.heures_jour * self.rate
            self.revenu_semaine = self.heures_semaine * self.rate
            self.revenu_mois = self.heures_mois * self.rate
            self.revenu_annee = self.heures_annee * self.rate

    def to_dict(self):
        return {"contract_id": self.contract_id, "name": self.name,
                "contract_type": self.contract_type, "rate": self.rate,
                "rate_currency": self.rate_currency, "original_rate": self.original_rate,
                "somme_negociee": self.somme_negociee, "client_name": self.client_name,
                "active": self.active, "machines_ids": self.machines_ids}

    @classmethod
    def from_dict(cls, d):
        return cls(d["contract_id"], d["name"], d["contract_type"], d["rate"],
                   d.get("somme_negociee"), d.get("client_name"),
                   d.get("rate_currency", "USD"), d.get("original_rate"),
                   d.get("active", True), d.get("machines_ids"))


def _to_usd(rate, currency, rates):
    if currency == "EUR" and rates.get("EUR"):
        return rate / rates["EUR"]
    if currency == "CFA" and rates.get("CFA"):
        return rate / rates["CFA"]
    return rate


class ContractManager:
    def __init__(self, tenant_id="default"):
        self.tenant_id = storage.safe_tenant_id(tenant_id)
        self.company_info = load_company(self.tenant_id)
        raw = storage.load_tenant_json(self.tenant_id, "finance_contracts.json", None)
        if raw is None:
            self.contracts = [
                MiningContract("CONT-001", "Contrat Mine A - BCM", "BCM", 15.0, 500000.0, "Mine A"),
                MiningContract("CONT-002", "Contrat Mine B - Horaires", "HOURLY", 200.0, 1200000.0, "Mine B"),
            ]
            self.save()
        else:
            self.contracts = [MiningContract.from_dict(d) for d in raw]

    def save(self):
        storage.save_tenant_json(self.tenant_id, "finance_contracts.json",
                                 [c.to_dict() for c in self.contracts])

    def get_contract(self, cid):
        return next((c for c in self.contracts if c.contract_id == cid), None)

    def add_contract(self, cid, name, ctype, rate, currency="USD", somme=None, client=None):
        if self.get_contract(cid):
            return False
        rates = get_exchange_rates()
        rate_usd = _to_usd(rate, currency, rates)
        self.contracts.append(MiningContract(cid, name, ctype, rate_usd, somme, client, currency, rate))
        self.save()
        return True

    def update_rate(self, cid, new_rate, currency="USD"):
        c = self.get_contract(cid)
        if not c:
            return False
        rates = get_exchange_rates()
        c.rate = _to_usd(new_rate, currency, rates)
        c.original_rate = new_rate
        c.rate_currency = currency
        self.save()
        return True

    def toggle_active(self, cid):
        c = self.get_contract(cid)
        if c:
            c.active = not c.active
            self.save()
            return True
        return False

    def update_from_fleet(self, fleet_manager):
        """Recalcule volumes/heures/revenus depuis la flotte (non persisté — dérivé)."""
        for c in self.contracts:
            if not c.active:
                continue
            for a in ("volume_jour", "volume_semaine", "volume_mois", "volume_annee",
                      "heures_jour", "heures_semaine", "heures_mois", "heures_annee"):
                setattr(c, a, 0)
            if c.machines_ids:
                machines = [m for m in fleet_manager.machines if m.id in c.machines_ids]
            else:
                machines = [m for m in fleet_manager.machines if m.status == "Active"]
            for m in machines:
                if c.contract_type == "BCM":
                    eh = max(1, m.engine_hours)
                    if m.cycle > 0 and m.engine_hours > 0:
                        c.volume_jour += (m.production_tonnes * m.h_jour) / eh * c.tonnes_to_bcm_factor
                        c.volume_semaine += (m.production_tonnes * m.h_semaine) / eh * c.tonnes_to_bcm_factor
                        c.volume_mois += (m.production_tonnes * m.h_mois) / eh * c.tonnes_to_bcm_factor
                        c.volume_annee += m.production_tonnes * c.tonnes_to_bcm_factor
                else:
                    c.heures_jour += m.h_jour
                    c.heures_semaine += m.h_semaine
                    c.heures_mois += m.h_mois
                    c.heures_annee += m.h_mois
            c.recalculate_revenue()

    def revenue_summary(self):
        act = [c for c in self.contracts if c.active]
        return {
            "jour": sum(c.revenu_jour for c in act),
            "semaine": sum(c.revenu_semaine for c in act),
            "mois": sum(c.revenu_mois for c in act),
            "annee": sum(c.revenu_annee for c in act),
        }


def collect_fuel_expenses(tenant_id, start_date, end_date):
    """Dépenses carburant sur une période : fuel_logs + manual_entries."""
    sd, ed = start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")

    def _pd(v):
        s = str(v or "")
        try:
            return datetime.strptime(s.split()[0] if " " in s else s[:10], "%Y-%m-%d").date()
        except (ValueError, IndexError):
            return None

    total = 0.0
    rows = []
    with get_connection(tenant_id) as conn:
        cur = conn.cursor()
        cur.execute("SELECT machine_id, date, litres, total_usd FROM fuel_logs "
                    "WHERE date(date) >= date(?) AND date(date) <= date(?) ORDER BY date", (sd, ed))
        for r in cur.fetchall():
            d = _pd(r["date"])
            if d is None or not (start_date <= d <= end_date):
                continue
            cost = float(r["total_usd"] or 0)
            total += cost
            rows.append({"machine": r["machine_id"], "date": d.strftime("%d/%m/%Y"),
                         "liters": float(r["litres"] or 0), "cost": cost, "source": "Ravitaillement"})
        cur.execute("SELECT machine_id, entry_date, shift, fuel_consumed, fuel_price_usd FROM manual_entries "
                    "WHERE entry_date >= ? AND entry_date <= ? AND COALESCE(fuel_consumed,0) > 0 "
                    "ORDER BY entry_date", (sd, ed))
        for r in cur.fetchall():
            d = _pd(r["entry_date"])
            if d is None or not (start_date <= d <= end_date):
                continue
            liters = float(r["fuel_consumed"] or 0)
            cost = liters * float(r["fuel_price_usd"] or 0)
            total += cost
            rows.append({"machine": r["machine_id"], "date": d.strftime("%d/%m/%Y"), "liters": liters,
                         "cost": cost, "source": f"Ingénierie ({r['shift']})" if r["shift"] else "Ingénierie"})
    rows.sort(key=lambda x: x["date"])
    return total, rows
