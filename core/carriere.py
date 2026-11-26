"""Carrière (exploitation de granulats) — GEMining.

Type de mine distinct (≠ souterrain, ≠ ciel ouvert métallifère). Couvre la
chaîne : extraction (tirs d'abattage, volume BCM, explosif, gasoil) →
concassage (tout-venant → granulats par granulométrie) → stocks de granulats
(bilan entrées/sorties) → pesée / ventes (tickets bascule, bons de livraison)
→ pilotage (conso explosif & gasoil au m³, rapprochement production↔ventes,
alertes stock bas).

Données persistées par tenant dans tenant_data/<tid>/carriere/ :
  - production.json : tirs d'abattage / extraction
  - concassage.json : postes de concassage (production par granulométrie)
  - ventes.json     : tickets de pesée / ventes de granulats
  - config.json     : granulométries actives + seuils de stock bas

Volontairement autonome (JSON par tenant), comme les autres modules métier.
"""
import json
import os
import uuid
from datetime import date, datetime

from . import storage

# Granulométries courantes en carrière de granulats (concassés + sables).
GRANULOS_DEFAUT = [
    "0/4 (sable)",
    "4/8",
    "8/16",
    "16/25",
    "25/40",
    "Tout-venant",
]


def _dir(tid):
    d = os.path.join(storage.tenant_dir(tid), "carriere")
    os.makedirs(d, exist_ok=True)
    return d


def _load(tid, name, key):
    p = os.path.join(_dir(tid), name)
    if not os.path.isfile(p):
        return {key: []}
    try:
        with open(p, "r", encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) and key in d else {key: []}
    except (OSError, ValueError):
        return {key: []}


def _save(tid, name, data):
    p = os.path.join(_dir(tid), name)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _num(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


# --- Configuration (granulométries + seuils) -------------------------------
def load_config(tid):
    p = os.path.join(_dir(tid), "config.json")
    if not os.path.isfile(p):
        return {"granulos": list(GRANULOS_DEFAUT), "seuils": {}}
    try:
        with open(p, "r", encoding="utf-8") as f:
            d = json.load(f)
        if not isinstance(d, dict):
            raise ValueError
        d.setdefault("granulos", list(GRANULOS_DEFAUT))
        d.setdefault("seuils", {})
        return d
    except (OSError, ValueError):
        return {"granulos": list(GRANULOS_DEFAUT), "seuils": {}}


def save_config(tid, granulos=None, seuils=None):
    cfg = load_config(tid)
    if granulos is not None:
        cfg["granulos"] = [g.strip() for g in granulos if g and g.strip()] or list(GRANULOS_DEFAUT)
    if seuils is not None:
        cfg["seuils"] = {k: _num(v) for k, v in seuils.items() if _num(v) > 0}
    _save(tid, "config.json", cfg)
    return cfg


def granulos(tid):
    return load_config(tid)["granulos"]


# --- Extraction / tirs d'abattage ------------------------------------------
def load_production(tid):
    return _load(tid, "production.json", "production")["production"]


def add_production(tid, date_iso, front, volume_bcm, explosif_kg, gasoil_l, note, auteur):
    data = _load(tid, "production.json", "production")
    bcm = _num(volume_bcm)
    expl = _num(explosif_kg)
    data["production"].insert(0, {
        "id": uuid.uuid4().hex[:12],
        "date": date_iso or date.today().isoformat(),
        "front": front,
        "volumeBcm": bcm,
        "explosifKg": expl,
        "gasoilL": _num(gasoil_l),
        # Facteur de poudre = kg d'explosif par m³ abattu (BCM).
        "facteurPoudre": round(expl / bcm, 3) if bcm > 0 else 0.0,
        "note": note,
        "auteur": auteur,
        "createdAt": datetime.utcnow().isoformat(timespec="seconds") + "Z",
    })
    _save(tid, "production.json", data)
    return data["production"][0]


def delete_production(tid, rec_id):
    data = _load(tid, "production.json", "production")
    data["production"] = [r for r in data["production"] if r.get("id") != rec_id]
    _save(tid, "production.json", data)


# --- Concassage / traitement -----------------------------------------------
def load_concassage(tid):
    return _load(tid, "concassage.json", "concassage")["concassage"]


def add_concassage(tid, date_iso, tout_venant_t, temps_marche_h, par_granulo, note, auteur):
    """par_granulo : dict {granulométrie: tonnes produites}."""
    data = _load(tid, "concassage.json", "concassage")
    prod = {k: _num(v) for k, v in (par_granulo or {}).items() if _num(v) > 0}
    total = sum(prod.values())
    tv = _num(tout_venant_t)
    data["concassage"].insert(0, {
        "id": uuid.uuid4().hex[:12],
        "date": date_iso or date.today().isoformat(),
        "toutVenantT": tv,
        "tempsMarcheH": _num(temps_marche_h),
        "parGranulo": prod,
        "totalProduitT": round(total, 2),
        # Rendement = granulats produits / tout-venant alimenté.
        "rendementPct": round(total / tv * 100, 1) if tv > 0 else 0.0,
        "note": note,
        "auteur": auteur,
        "createdAt": datetime.utcnow().isoformat(timespec="seconds") + "Z",
    })
    _save(tid, "concassage.json", data)
    return data["concassage"][0]


def delete_concassage(tid, rec_id):
    data = _load(tid, "concassage.json", "concassage")
    data["concassage"] = [r for r in data["concassage"] if r.get("id") != rec_id]
    _save(tid, "concassage.json", data)


# --- Pesée / ventes --------------------------------------------------------
def load_ventes(tid):
    return _load(tid, "ventes.json", "ventes")["ventes"]


def add_vente(tid, date_iso, client, produit, tare_t, brut_t, prix_unitaire,
              bl_numero, note, auteur):
    """Ticket de bascule : net = brut - tare (en tonnes). Vente au poids."""
    data = _load(tid, "ventes.json", "ventes")
    brut = _num(brut_t)
    tare = _num(tare_t)
    net = max(brut - tare, 0.0)
    pu = _num(prix_unitaire)
    data["ventes"].insert(0, {
        "id": uuid.uuid4().hex[:12],
        "date": date_iso or date.today().isoformat(),
        "client": client,
        "produit": produit,
        "tareT": tare,
        "brutT": brut,
        "netT": round(net, 2),
        "prixUnitaire": pu,          # FCFA / tonne
        "montant": round(net * pu, 0),
        "blNumero": bl_numero,
        "note": note,
        "auteur": auteur,
        "createdAt": datetime.utcnow().isoformat(timespec="seconds") + "Z",
    })
    _save(tid, "ventes.json", data)
    return data["ventes"][0]


def delete_vente(tid, rec_id):
    data = _load(tid, "ventes.json", "ventes")
    data["ventes"] = [r for r in data["ventes"] if r.get("id") != rec_id]
    _save(tid, "ventes.json", data)


# --- Stocks de granulats (bilan entrées / sorties) -------------------------
def stocks(tid):
    """Stock par granulométrie = cumul concassage (entrées) − ventes (sorties).

    Calcul sur tout l'historique (le stock est un cumul, pas un flux mensuel).
    """
    cfg = load_config(tid)
    gl = list(cfg["granulos"])
    seuils = cfg.get("seuils", {})
    entrees = {g: 0.0 for g in gl}
    for c in load_concassage(tid):
        for g, t in (c.get("parGranulo") or {}).items():
            entrees[g] = entrees.get(g, 0.0) + _num(t)
    sorties = {g: 0.0 for g in gl}
    for v in load_ventes(tid):
        g = v.get("produit") or ""
        sorties[g] = sorties.get(g, 0.0) + _num(v.get("netT"))
    rows = []
    for g in sorted(set(list(entrees) + list(sorties)), key=lambda x: (x not in gl, x)):
        e = entrees.get(g, 0.0)
        s = sorties.get(g, 0.0)
        stock = e - s
        seuil = _num(seuils.get(g))
        rows.append({
            "granulo": g,
            "entrees": round(e, 2),
            "sorties": round(s, 2),
            "stock": round(stock, 2),
            "seuil": seuil,
            "bas": seuil > 0 and stock < seuil,
        })
    return rows


# --- Synthèse / pilotage ---------------------------------------------------
def summary(tid, month=None):
    def _m(recs):
        return [r for r in recs if not month or str(r.get("date", ""))[:7] == month]

    prod = _m(load_production(tid))
    conc = _m(load_concassage(tid))
    vts = _m(load_ventes(tid))

    tot_bcm = sum(_num(r.get("volumeBcm")) for r in prod)
    tot_expl = sum(_num(r.get("explosifKg")) for r in prod)
    tot_gasoil = sum(_num(r.get("gasoilL")) for r in prod)

    tot_tv = sum(_num(r.get("toutVenantT")) for r in conc)
    tot_produit = sum(_num(r.get("totalProduitT")) for r in conc)
    tot_marche = sum(_num(r.get("tempsMarcheH")) for r in conc)

    tot_vendu = sum(_num(r.get("netT")) for r in vts)
    ca = sum(_num(r.get("montant")) for r in vts)

    st = stocks(tid)
    alertes = []
    for s in st:
        if s["bas"]:
            alertes.append(f"Stock bas {s['granulo']} : {s['stock']:.0f} t (seuil {s['seuil']:.0f} t)")
    # Écart production concassée vs ventes (sur la période) — indicatif.
    ecart = tot_produit - tot_vendu

    return {
        # Extraction
        "totalBcm": round(tot_bcm, 1),
        "totalExplosifKg": round(tot_expl, 1),
        "totalGasoilL": round(tot_gasoil, 1),
        "facteurPoudre": round(tot_expl / tot_bcm, 3) if tot_bcm > 0 else 0.0,
        "gasoilParBcm": round(tot_gasoil / tot_bcm, 2) if tot_bcm > 0 else 0.0,
        # Concassage
        "totalToutVenantT": round(tot_tv, 1),
        "totalProduitT": round(tot_produit, 1),
        "rendementPct": round(tot_produit / tot_tv * 100, 1) if tot_tv > 0 else 0.0,
        "tempsMarcheH": round(tot_marche, 1),
        # Ventes
        "totalVenduT": round(tot_vendu, 1),
        "ca": round(ca, 0),
        "nbTickets": len(vts),
        # Pilotage
        "ecartProdVenteT": round(ecart, 1),
        "stocks": st,
        "alertes": alertes,
    }
