"""Récupération de l'accès administrateur plateforme de GE Mining.

But : regagner l'accès au compte « gestionnaire » (rôle Gestionnaire, console
plateforme) par un simple redéploiement, sans terminal ni manipulation.

Comportement (appelée depuis le Dockerfile, avant gunicorn) :

1. Si RESET_MINE_ADMIN est défini (≠ off/vide) OU MINE_ADMIN_PASSWORD fourni :
   (re)définit le mot de passe du compte « gestionnaire » (ou MINE_ADMIN_USERNAME).
   La valeur de RESET_MINE_ADMIN sert de mot de passe si ce n'est pas un simple
   drapeau (1/true/on/yes) ; sinon MINE_ADMIN_PASSWORD, puis le mot de passe de
   secours.

2. Sinon : réinitialisation AUTOMATIQUE, UNE SEULE FOIS, vers un mot de passe de
   secours connu, tant qu'un marqueur n'existe pas dans GE_DATA_ROOT. Une fois
   appliquée, elle n'est plus rejouée (le marqueur est écrit).

N'altère aucune donnée métier : ne touche qu'au compte administrateur dans
app_database.json. Mot de passe de secours à changer immédiatement après
connexion.
"""
import os
import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from core.auth import get_user_manager

RECOVERY_USERNAME = "gestionnaire"
RECOVERY_PASSWORD = "GEDrilling2026"
_FLAG_VALUES = {"1", "true", "on", "yes"}


class Command(BaseCommand):
    help = "Crée ou réinitialise l'administrateur plateforme de GE Mining (récupération d'accès)."

    def _marker_path(self) -> Path:
        base = os.environ.get("GE_DATA_ROOT") or str(getattr(settings, "GE_DATA_ROOT", "."))
        return Path(base) / ".mine_admin_reset_v1"

    def _apply(self, username: str, password: str) -> str:
        mgr = get_user_manager()
        if mgr.get_user(username) is None:
            mgr.add_user(username, password, "Gestionnaire", tenant_id="__platform__")
            return "créé"
        mgr.update_user(username, password=password)
        return "réinitialisé"

    def handle(self, *args, **options):
        username = (os.environ.get("MINE_ADMIN_USERNAME") or RECOVERY_USERNAME).strip() or RECOVERY_USERNAME
        env_pwd = (os.environ.get("MINE_ADMIN_PASSWORD") or "").strip()
        reset_flag = (os.environ.get("RESET_MINE_ADMIN") or "").strip()

        # (1) Réinitialisation pilotée par variable d'environnement.
        if (reset_flag and reset_flag.lower() != "off") or env_pwd:
            if reset_flag and reset_flag.lower() not in _FLAG_VALUES and reset_flag.lower() != "off":
                password = reset_flag
            else:
                password = env_pwd or RECOVERY_PASSWORD
            action = self._apply(username, password)
            self.stdout.write(
                f"🔑 Admin Mine « {username} » {action} via variable d'environnement. "
                f"Connectez-vous puis RETIREZ RESET_MINE_ADMIN / MINE_ADMIN_PASSWORD."
            )
            return

        # (2) Récupération automatique unique (marqueur).
        marker = self._marker_path()
        try:
            already = marker.exists()
        except Exception:
            already = False
        if already:
            self.stdout.write("Admin Mine : marqueur de récupération présent, aucune action.")
            return

        action = self._apply(username, RECOVERY_PASSWORD)
        try:
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text(datetime.datetime.utcnow().isoformat() + "\n")
        except Exception:
            pass
        self.stdout.write(
            f"🔑 Récupération automatique unique — admin Mine « {username} » {action} "
            f"avec le mot de passe « {RECOVERY_PASSWORD} ». À CHANGER immédiatement après connexion."
        )
