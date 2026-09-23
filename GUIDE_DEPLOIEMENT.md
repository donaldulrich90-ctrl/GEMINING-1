# Mettre GOOD ENGINEERS OS (Django) en ligne — Contabo + Coolify

Ce guide déploie la nouvelle version **Django** sur votre VPS Contabo via **Coolify**,
à partir d'un dépôt **GitHub**, sur l'adresse **gemining.duckdns.org** (en remplacement
de l'ancienne version Streamlit). C'est le même schéma que gedrilling.duckdns.org.

Tout est déjà préparé dans le dossier `webapp/` : `Dockerfile`, `requirements.txt`
(gunicorn + WhiteNoise), réglages de production, `.gitignore`, `.dockerignore`, `.env.example`.

---

## 1. Créer le dépôt GitHub et y pousser le code

Le dépôt = le contenu du dossier `webapp/` (le `Dockerfile` est à sa racine).
Vos données (`geo_data.db`, `app_database.json`, `tenant_data/`) NE sont PAS poussées
(elles sont dans `.gitignore`) — elles vivront sur un volume persistant côté serveur.

> ⚠️ **ATTENTION — ne poussez PAS depuis le dossier `TEST_MINE`.**
> Le dossier `TEST_MINE` est déjà un dépôt git, mais il est relié à **GEDRILLING.git**
> (le dépôt de votre application de forage) et contient l'ancien `app.py` Streamlit.
> Pousser depuis là écraserait votre dépôt de forage. La version minière doit avoir
> **son propre dépôt**, initialisé DANS le dossier `webapp/` (fait ci-dessous).
> J'ai déjà initialisé ce dépôt `webapp/` pour vous (git init + 1er commit) — il ne
> reste qu'à créer le dépôt GitHub et à pousser.

1. Sur GitHub (compte **donaldulrich90-ctrl**), créez un dépôt **privé** vide,
   par exemple `good-engineers-os`. Ne cochez rien (pas de README, pas de .gitignore).
2. Sur votre PC, dans `D:\PROJET GOOD ENGINEERS\TEST_MINE\webapp\`, ouvrez un terminal
   et lancez :

   ```
   git remote add origin https://github.com/donaldulrich90-ctrl/good-engineers-os.git
   git branch -M main
   git push -u origin main
   ```

   Git demandera vos identifiants GitHub (utilisez un **token d'accès personnel** comme
   mot de passe si demandé — Settings → Developer settings → Personal access tokens).

> Si vous préférez tout faire vous-même depuis zéro (au lieu d'utiliser le dépôt déjà
> initialisé), lancez d'abord `git init && git add . && git commit -m "Version Django"`.
>
> Pour les mises à jour futures : `git add . && git commit -m "..." && git push`,
> puis Coolify redéploie automatiquement.

---

## 2. Créer l'application dans Coolify

1. Coolify → votre projet → **+ New Resource** → **Application**.
2. Source : **GitHub** → sélectionnez le dépôt `good-engineers-os`, branche `main`.
3. Build Pack : **Dockerfile** (Coolify détecte le `Dockerfile` à la racine).
4. Port exposé : **8000**.

### Variables d'environnement (onglet Environment Variables)

Copiez celles-ci (voir `.env.example`) :

| Variable | Valeur |
|---|---|
| `GE_SECRET_KEY` | une clé longue et **stable** (voir ci-dessous) |
| `GE_DEBUG` | `0` |
| `GE_ALLOWED_HOSTS` | `gemining.duckdns.org` |
| `GE_CSRF_TRUSTED_ORIGINS` | `https://gemining.duckdns.org` |
| `GE_DATA_ROOT` | `/data` |

Pour générer `GE_SECRET_KEY`, sur votre PC :

```
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

Collez le résultat comme valeur. **Ne la changez plus** ensuite (sinon déconnexions).

### Volume persistant (TRÈS IMPORTANT)

Sans cela, vos entreprises/utilisateurs/données seraient effacés à chaque redéploiement.

- Onglet **Storages** (ou Persistent Storage) → **Add** :
  - **Name** : `ge-data`
  - **Destination Path (dans le conteneur)** : `/data`

C'est là que l'app écrira `app_database.json`, `geo_data.db` et `tenant_data/`.

### Domaine

- Onglet **Domains** : mettez `https://gemining.duckdns.org`.
- Coolify gère le certificat HTTPS (Let's Encrypt) automatiquement.
- Assurez-vous que DuckDNS `gemining` pointe bien vers l'IP du VPS (37.60.243.107).
  Comme l'ancienne version Streamlit y répondait déjà, c'est probablement déjà le cas —
  il suffit de rediriger le domaine de l'ancien conteneur vers celui-ci (ou d'arrêter
  l'ancien conteneur Streamlit pour libérer l'adresse).

---

## 3. Déployer

Cliquez sur **Deploy**. Au premier démarrage, si le volume `/data` est vide,
l'application crée automatiquement un compte administrateur par défaut :

- **admin / admin**  (changez ce mot de passe tout de suite dans l'onglet Admin)
- Console plateforme : **gestionnaire / gestionnaire**

Ouvrez `https://gemining.duckdns.org/` — vous devez voir la page de connexion.

---

## 4. (Optionnel) Reprendre vos données existantes du PC

Si vous voulez démarrer en ligne avec vos entreprises déjà créées sur votre PC
(tenants `default`, `vital-mining`, `ge`…), copiez le contenu de votre `GE_DATA_ROOT`
local vers le volume `/data` du serveur, **app arrêtée** :

Fichiers/dossiers à copier (depuis `D:\PROJET GOOD ENGINEERS\TEST_MINE\`) :
- `app_database.json`
- `geo_data.db`
- le dossier `tenant_data/`

Méthode simple : dans Coolify, ouvrez le **terminal** du conteneur (ou un accès SSH au
VPS), et déposez ces fichiers dans le volume monté sur `/data`. Puis redémarrez l'app.
Je peux vous accompagner pas à pas pour cette copie quand vous y serez.

> Attention : ne mélangez pas des données de test et des données réelles. Faites une
> sauvegarde de `/data` avant toute manipulation.

---

## Récapitulatif des fichiers de production ajoutés

- `Dockerfile` — image Python + gunicorn + WhiteNoise, collectstatic à la construction.
- `requirements.txt` — ajoute `gunicorn`, `whitenoise`, `requests`.
- `good_engineers_os/settings.py` — WhiteNoise, cookies sécurisés en prod, en-tête proxy HTTPS.
- `.env.example` — modèle des variables Coolify.
- `.gitignore` / `.dockerignore` — excluent secrets et données.

Bon déploiement — en cas de blocage (build qui échoue, 400/500, données), envoyez-moi
le message d'erreur de Coolify et je corrige.
