# GOOD ENGINEERS OS — migration Streamlit → Django

Nouvelle base de l'application, **sans Streamlit**, en conservant le design
(vert foncé / or), l'authentification multi-entreprise et les données existantes.

## Ce qui est déjà fait (étape 1 — socle + module démo)

- **Socle Django complet** : projet `good_engineers_os`, application `webcore`.
- **Réutilisation des données existantes** : aucune migration de base. L'app lit
  directement `app_database.json`, `geo_data.db` et `tenant_data/` de l'ancienne
  application (dossier parent par défaut). Les mots de passe hachés SHA-256
  restent valides — vos comptes fonctionnent tels quels.
- **Authentification + rôles + multi-tenant** portés à l'identique
  (Administrateur, Gestionnaire, RH, Invité, Opérateur, Superviseurs, Ingénieur…).
- **Design porté** : page de connexion split-screen, bannière de marque,
  navigation par onglets selon le rôle, thème sombre vert/or.
- **Module Dashboard complet** (démo) branché sur les vraies données SQLite :
  KPI (flotte, production, carburant, pannes, maintenance, stock), graphiques
  (répartition des statuts + production par machine, en SVG natif, sans CDN),
  alertes et tableau de la flotte.
- Les 13 autres onglets sont en place dans la navigation, avec une page
  « à migrer » — ce sont les prochaines étapes.

## Architecture

```
webapp/
  manage.py
  good_engineers_os/         # configuration Django (settings, urls, wsgi)
  core/                      # LOGIQUE MÉTIER (réutilisable, sans Streamlit)
    security.py              # hachage mots de passe (SHA-256 NFKC)
    storage.py               # chemins données + app_database.json + tenants
    db.py                    # connexion SQLite par tenant + schéma
    auth.py                  # UserManager (comptes, rôles, permissions)
    fleet.py                 # Machine, FleetManager, Stock, Maintenance
    permissions.py           # onglets visibles par rôle
  webcore/                   # couche web Django
    middleware.py            # auth par session + isolation tenant
    views.py                 # login, dashboard, onglets
    context_processors.py    # navigation
  templates/                 # login, base, dashboard, placeholder
  static/css, static/img     # thème + visuels
```

Le dossier `core/` contient la logique métier **portée depuis l'ancien `app.py`**
(16 684 lignes). Elle ne dépend plus de Streamlit : les prochains modules
(Carburant, Maintenance, Stock, Finance, RH…) réutiliseront ces mêmes classes.

## Lancer en local (Windows)

Dans le dossier `webapp/` :

```powershell
pip install -r requirements.txt
python manage.py runserver 0.0.0.0:8000
```

Puis ouvrir http://localhost:8000/ — comptes de test : `admin` / `admin`.

> Par défaut, l'app lit les données dans le **dossier parent** (`TEST_MINE`).
> Pour pointer ailleurs : variable d'environnement `GE_DATA_ROOT`.

## Déploiement (remplacer le conteneur Streamlit)

En production, servir via un serveur WSGI (gunicorn/uwsgi) derrière votre
reverse-proxy actuel (NPM / OpenResty) :

```bash
pip install gunicorn
python manage.py collectstatic --noinput
gunicorn good_engineers_os.wsgi:application --bind 0.0.0.0:8000
```

Variables d'environnement utiles :
`GE_SECRET_KEY`, `GE_DEBUG=0`, `GE_ALLOWED_HOSTS=gemining.duckdns.org`,
`GE_CSRF_TRUSTED_ORIGINS=https://gemining.duckdns.org`, `GE_DATA_ROOT`.

## Modules déjà migrés

- **Dashboard** — KPI, graphiques, alertes, tableau flotte.
- **Cycles** — performance des engins (tonnes/h, cycles/h, efficacité), classement, top 10.
- **Carburant** — consommation, coûts, rentabilité, taux de change live, saisie de plein multi-devise (écrit dans `fuel_logs`).
- **Maintenance** — santé du parc, planification, signalement de panne, réparation, PM, historique (`maintenance_logs`).
- **Marché Or** — cours de l'or (once / gramme) en USD et CFA.
- **Admin** — gestion des utilisateurs : liste, ajout, modification, suppression, permissions (écrit dans `app_database.json`).
- **Stock** — pièces de rechange : état, entrées/sorties, seuils, historique (persisté dans `tenant_data/<tid>/stock.json`).
- **RH** — personnel : liste, ajout, désactivation/réactivation, suppression, présence, équipes et classements (persisté dans `tenant_data/<tid>/staff.json`). La performance par opérateur est désormais affichée dans l'onglet Cycles.
- **Finance** — contrats miniers (BCM / horaire), revenus par période, ajout/modification de taux, activation, fiche entreprise, dépenses carburant par période, et **facture imprimable** (PDF via le navigateur). Contrats persistés dans `finance_contracts.json` ; la fiche entreprise réutilise le fichier de l'ancienne app (`branding/finance_company_profile.json`).
- **Carte** — positions GPS des engins sur fond OpenStreetMap (marqueurs colorés par statut), avec repli sur la liste des coordonnées hors-ligne.
- **Données Ingénierie** — saisie manuelle (H-mètre début/fin, production, carburant, par shift) qui met à jour les agrégats de l'engin et alimente Dashboard/Cycles/Finance ; synthèse du jour par shift + historique (`manual_entries`).
- **SST** — fiches sécurité (Take 5, JHA, incidents, near-miss…) et contrôles conducteurs (inspection véhicule, Take 5, test de frein) avec synthèse par conducteur ; persisté dans `collaboration/sst_records.json` et `sst_driver_checks.json` (mêmes fichiers que l'ancienne app).
- **Messagerie** — messages d'équipe et directs, communiqués (admin), et **bandeau défilant** en haut de toutes les pages ; persisté dans `collaboration/messages.json` et `banner_annonce.json`.
- **Validation Opérateur** — l'opérateur de chargement valide un chargement (camion, matériau, teneur, destination) → notification aux opérateurs de transport qui l'acquittent ; persisté dans `operator_notifications.json`.
- **Console Gestionnaire** (plateforme SaaS) — page dédiée au rôle Gestionnaire (`gestionnaire` / `ge-plateforme`) : liste des entreprises clientes, **création d'un client** (entreprise + compte admin + base isolée), modification, suspension/activation et suppression.

**La migration est complète : les 14 onglets + la console plateforme sont portés.**

> Note : le stock, le personnel et les contrats, gardés en mémoire dans
> l'ancienne app (perdus au redémarrage), sont maintenant **persistés** en JSON
> par entreprise.

## Améliorations restantes possibles (facultatif)

La migration fonctionnelle est terminée. Pistes d'amélioration ultérieures :
pièces jointes dans la messagerie et les fiches SST, upload de logo/cachet pour
les factures, exports CSV des rapports, et l'atelier-pièces avancé de la
maintenance (sélection de pièces liée au stock lors des réparations).
