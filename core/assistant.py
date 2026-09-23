"""Assistant plateforme — répond aux questions sur GOOD ENGINEERS OS.

Connaissances intégrées sur chaque module + base apprenable par entreprise
(tenant_data/<tid>/assistant_kb.json). Correspondance par recouvrement de
mots-clés (simple, sans dépendance / sans réseau).
"""
import re
import unicodedata

from . import storage

# Connaissances intégrées : (mots-clés, réponse)
BUILTIN = [
    (["dashboard", "accueil", "kpi", "tableau", "bord"],
     "📊 Le Dashboard affiche les KPI temps réel : flotte active, pannes, production cumulée, "
     "niveau carburant, maintenances ouvertes et stock critique, avec graphiques et tableau de la flotte."),
    (["cycle", "cycles", "performance", "tonnes/heure", "rendement"],
     "🔄 Cycles montre le rendement des engins (tonnes/heure, cycles/heure, efficacité), un classement "
     "des engins et la performance par opérateur."),
    (["carburant", "gasoil", "plein", "conso", "consommation", "fuel"],
     "⛽ Carburant suit la consommation, les coûts et la rentabilité, avec saisie de plein multi-devise "
     "(CFA / EUR / USD) et conversion automatique."),
    (["maintenance", "panne", "reparation", "pm", "entretien", "atelier", "engin", "machine", "flotte"],
     "🔧 Maintenance : gestion de la flotte (ajouter/supprimer un engin), santé du parc, planification, "
     "signalement de panne, réparation, PM effectuées et historique."),
    (["stock", "piece", "pieces", "rechange", "seuil", "inventaire"],
     "📦 Stock gère les pièces de rechange : état, entrées, sorties, configuration des seuils d'alerte "
     "et historique des mouvements."),
    (["carte", "gps", "position", "localisation"],
     "🗺️ La Carte affiche les positions GPS des engins sur un fond OpenStreetMap, colorées par statut."),
    (["finance", "contrat", "revenu", "facture", "bcm", "horaire", "client"],
     "💰 Finance gère les contrats miniers (BCM et horaires), les revenus par période, les dépenses "
     "carburant, la fiche entreprise, et génère des factures imprimables (PDF via le navigateur)."),
    (["rh", "personnel", "employe", "employé", "equipe", "présence", "presence", "classement", "operateur"],
     "👥 RH gère le personnel : liste, ajout, désactivation, présence, équipes et classements "
     "(production, ancienneté, assiduité)."),
    (["ingenierie", "ingénierie", "saisie", "hmetre", "h-mètre", "manuel", "production"],
     "📐 Données Ingénierie sert à saisir les heures (H-mètre), le tonnage et le carburant par shift. "
     "La saisie met à jour l'engin et alimente Dashboard, Cycles et Finance."),
    (["voyage", "voyages", "tonnage", "facteur", "pesee", "pesée", "poids", "peser", "camion"],
     "⛏ Pour le tonnage, deux méthodes : (1) pesée directe → renseignez « Production (T) » ; "
     "(2) calcul → renseignez le « nombre de voyages » et le « tonnage/voyage » (t). "
     "Sans facteur, la capacité de l'engin sert de tonnage par voyage. Tonnage = voyages × tonnage/voyage."),
    (["periode", "période", "mise a jour", "mise à jour", "journaliere", "hebdomadaire", "mensuelle"],
     "🗓️ La « période de mise à jour » indique à quels totaux la saisie s'ajoute : Journalière = jour "
     "seul ; Hebdomadaire = aussi la semaine ; Mensuelle = aussi le mois/l'année ; Toutes = tous les compteurs."),
    (["sst", "securite", "sécurité", "incident", "take5", "take 5", "frein", "accident", "epi"],
     "🦺 SST gère les fiches sécurité (Take 5, JHA, incidents, near-miss) et les contrôles conducteurs "
     "(inspection véhicule, Take 5, test de frein), avec synthèse par conducteur."),
    (["messagerie", "message", "communique", "communiqué", "bandeau", "annonce", "chat"],
     "💬 Messagerie : messages d'équipe et directs, communiqués (admin) et bandeau défilant en haut de page."),
    (["validation", "chargement", "dechargement", "déchargement", "transport"],
     "✅ Validation Opérateur : l'opérateur de chargement valide un chargement (camion, matériau, teneur), "
     "ce qui notifie les opérateurs de transport qui l'acquittent."),
    (["admin", "utilisateur", "compte", "permission", "role", "rôle"],
     "⚙️ Admin gère les utilisateurs : liste, ajout, modification, suppression et permissions par onglet."),
    (["or", "marche", "marché", "cours", "gramme", "once"],
     "🥇 Marché Or affiche le cours de l'or (once et gramme) en USD et en CFA."),
    (["taux", "devise", "conversion", "convertir", "change", "cfa", "eur", "usd", "dollar", "euro"],
     "💱 Les taux du jour et le convertisseur de devises (barre de gauche) utilisent des taux en direct. "
     "Entrez un montant, choisissez les devises, le résultat se calcule instantanément."),
    (["connexion", "connecter", "mot de passe", "login", "identifiant", "deconnexion"],
     "🔐 Connectez-vous avec votre identifiant et mot de passe. L'administrateur crée et gère les comptes "
     "dans l'onglet Admin ; la console plateforme est réservée au rôle Gestionnaire."),
    (["gestionnaire", "plateforme", "saas", "entreprise", "tenant", "abonnement"],
     "🛰️ La console Gestionnaire (rôle plateforme) gère les entreprises clientes : création d'un espace "
     "client (entreprise + base isolée + admin), modification, suspension et suppression."),
]


def _norm(s):
    s = unicodedata.normalize("NFKD", str(s or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s


def _tokens(s):
    return set(re.findall(r"[a-z0-9]+", _norm(s)))


def load_kb(tid):
    data = storage.load_tenant_json(tid, "assistant_kb.json", {"entries": []})
    return data.get("entries", []) if isinstance(data, dict) else []


def add_kb(tid, question, answer):
    kb = load_kb(tid)
    kb.insert(0, {"q": question.strip(), "a": answer.strip()})
    storage.save_tenant_json(tid, "assistant_kb.json", {"entries": kb[:200]})


def delete_kb(tid, index):
    kb = load_kb(tid)
    if 0 <= index < len(kb):
        kb.pop(index)
        storage.save_tenant_json(tid, "assistant_kb.json", {"entries": kb})


def answer(tid, question):
    q = _norm(question)
    qtok = _tokens(question)
    if not qtok:
        return "Posez une question sur la plateforme (ex. « comment saisir le tonnage ? », « à quoi sert Finance ? »)."

    best_score, best_ans = 0, None

    # Base apprise (prioritaire) — poids fort ; correspondance par sous-chaîne
    # pour tolérer les pluriels (équipe / équipes) et les variantes.
    for e in load_kb(tid):
        etok = [t for t in _tokens(e.get("q", "")) if len(t) >= 3]
        if not etok:
            continue
        score = sum(3 for t in etok if t in q)  # chaque mot-clé appris trouvé
        if _norm(e.get("q", "")) in q:
            score += 5
        if score > best_score:
            best_score, best_ans = score, e.get("a", "")

    # Connaissances intégrées
    for keywords, ans in BUILTIN:
        score = 0
        for kw in keywords:
            if kw in q:
                score += 2
        score += len(qtok & _tokens(" ".join(keywords)))
        if score > best_score:
            best_score, best_ans = score, ans

    if best_ans and best_score >= 2:
        return best_ans
    return ("Je n'ai pas de réponse précise à cela. Modules disponibles : Dashboard, Cycles, Carburant, "
            "Maintenance, Stock, Carte, Finance, RH, Ingénierie, Messagerie, SST, Validation, Marché Or, Admin. "
            "Un administrateur peut m'apprendre de nouvelles réponses via le bouton « Enseigner ».")
