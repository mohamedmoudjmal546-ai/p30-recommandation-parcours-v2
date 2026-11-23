"""Opérations CRUD génériques sur les nœuds et relations.

Les labels (Metier, Competence...) et noms de champs proviennent du code,
jamais de l'utilisateur ; toutes les valeurs passent par des paramètres Cypher.
"""
from fastapi import HTTPException

import  database as db


# ---------------------------------------------------------------------------
# Nœuds
# ---------------------------------------------------------------------------
def prochain_id(label: str, prefixe: str) -> str:
    rows = db.lire(f"MATCH (n:{label}) RETURN coalesce(max(toInteger(substring(n.id, 1))), 0) AS dernier")
    return f"{prefixe}{rows[0]['dernier'] + 1:02d}"


def lister(label: str, filtres: dict[str, str | None], q: str | None, skip: int, limit: int) -> list[dict]:
    conditions, params = [], {"skip": skip, "limit": limit}
    for champ, valeur in filtres.items():
        if valeur:
            conditions.append(f"n.{champ} = ${champ}")
            params[champ] = valeur
    if q:
        conditions.append("toLower(n.nom) CONTAINS toLower($q)")
        params["q"] = q
    clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    rows = db.lire(
        f"MATCH (n:{label}) {clause} RETURN properties(n) AS n ORDER BY n.id SKIP $skip LIMIT $limit", **params)
    return [r["n"] for r in rows]


def obtenir(label: str, id_: str) -> dict:
    rows = db.lire(f"MATCH (n:{label} {{id: $id}}) RETURN properties(n) AS n", id=id_)
    if not rows:
        raise HTTPException(404, f"{label} '{id_}' introuvable")
    return rows[0]["n"]


def _verifier_nom_libre(label: str, nom: str, sauf_id: str | None = None) -> None:
    rows = db.lire(f"MATCH (n:{label} {{nom: $nom}}) WHERE n.id <> $sauf RETURN n.id AS id",
                   nom=nom, sauf=sauf_id or "")
    if rows:
        raise HTTPException(409, f"Le nom '{nom}' est déjà utilisé par {rows[0]['id']}")


def creer(label: str, prefixe: str, donnees: dict) -> dict:
    _verifier_nom_libre(label, donnees["nom"])
    props = {**donnees, "id": prochain_id(label, prefixe)}
    rows = db.ecrire(f"CREATE (n:{label}) SET n = $props RETURN properties(n) AS n", props=props)
    return rows[0]["n"]


def modifier(label: str, id_: str, changements: dict) -> dict:
    if not changements:
        raise HTTPException(400, "Aucun champ à modifier")
    obtenir(label, id_)
    if "nom" in changements:
        _verifier_nom_libre(label, changements["nom"], sauf_id=id_)
    rows = db.ecrire(
        f"MATCH (n:{label} {{id: $id}}) SET n += $changements RETURN properties(n) AS n",
        id=id_, changements=changements)
    return rows[0]["n"]


def supprimer(label: str, id_: str, force: bool) -> None:
    obtenir(label, id_)
    if not force:
        nb = db.lire(f"MATCH (n:{label} {{id: $id}})-[r]-() RETURN count(r) AS nb", id=id_)[0]["nb"]
        if nb:
            raise HTTPException(
                409, f"{label} '{id_}' possède {nb} relation(s) : utilisez force=true pour les supprimer aussi")
    db.ecrire(f"MATCH (n:{label} {{id: $id}}) DETACH DELETE n", id=id_)


# ---------------------------------------------------------------------------
# Relations
# ---------------------------------------------------------------------------
def competences_du_metier(metier_id: str) -> list[dict]:
    obtenir("Metier", metier_id)
    return db.lire(
        """MATCH (:Metier {id: $id})-[r:REQUIERT]->(c:Competence)
           RETURN c.id AS id, c.nom AS nom, c.categorie AS categorie, r.importance AS importance
           ORDER BY importance DESC, nom""", id=metier_id)


def definir_requiert(metier_id: str, competence_id: str, importance: int) -> dict:
    rows = db.ecrire(
        """MATCH (m:Metier {id: $m}), (c:Competence {id: $c})
           MERGE (m)-[r:REQUIERT]->(c) SET r.importance = $importance
           RETURN m.id AS metier_id, c.id AS competence_id, r.importance AS importance""",
        m=metier_id, c=competence_id, importance=importance)
    if not rows:
        raise HTTPException(404, "Métier ou compétence introuvable")
    return rows[0]


def retirer_requiert(metier_id: str, competence_id: str) -> None:
    rows = db.ecrire(
        "MATCH (:Metier {id: $m})-[r:REQUIERT]->(:Competence {id: $c}) DELETE r RETURN 1 AS n",
        m=metier_id, c=competence_id)
    if not rows:
        raise HTTPException(404, "Relation REQUIERT introuvable")


def competences_de_la_formation(formation_id: str) -> list[dict]:
    obtenir("Formation", formation_id)
    return db.lire(
        """MATCH (:Formation {id: $id})-[d:DEVELOPPE]->(c:Competence)
           RETURN c.id AS id, c.nom AS nom, c.categorie AS categorie, d.niveau_acquis AS niveau_acquis
           ORDER BY niveau_acquis DESC, nom""", id=formation_id)


def definir_developpe(formation_id: str, competence_id: str, niveau_acquis: int) -> dict:
    rows = db.ecrire(
        """MATCH (f:Formation {id: $f}), (c:Competence {id: $c})
           MERGE (f)-[d:DEVELOPPE]->(c) SET d.niveau_acquis = $niveau
           RETURN f.id AS formation_id, c.id AS competence_id, d.niveau_acquis AS niveau_acquis""",
        f=formation_id, c=competence_id, niveau=niveau_acquis)
    if not rows:
        raise HTTPException(404, "Formation ou compétence introuvable")
    return rows[0]


def retirer_developpe(formation_id: str, competence_id: str) -> None:
    rows = db.ecrire(
        "MATCH (:Formation {id: $f})-[d:DEVELOPPE]->(:Competence {id: $c}) DELETE d RETURN 1 AS n",
        f=formation_id, c=competence_id)
    if not rows:
        raise HTTPException(404, "Relation DEVELOPPE introuvable")


def ajouter_prerequis(competence_id: str, prerequis_id: str) -> dict:
    """Crée (competence)-[:PREREQUIS]->(prerequis) en refusant boucles et cycles."""
    if competence_id == prerequis_id:
        raise HTTPException(400, "Une compétence ne peut pas être son propre prérequis")
    rows = db.lire(
        """MATCH (a:Competence {id: $a}), (b:Competence {id: $b})
           RETURN EXISTS { (b)-[:PREREQUIS*1..20]->(a) } AS cycle""",
        a=competence_id, b=prerequis_id)
    if not rows:
        raise HTTPException(404, "Compétence ou prérequis introuvable")
    if rows[0]["cycle"]:
        raise HTTPException(409, f"{prerequis_id} dépend déjà (directement ou non) de {competence_id} : cycle interdit")
    db.ecrire(
        """MATCH (a:Competence {id: $a}), (b:Competence {id: $b}) MERGE (a)-[:PREREQUIS]->(b)""",
        a=competence_id, b=prerequis_id)
    return {"competence_id": competence_id, "prerequis_id": prerequis_id}


def retirer_prerequis(competence_id: str, prerequis_id: str) -> None:
    rows = db.ecrire(
        "MATCH (:Competence {id: $a})-[r:PREREQUIS]->(:Competence {id: $b}) DELETE r RETURN 1 AS n",
        a=competence_id, b=prerequis_id)
    if not rows:
        raise HTTPException(404, "Relation PREREQUIS introuvable")
