"""Gestion des utilisateurs, rôles et permissions — porté depuis app.py.

Sans dépendance Streamlit : lit/écrit app_database.json via core.storage.
Les mots de passe restent hachés en SHA-256 (compatibles avec l'ancienne base).
"""
from .security import hash_password, is_hashed
from .storage import get_database, save_database, safe_tenant_id

DEFAULT_PERMISSIONS = {
    "Administrateur": {
        "dashboard": True, "cycles": True, "carburant": True, "maintenance": True, "stock": True,
        "carte": True, "finance": True, "rh": True, "admin": True, "validation_operateur": True,
        "donnees_ingenierie": True, "messagerie": True, "sst": True,
        "can_add_users": True, "can_modify_users": True, "can_delete_users": True,
        "can_view_all": True, "can_export": True, "can_modify_data": True,
    },
    "Ingenieur": {
        "dashboard": True, "cycles": True, "carburant": False, "maintenance": True, "stock": True,
        "carte": True, "finance": False, "rh": False, "admin": False, "validation_operateur": True,
        "donnees_ingenierie": True, "messagerie": True, "sst": True,
        "can_add_users": False, "can_modify_users": False, "can_delete_users": False,
        "can_view_all": True, "can_export": True, "can_modify_data": True,
    },
    "RH": {
        "dashboard": True, "cycles": False, "carburant": False, "maintenance": False, "stock": True,
        "carte": False, "finance": False, "rh": True, "admin": False, "validation_operateur": False,
        "messagerie": True, "sst": True,
        "can_add_users": False, "can_modify_users": False, "can_delete_users": False,
        "can_view_all": False, "can_export": True, "can_modify_data": True,
    },
    "Invite": {
        "dashboard": True, "cycles": True, "carburant": False, "maintenance": False, "stock": False,
        "carte": True, "finance": False, "rh": False, "admin": False, "validation_operateur": False,
        "messagerie": True, "sst": True,
        "can_add_users": False, "can_modify_users": False, "can_delete_users": False,
        "can_view_all": False, "can_export": False, "can_modify_data": False,
    },
    "Superviseur Production": {
        "dashboard": True, "cycles": True, "carburant": True, "maintenance": True, "stock": True,
        "carte": True, "finance": True, "rh": False, "admin": False, "validation_operateur": True,
        "donnees_ingenierie": True, "messagerie": True, "sst": True,
        "can_add_users": False, "can_modify_users": False, "can_delete_users": False,
        "can_view_all": True, "can_export": True, "can_modify_data": True,
    },
    "Superviseur Mecanicien": {
        "dashboard": True, "cycles": True, "carburant": True, "maintenance": True, "stock": True,
        "carte": True, "finance": False, "rh": False, "admin": False, "validation_operateur": True,
        "donnees_ingenierie": True, "messagerie": True, "sst": True,
        "can_add_users": False, "can_modify_users": False, "can_delete_users": False,
        "can_view_all": True, "can_export": True, "can_modify_data": True,
    },
    "Operateur": {
        "dashboard": False, "cycles": False, "carburant": False, "maintenance": False, "stock": False,
        "carte": False, "finance": False, "rh": False, "admin": False,
        "validation_operateur": True, "messagerie": True, "sst": True,
        "can_add_users": False, "can_modify_users": False, "can_delete_users": False,
        "can_view_all": False, "can_export": False, "can_modify_data": False,
    },
    "Gestionnaire": {
        "dashboard": False, "cycles": False, "carburant": False, "maintenance": False, "stock": False,
        "carte": False, "finance": False, "rh": False, "admin": False,
        "donnees_ingenierie": False, "validation_operateur": False, "messagerie": False, "sst": False,
        "can_add_users": False, "can_modify_users": False, "can_delete_users": False,
        "can_view_all": False, "can_export": False, "can_modify_data": False,
        "platform_admin": True,
    },
}

# Comptes créés au premier démarrage si la base est vide (mots de passe en clair
# → hachés à la première sauvegarde, comme dans l'ancienne app).
_BOOTSTRAP_USERS = [
    {"user": "admin", "pass": "admin", "role": "Administrateur", "tenant_id": "default"},
    {"user": "gestionnaire", "pass": "ge-plateforme", "role": "Gestionnaire", "tenant_id": "__platform__"},
    {"user": "rh", "pass": "rh", "role": "RH", "tenant_id": "default"},
    {"user": "visiteur", "pass": "visiteur", "role": "Invite", "tenant_id": "default"},
]


class UserManager:
    def __init__(self):
        self.default_permissions = DEFAULT_PERMISSIONS
        self.users_db = []
        self._bootstrap_users()

    # -- persistance -------------------------------------------------------
    def persist_users(self):
        db = get_database()
        db["users_list"] = self.users_db
        save_database(db)

    def reload_users_from_disk(self):
        db = get_database()
        loaded = db.get("users_list")
        if loaded and isinstance(loaded, list) and len(loaded) > 0:
            self.users_db = loaded
        self._migrate_users()

    def _bootstrap_users(self):
        db = get_database()
        loaded = db.get("users_list")
        if loaded and isinstance(loaded, list) and len(loaded) > 0:
            self.users_db = loaded
        else:
            self.users_db = [
                {**u, "permissions": self.default_permissions[u["role"]].copy()}
                for u in _BOOTSTRAP_USERS
            ]
            self.persist_users()
        self._migrate_users()

    def _migrate_users(self):
        """Complète les champs manquants et hache les mots de passe en clair."""
        changed = False
        for u in self.users_db:
            if not isinstance(u, dict):
                continue
            if not str(u.get("user", "")).strip():
                alt = u.get("username") or u.get("login")
                if alt and str(alt).strip():
                    u["user"] = str(alt).strip()
                    changed = True
            elif isinstance(u.get("user"), str) and u["user"].strip() != u["user"]:
                u["user"] = u["user"].strip()
                changed = True
            if "pass" not in u and u.get("password") is not None:
                u["pass"] = u["password"]
                changed = True
            if "tenant_id" not in u:
                u["tenant_id"] = "default"
                changed = True
            if not u.get("permissions"):
                role = u.get("role", "Invite")
                u["permissions"] = self.default_permissions.get(
                    role, self.default_permissions["Invite"]
                ).copy()
                changed = True
            raw_pass = str(u.get("pass", ""))
            if raw_pass and not is_hashed(raw_pass):
                u["pass"] = hash_password(raw_pass)
                changed = True
        if changed:
            self.persist_users()

    # -- authentification --------------------------------------------------
    def verify_login(self, username, password):
        u_in = (username or "").strip()
        if not u_in or not password:
            return None
        u_in_lower = u_in.lower()
        p_hashed = hash_password(password)
        for u in self.users_db:
            if not isinstance(u, dict):
                continue
            u_name = str(u.get("user", "") or u.get("username") or u.get("login") or "").strip()
            if not u_name:
                continue
            stored = str(u.get("pass", u.get("password", "")))
            if u_name.lower() == u_in_lower and stored == p_hashed:
                return u
        return None

    def get_user(self, username):
        un = (username or "").strip().lower()
        if not un:
            return None
        for u in self.users_db:
            if not isinstance(u, dict):
                continue
            u_name = str(u.get("user", "") or u.get("username") or u.get("login") or "").strip().lower()
            if u_name == un:
                return u
        return None

    # -- administration ----------------------------------------------------
    def add_user(self, username, password, role, custom_permissions=None, tenant_id="default"):
        ul = (username or "").strip().lower()
        for u in self.users_db:
            if str(u.get("user", "")).strip().lower() == ul:
                return False
        permissions = (
            custom_permissions
            or self.default_permissions.get(role, self.default_permissions["Invite"]).copy()
        )
        self.users_db.append({
            "user": username.strip(),
            "pass": hash_password(password),
            "role": role,
            "tenant_id": safe_tenant_id(tenant_id),
            "permissions": permissions,
        })
        self.persist_users()
        return True

    def update_user(self, username, password=None, role=None, permissions=None):
        un = (username or "").strip().lower()
        for u in self.users_db:
            if not isinstance(u, dict):
                continue
            if str(u.get("user", "")).strip().lower() == un:
                if password:
                    u["pass"] = hash_password(password)
                if role:
                    u["role"] = role
                    u["permissions"] = self.default_permissions.get(
                        role, self.default_permissions["Invite"]
                    ).copy()
                if permissions:
                    u["permissions"] = permissions
                self.persist_users()
                return True
        return False

    def delete_user(self, username):
        if username in ("admin", "gestionnaire"):
            return False
        self.users_db = [u for u in self.users_db if u.get("user") != username]
        self.persist_users()
        return True

    def users_in_tenant(self, tenant_id):
        tid = safe_tenant_id(tenant_id)
        return [u for u in self.users_db if safe_tenant_id(u.get("tenant_id", "default")) == tid]


def get_user_manager():
    """Instance fraîche (relit la base à chaque appel — multi-session sûr)."""
    return UserManager()
