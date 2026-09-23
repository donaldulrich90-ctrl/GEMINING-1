"""Gestion du personnel (RH) — porté depuis app.py, avec persistance JSON.

L'ancienne app gardait le personnel en mémoire (perdu au redémarrage). Ici il
est persisté dans tenant_data/<tid>/staff.json — une amélioration.
"""
import random
from datetime import date, datetime, timedelta

from . import storage

ROLES_RH = ["Operateur", "Superviseur Production", "Superviseur Mecanicien",
            "Ingenieur", "Mecanicien", "Electricien"]
SHIFTS = ["Standard", "3x8", "2x12", "Jour", "Nuit"]


class Employee:
    def __init__(self, name, role, team, shift_type="Standard", matricule=None,
                 date_arrivee=None, statut="Actif", date_depart=None):
        self.matricule = matricule or f"MAT-{random.randint(1000, 9999)}"
        self.name = name
        self.role = role
        self.team = team
        self.shift_type = shift_type
        self.date_arrivee = date_arrivee or date.today()
        self.statut = statut
        self.date_depart = date_depart
        self.performance_score = 0
        self.assigned_machine = "Aucune"
        self.production_tonnes = 0
        self.total_retards = 0
        self.total_absences = 0
        self.jours_sans_retard_absence = 0

    def anciennete_annees(self):
        return round((date.today() - self.date_arrivee).days / 365.25, 1)

    def to_dict(self):
        return {
            "matricule": self.matricule, "name": self.name, "role": self.role,
            "team": self.team, "shift_type": self.shift_type,
            "date_arrivee": self.date_arrivee.strftime("%Y-%m-%d"),
            "statut": self.statut,
            "date_depart": self.date_depart.strftime("%Y-%m-%d") if self.date_depart else None,
            "performance_score": self.performance_score, "assigned_machine": self.assigned_machine,
            "production_tonnes": self.production_tonnes, "total_retards": self.total_retards,
            "total_absences": self.total_absences,
            "jours_sans_retard_absence": self.jours_sans_retard_absence,
        }

    @classmethod
    def from_dict(cls, d):
        def _pdate(v):
            try:
                return datetime.strptime(v, "%Y-%m-%d").date() if v else None
            except (TypeError, ValueError):
                return None
        e = cls(d.get("name", ""), d.get("role", "Operateur"), d.get("team", "A"),
                d.get("shift_type", "Standard"), d.get("matricule"),
                _pdate(d.get("date_arrivee")) or date.today(), d.get("statut", "Actif"),
                _pdate(d.get("date_depart")))
        e.performance_score = d.get("performance_score", 0)
        e.assigned_machine = d.get("assigned_machine", "Aucune")
        e.production_tonnes = d.get("production_tonnes", 0)
        e.total_retards = d.get("total_retards", 0)
        e.total_absences = d.get("total_absences", 0)
        e.jours_sans_retard_absence = d.get("jours_sans_retard_absence", 0)
        return e


def _seed(today):
    return [
        Employee("Moussa Koné", "Operateur", "A", "3x8", "MAT-1001", today - timedelta(days=365)),
        Employee("Jean Ouedraogo", "Operateur", "B", "3x8", "MAT-1002", today - timedelta(days=180)),
        Employee("Fatou Diallo", "Ingenieur", "A", "Standard", "MAT-3001", today - timedelta(days=120)),
        Employee("Ibrahim Sano", "Mecanicien", "A", "Standard", "MAT-4001", today - timedelta(days=200)),
        Employee("Aminata Coulibaly", "Electricien", "B", "Standard", "MAT-4002", today - timedelta(days=150)),
        Employee("Boubacar Traoré", "Superviseur Production", "A", "3x8", "MAT-2002", today - timedelta(days=400)),
        Employee("Sékou Diarra", "Superviseur Mecanicien", "A", "Standard", "MAT-2003", today - timedelta(days=500)),
    ]


class StaffManager:
    def __init__(self, tenant_id="default"):
        self.tenant_id = tenant_id
        raw = storage.load_tenant_json(tenant_id, "staff.json", None)
        if raw is None:
            self.staff = _seed(date.today())
            self.save()
        else:
            self.staff = [Employee.from_dict(d) for d in raw]

    def save(self):
        storage.save_tenant_json(self.tenant_id, "staff.json", [e.to_dict() for e in self.staff])

    # -- lecture -----------------------------------------------------------
    def get_active_staff(self):
        return [e for e in self.staff if e.statut == "Actif"]

    def get_inactive_staff(self):
        return [e for e in self.staff if e.statut == "Inactif"]

    def get_employee_by_matricule(self, matricule):
        return next((e for e in self.staff if e.matricule == matricule), None)

    def teams(self):
        t = {}
        for e in self.get_active_staff():
            t.setdefault(e.team, []).append(e)
        return dict(sorted(t.items()))

    def get_classement_anciennete(self):
        return sorted(self.staff, key=lambda e: e.date_arrivee)

    def get_classement_production(self):
        ops = [e for e in self.staff if e.role == "Operateur"]
        return sorted(ops, key=lambda e: e.production_tonnes, reverse=True)

    def get_classement_assiduite(self):
        ops = [e for e in self.staff if e.role == "Operateur"]
        return sorted(ops, key=lambda e: e.jours_sans_retard_absence, reverse=True)

    # -- écriture ----------------------------------------------------------
    def add_employee(self, name, role, team, shift_type, matricule=None, date_arrivee=None):
        if not matricule:
            existing = [e.matricule for e in self.staff]
            n = 1000
            while f"MAT-{n}" in existing:
                n += 1
            matricule = f"MAT-{n}"
        elif any(e.matricule == matricule for e in self.staff):
            return False
        self.staff.append(Employee(name, role, team, shift_type, matricule, date_arrivee))
        self.save()
        return True

    def desactiver_employee(self, matricule):
        e = self.get_employee_by_matricule(matricule)
        if e:
            e.statut = "Inactif"
            e.date_depart = date.today()
            self.save()
            return True
        return False

    def reactiver_employee(self, matricule):
        e = self.get_employee_by_matricule(matricule)
        if e:
            e.statut = "Actif"
            e.date_depart = None
            self.save()
            return True
        return False

    def remove_employee(self, matricule):
        e = self.get_employee_by_matricule(matricule)
        if e:
            self.staff.remove(e)
            self.save()
            return True
        return False

    def enregistrer_presence(self, matricule, statut="present", retard=False):
        e = self.get_employee_by_matricule(matricule)
        if not e:
            return False
        if statut == "absent":
            e.total_absences += 1
            e.jours_sans_retard_absence = 0
        elif retard:
            e.total_retards += 1
            e.jours_sans_retard_absence = 0
        else:
            e.jours_sans_retard_absence += 1
        self.save()
        return True
