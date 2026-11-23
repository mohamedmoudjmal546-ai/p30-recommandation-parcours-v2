"""Moteur de recommandation : requêtes Cypher du fichier cypher/02_*.cypher
rendues paramétrables, puis assemblage du résultat.

Fonctionnalités spécifiques à Neo4j mises en œuvre ici :
  * parcours de graphe à profondeur variable  (PREREQUIS*1..4, PREREQUIS*0..4)
  * plus court chemin                         (shortestPath)
"""
from fastapi import HTTPException

import  crud
import  database as db
from planification import construire_parcours

PROFONDEUR_MAX = 4

# --- Q1 : prérequis transitifs (parcours *1..N) -----------------------------
# Neo4j n'accepte pas de paramètre pour les bornes d'un chemin variable : la
# borne est insérée après validation (entier 1..4 imposé par l'API).
Q1_PREREQUIS = """
MATCH p = (c:Competence {id: $id})-[:PREREQUIS*1..__N__]->(pre:Competence)
WITH pre, min(length(p)) AS distance
RETURN pre.id AS id, pre.nom AS nom, pre.categorie AS categorie, distance
ORDER BY distance, nom
"""

# --- Q2 : plus court chemin entre deux nœuds quelconques --------------------
Q2_EXISTENCE = "MATCH (n) WHERE n.id IN [$a, $b] RETURN collect(n.id) AS ids"
Q2_CHEMIN = """
MATCH (a {id: $a}), (b {id: $b})
MATCH p = shortestPath((a)-[:REQUIERT|DEVELOPPE|PREREQUIS|MENE_A|INCLUT*..6]-(b))
RETURN [n IN nodes(p) | {id: n.id, nom: n.nom, type: head(labels(n))}] AS noeuds,
       [r IN relationships(p) | {type: type(r), de: startNode(r).id, vers: endNode(r).id}] AS relations,
       length(p) AS longueur
"""

# --- Q3 : compétences manquantes d'un métier --------------------------------
Q3_MANQUANTES = """
MATCH (m:Metier {id: $metier_id})-[r:REQUIERT]->(c:Competence)
WHERE NOT c.id IN $acquises
RETURN c.id AS id, c.nom AS nom, c.categorie AS categorie, r.importance AS importance
ORDER BY importance DESC, nom
"""
Q3_TOTAL = """
MATCH (:Metier {id: $metier_id})-[r:REQUIERT]->(:Competence)
RETURN count(r) AS nb_requises, sum(r.importance) AS poids_total
"""

# --- Q4 : formations classées par score -------------------------------------
Q4_FORMATIONS = """
MATCH (:Metier {id: $metier_id})-[r:REQUIERT]->(c:Competence)
WHERE NOT c.id IN $acquises
MATCH (f:Formation)-[d:DEVELOPPE]->(c)
WITH f, collect(c.nom) AS competences_couvertes, count(c) AS nb_competences,
     sum(r.importance * d.niveau_acquis) AS score
RETURN f.id AS id, f.nom AS nom, f.niveau AS niveau, f.duree_heures AS duree_heures,
       nb_competences, competences_couvertes, score,
       round(1.0 * score / f.duree_heures * 10, 2) AS efficacite_pour_10h
ORDER BY score DESC, duree_heures ASC
LIMIT $limite
"""

# --- Q5 : couverture pondérée de chaque métier ------------------------------
Q5_COUVERTURE = """
MATCH (m:Metier)-[r:REQUIERT]->(c:Competence)
WITH m, count(c) AS nb_requises, sum(r.importance) AS poids_total,
     sum(CASE WHEN c.id IN $acquises THEN 1 ELSE 0 END) AS nb_acquises,
     sum(CASE WHEN c.id IN $acquises THEN r.importance ELSE 0 END) AS poids_acquis
RETURN m.id AS id, m.nom AS nom, m.secteur AS secteur, nb_acquises, nb_requises,
       round(100.0 * poids_acquis / poids_total, 1) AS couverture_pct
ORDER BY couverture_pct DESC, nom
"""

# --- Q6 : besoins (cibles + prérequis manquants) avec leur profondeur --------
Q6_BESOINS = """
MATCH (:Metier {id: $metier_id})-[r:REQUIERT]->(c:Competence)
MATCH p = (c)-[:PREREQUIS*0..__N__]->(besoin:Competence)
WHERE NOT besoin.id IN $acquises
WITH besoin, max(length(p)) AS profondeur, max(r.importance) AS poids,
     max(CASE WHEN length(p) = 0 THEN 1 ELSE 0 END) AS flag_direct
RETURN besoin.id AS id, besoin.nom AS nom, besoin.categorie AS categorie,
       profondeur, poids, flag_direct = 1 AS directe
ORDER BY profondeur DESC, nom
"""
Q6_CANDIDATS = """
MATCH (f:Formation)-[d:DEVELOPPE]->(c:Competence)
WHERE c.id IN $ids
RETURN f.id AS id, f.nom AS nom, f.niveau AS niveau, f.duree_heures AS duree_heures,
       collect({id: c.id, niveau: d.niveau_acquis}) AS couvre
"""
Q6_DEPENDANCES = """
MATCH (c:Competence)-[:PREREQUIS]->(p:Competence)
WHERE c.id IN $ids AND p.id IN $ids
RETURN c.id AS competence, p.id AS prerequis
"""

# --- Compétences acquises + tous leurs prérequis (fermeture transitive) -----
Q_FERMETURE = """
MATCH (a:Competence) WHERE a.id IN $ids
OPTIONAL MATCH (a)-[:PREREQUIS*1..10]->(p:Competence)
RETURN collect(DISTINCT a.id) + collect(DISTINCT p.id) AS ids
"""

# --- Analyses ----------------------------------------------------------------
Q7_PIVOT = """
MATCH (m:Metier)-[r:REQUIERT]->(c:Competence)
WITH c, count(DISTINCT m) AS nb_metiers, round(avg(r.importance), 2) AS importance_moyenne
OPTIONAL MATCH (f:Formation)-[:DEVELOPPE]->(c)
RETURN c.id AS id, c.nom AS nom, c.categorie AS categorie, nb_metiers, importance_moyenne,
       count(DISTINCT f) AS nb_formations
ORDER BY nb_metiers DESC, importance_moyenne DESC, nom
LIMIT $limite
"""
Q8_SIMILAIRES = """
MATCH (a:Metier {id: $id})-[:REQUIERT]->(c:Competence)<-[:REQUIERT]-(b:Metier)
WITH a, b, collect(c.nom) AS communes, count(c) AS nb_communes
MATCH (a)-[:REQUIERT]->(ca:Competence)
WITH a, b, communes, nb_communes, count(ca) AS na
MATCH (b)-[:REQUIERT]->(cb:Competence)
WITH a, b, communes, nb_communes, na, count(cb) AS nb
RETURN b.id AS id, b.nom AS nom, nb_communes,
       round(1.0 * nb_communes / (na + nb - nb_communes), 2) AS jaccard, communes
ORDER BY jaccard DESC, nom
LIMIT $limite
"""
Q9_CYCLES = """
MATCH p = (c:Competence)-[:PREREQUIS*1..10]->(c)
RETURN c.id AS competence, length(p) AS longueur
LIMIT 10
"""
Q10_PARCOURS = """
MATCH (p:Parcours)-[:MENE_A]->(m:Metier)
WHERE $id IS NULL OR p.id = $id
OPTIONAL MATCH (p)-[i:INCLUT]->(f:Formation)
WITH p, m, i, f ORDER BY i.ordre
RETURN p.id AS id, p.nom AS nom, p.description AS description, p.duree_mois AS duree_mois,
       m.id AS metier_id, m.nom AS metier,
       collect(CASE WHEN f IS NULL THEN NULL
                    ELSE {ordre: i.ordre, id: f.id, nom: f.nom, duree_heures: f.duree_heures} END) AS formations,
       sum(coalesce(f.duree_heures, 0)) AS heures_totales
ORDER BY id
"""
Q_GRAPHE = """
MATCH (m:Metier {id: $id})-[r:REQUIERT]->(c:Competence)
OPTIONAL MATCH (f:Formation)-[d:DEVELOPPE]->(c)
OPTIONAL MATCH (c)-[:PREREQUIS]->(p:Competence)
RETURN m.id AS m_id, m.nom AS m_nom, c.id AS c_id, c.nom AS c_nom, r.importance AS importance,
       f.id AS f_id, f.nom AS f_nom, d.niveau_acquis AS niveau_acquis, p.id AS p_id, p.nom AS p_nom
"""
Q_STATS_NOEUDS = "MATCH (n) RETURN labels(n)[0] AS label, count(n) AS nb ORDER BY label"
Q_STATS_RELATIONS = "MATCH ()-[r]->() RETURN type(r) AS type, count(r) AS nb ORDER BY type"


# ---------------------------------------------------------------------------
# Outils
# ---------------------------------------------------------------------------
def _borne(profondeur: int) -> int:
    if not isinstance(profondeur, int) or not 1 <= profondeur <= PROFONDEUR_MAX:
        raise HTTPException(422, f"profondeur doit être un entier entre 1 et {PROFONDEUR_MAX}")
    return profondeur


def _acquises_avec_prerequis(acquises: list[str]) -> list[str]:
    """Valide les identifiants puis ajoute les prérequis implicites des acquis."""
    if not acquises:
        return []
    connues = {r["id"] for r in db.lire("MATCH (c:Competence) WHERE c.id IN $ids RETURN c.id AS id", ids=acquises)}
    inconnues = sorted(set(acquises) - connues)
    if inconnues:
        raise HTTPException(422, f"Compétence(s) inconnue(s) : {', '.join(inconnues)}")
    ids = db.lire(Q_FERMETURE, ids=acquises)[0]["ids"]
    return sorted(set(ids))


# ---------------------------------------------------------------------------
# Fonctions publiques (appelées par main.py)
# ---------------------------------------------------------------------------
def prerequis_transitifs(competence_id: str, profondeur: int) -> dict:
    crud.obtenir("Competence", competence_id)
    n = _borne(profondeur)
    rows = db.lire(Q1_PREREQUIS.replace("__N__", str(n)), id=competence_id)
    return {"competence_id": competence_id, "profondeur_max": n, "prerequis": rows}


def plus_court_chemin(source: str, cible: str) -> dict:
    if source == cible:
        raise HTTPException(400, "source et cible doivent être différentes")
    trouves = db.lire(Q2_EXISTENCE, a=source, b=cible)[0]["ids"]
    for id_ in (source, cible):
        if id_ not in trouves:
            raise HTTPException(404, f"Nœud '{id_}' introuvable")
    rows = db.lire(Q2_CHEMIN, a=source, b=cible)
    if not rows:
        return {"source": source, "cible": cible, "chemin": None, "message": "Aucun chemin de longueur ≤ 6"}
    return {"source": source, "cible": cible, "chemin": rows[0]}


def recommander(metier_id: str, acquises: list[str], max_formations: int) -> dict:
    metier = crud.obtenir("Metier", metier_id)
    acq = _acquises_avec_prerequis(acquises)

    total = db.lire(Q3_TOTAL, metier_id=metier_id)[0]
    manquantes = db.lire(Q3_MANQUANTES, metier_id=metier_id, acquises=acq)
    poids_manquant = sum(m["importance"] for m in manquantes)
    poids_total = total["poids_total"] or 1
    couverture = round(100.0 * (1 - poids_manquant / poids_total), 1)

    besoins_rows = db.lire(Q6_BESOINS.replace("__N__", str(PROFONDEUR_MAX)), metier_id=metier_id, acquises=acq)
    besoins = {r["id"]: r for r in besoins_rows}
    prerequis_manquants = [r for r in besoins_rows if not r["directe"]]

    classement = db.lire(Q4_FORMATIONS, metier_id=metier_id, acquises=acq, limite=max_formations)

    if besoins:
        ids = list(besoins)
        candidats = db.lire(Q6_CANDIDATS, ids=ids)
        deps = [(r["competence"], r["prerequis"]) for r in db.lire(Q6_DEPENDANCES, ids=ids)]
        parcours = construire_parcours(besoins, candidats, deps, max_formations)
    else:
        parcours = {"etapes": [], "nb_formations": 0, "duree_totale_heures": 0, "competences_non_couvertes": []}

    return {
        "metier": {"id": metier["id"], "nom": metier["nom"]},
        "competences_acquises": acq,
        "nb_competences_requises": total["nb_requises"],
        "couverture_pct": couverture,
        "competences_manquantes": manquantes,
        "prerequis_manquants": prerequis_manquants,
        "formations_recommandees": classement,
        "parcours_propose": parcours,
    }


def couverture_metiers(acquises: list[str]) -> list[dict]:
    return db.lire(Q5_COUVERTURE, acquises=_acquises_avec_prerequis(acquises))


def competences_pivot(limite: int) -> list[dict]:
    return db.lire(Q7_PIVOT, limite=limite)


def metiers_similaires(metier_id: str, limite: int) -> list[dict]:
    crud.obtenir("Metier", metier_id)
    return db.lire(Q8_SIMILAIRES, id=metier_id, limite=limite)


def detecter_cycles() -> dict:
    cycles = db.lire(Q9_CYCLES)
    return {"integre": not cycles, "cycles": cycles}


def parcours_predefinis(parcours_id: str | None = None) -> list[dict]:
    rows = db.lire(Q10_PARCOURS, id=parcours_id)
    if parcours_id and not rows:
        raise HTTPException(404, f"Parcours '{parcours_id}' introuvable")
    return rows


def graphe_metier(metier_id: str) -> dict:
    """Sous-graphe autour d'un métier : compétences, formations, prérequis."""
    crud.obtenir("Metier", metier_id)
    rows = db.lire(Q_GRAPHE, id=metier_id)
    noeuds: dict[str, dict] = {}
    aretes: dict[tuple, dict] = {}

    def noeud(id_, nom, label):
        if id_ and id_ not in noeuds:
            noeuds[id_] = {"id": id_, "nom": nom, "label": label}

    def arete(source, cible, type_, **props):
        if source and cible:
            aretes[(source, cible, type_)] = {"source": source, "cible": cible, "type": type_, **props}

    for r in rows:
        noeud(r["m_id"], r["m_nom"], "Metier")
        noeud(r["c_id"], r["c_nom"], "Competence")
        arete(r["m_id"], r["c_id"], "REQUIERT", importance=r["importance"])
        if r["f_id"]:
            noeud(r["f_id"], r["f_nom"], "Formation")
            arete(r["f_id"], r["c_id"], "DEVELOPPE", niveau_acquis=r["niveau_acquis"])
        if r["p_id"]:
            noeud(r["p_id"], r["p_nom"], "Competence")
            arete(r["c_id"], r["p_id"], "PREREQUIS")
    return {"noeuds": list(noeuds.values()), "aretes": list(aretes.values())}


def statistiques() -> dict:
    return {
        "noeuds": {r["label"]: r["nb"] for r in db.lire(Q_STATS_NOEUDS)},
        "relations": {r["type"]: r["nb"] for r in db.lire(Q_STATS_RELATIONS)},
    }
