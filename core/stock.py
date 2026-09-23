"""Gestion de stock (pièces de rechange) — porté depuis app.py, persisté JSON.

L'ancienne app gardait le stock en mémoire. Ici il est persisté dans
tenant_data/<tid>/stock.json (niveaux + mouvements).
"""
from datetime import date, datetime

from . import storage

DEFAULT_PARTS = [
    {"nom": "Filtre à huile moteur", "cout": 25.0, "categorie": "Filtres"},
    {"nom": "Filtre à air", "cout": 45.0, "categorie": "Filtres"},
    {"nom": "Filtre à carburant", "cout": 30.0, "categorie": "Filtres"},
    {"nom": "Filtre hydraulique", "cout": 55.0, "categorie": "Filtres"},
    {"nom": "Huile moteur (L)", "cout": 12.0, "categorie": "Lubrifiants"},
    {"nom": "Huile hydraulique (L)", "cout": 15.0, "categorie": "Lubrifiants"},
    {"nom": "Graisse (kg)", "cout": 8.0, "categorie": "Lubrifiants"},
    {"nom": "Pneu avant", "cout": 850.0, "categorie": "Pneus"},
    {"nom": "Pneu arrière", "cout": 1200.0, "categorie": "Pneus"},
    {"nom": "Courroie de distribution", "cout": 120.0, "categorie": "Transmission"},
    {"nom": "Joint de culasse", "cout": 200.0, "categorie": "Moteur"},
    {"nom": "Injecteur", "cout": 450.0, "categorie": "Moteur"},
    {"nom": "Pompe à eau", "cout": 380.0, "categorie": "Moteur"},
    {"nom": "Alternateur", "cout": 850.0, "categorie": "Électrique"},
    {"nom": "Démarreur", "cout": 650.0, "categorie": "Électrique"},
    {"nom": "Batterie", "cout": 320.0, "categorie": "Électrique"},
    {"nom": "Freins plaquettes", "cout": 180.0, "categorie": "Freinage"},
    {"nom": "Disque de frein", "cout": 280.0, "categorie": "Freinage"},
]


def catalog_names():
    return [p["nom"] for p in DEFAULT_PARTS]


class StockStore:
    def __init__(self, tenant_id="default"):
        self.tenant_id = tenant_id
        data = storage.load_tenant_json(tenant_id, "stock.json", {"levels": {}, "movements": []})
        self.levels = data.get("levels", {})
        self.movements = data.get("movements", [])

    def save(self):
        storage.save_tenant_json(self.tenant_id, "stock.json",
                                 {"levels": self.levels, "movements": self.movements})

    def initialize(self, part_name, qty=0, seuil_min=5, unite="unité"):
        if part_name not in self.levels:
            self.levels[part_name] = {"quantite": qty, "seuil_min": seuil_min, "unite": unite}

    def set_level(self, part_name, qty, seuil_min=None, unite=None):
        self.initialize(part_name)
        self.levels[part_name]["quantite"] = qty
        if seuil_min is not None:
            self.levels[part_name]["seuil_min"] = seuil_min
        if unite:
            self.levels[part_name]["unite"] = unite
        self.save()

    def add_entry(self, part_name, qty, reference="", notes="", who=""):
        self.initialize(part_name)
        self.levels[part_name]["quantite"] += qty
        self._log("ENTREE", part_name, qty, reference, notes, who)
        self.save()
        return True

    def remove_entry(self, part_name, qty, reference="", notes="", who=""):
        self.initialize(part_name)
        if self.levels[part_name]["quantite"] < qty:
            return False
        self.levels[part_name]["quantite"] -= qty
        self._log("SORTIE", part_name, qty, reference, notes, who)
        self.save()
        return True

    def _log(self, mtype, part_name, qty, reference, notes, who):
        self.movements.insert(0, {
            "type": mtype, "piece": part_name, "quantite": qty,
            "date": date.today().strftime("%Y-%m-%d"), "heure": datetime.now().strftime("%H:%M"),
            "reference": reference, "notes": notes, "par": who,
        })
        self.movements = self.movements[:500]

    def get_low_stock_items(self):
        low = []
        for name, info in self.levels.items():
            if info["quantite"] <= info["seuil_min"]:
                low.append({"nom": name, "quantite": info["quantite"],
                            "seuil_min": info["seuil_min"], "unite": info.get("unite", "unité")})
        return low

    def rows(self):
        out = []
        for name, info in sorted(self.levels.items()):
            out.append({"nom": name, "quantite": info["quantite"], "seuil_min": info["seuil_min"],
                        "unite": info.get("unite", "unité"),
                        "bas": info["quantite"] <= info["seuil_min"]})
        return out
