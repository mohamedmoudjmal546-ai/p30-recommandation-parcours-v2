#!/usr/bin/env python3
"""Initialisation de la base Neo4j du projet P30.

Étapes :
  1. lecture et validation des CSV du dossier data/ (comptes, clés, références,
     bornes, absence de cycle dans PREREQUIS) ;
  2. connexion à Neo4j (identifiants lus dans .env, jamais dans le code) ;
  3. création des contraintes et index (cypher/01_schema.cypher) ;
  4. chargement idempotent des nœuds et des relations (MERGE) ;
  5. affichage d'un récapitulatif.

Utilisation :
    python init_neo4j.py                    # charge les données (idempotent)
    python init_neo4j.py --reset            # vide la base avant le chargement
    python init_neo4j.py --valider-seulement  # valide les CSV sans toucher à Neo4j
"""
from __future__ import annotations

import argparse
import csv
import os
import re
import sys
import time
from collections import defaultdict, deque
from pathlib import Path

from dotenv import load_dotenv

RACINE = Path(__file__).resolve().parent
DATA_DIR = RACINE / "data"
SCHEMA_FILE = RACINE / "cypher" / "01_schema.cypher"

# Volumes minimaux imposés par la fiche P30
MIN_METIERS, MIN_COMPETENCES, MIN_FORMATIONS, MIN_PARCOURS = 15, 50, 30, 5

NIVEAUX = {"Débutant", "Intermédiaire", "Avancé"}
MODALITES = {"En ligne", "Présentiel", "Hybride"}
PATTERNS_ID = {
    "metiers": re.compile(r"^M\d{2,3}$"),
    "competences": re.compile(r"^C\d{2,3}$"),
    "formations": re.compile(r"^F\d{2,3}$"),
    "parcours": re.compile(r"^P\d{2,3}$"),
}


class DonneesInvalides(Exception):
    """Levée quand les fichiers CSV ne respectent pas le référentiel attendu."""


# ---------------------------------------------------------------------------
# 1. Lecture et validation des CSV
# ---------------------------------------------------------------------------
def lire_csv(nom: str, data_dir: Path = DATA_DIR) -> list[dict]:
    chemin = Path(data_dir) / nom
    if not chemin.exists():
        raise DonneesInvalides(f"Fichier introuvable : {chemin}")
    lignes: list[dict] = []
    with open(chemin, encoding="utf-8-sig", newline="") as f:
        for numero, row in enumerate(csv.DictReader(f), start=2):
            if None in row or any(v is None for v in row.values()):
                raise DonneesInvalides(f"{nom}, ligne {numero} : nombre de colonnes incorrect")
            lignes.append({k.strip(): v.strip() for k, v in row.items()})
    return lignes


def _entier(valeur: str, nom_fichier: str, colonne: str) -> int:
    try:
        return int(valeur)
    except ValueError:
        raise DonneesInvalides(f"{nom_fichier} : '{valeur}' n'est pas un entier ({colonne})") from None


def charger_donnees(data_dir: Path = DATA_DIR) -> dict[str, list[dict]]:
    """Lit tous les CSV et convertit les colonnes numériques."""
    d = {
        "metiers": lire_csv("metiers.csv", data_dir),
        "competences": lire_csv("competences.csv", data_dir),
        "formations": lire_csv("formations.csv", data_dir),
        "parcours": lire_csv("parcours.csv", data_dir),
        "requiert": lire_csv("requiert.csv", data_dir),
        "developpe": lire_csv("developpe.csv", data_dir),
        "prerequis": lire_csv("prerequis.csv", data_dir),
        "mene_a": lire_csv("mene_a.csv", data_dir),
        "parcours_formations": lire_csv("parcours_formations.csv", data_dir),
    }
    for r in d["formations"]:
        r["duree_heures"] = _entier(r["duree_heures"], "formations.csv", "duree_heures")
    for r in d["parcours"]:
        r["duree_mois"] = _entier(r["duree_mois"], "parcours.csv", "duree_mois")
    for r in d["requiert"]:
        r["importance"] = _entier(r["importance"], "requiert.csv", "importance")
    for r in d["developpe"]:
        r["niveau_acquis"] = _entier(r["niveau_acquis"], "developpe.csv", "niveau_acquis")
    for r in d["parcours_formations"]:
        r["ordre"] = _entier(r["ordre"], "parcours_formations.csv", "ordre")
    return d


def a_un_cycle(aretes: list[tuple[str, str]]) -> bool:
    """Détection de cycle par tri topologique (algorithme de Kahn)."""
    voisins: dict[str, list[str]] = defaultdict(list)
    degre_entrant: dict[str, int] = defaultdict(int)
    noeuds: set[str] = set()
    for a, b in aretes:
        voisins[a].append(b)
        degre_entrant[b] += 1
        noeuds.update((a, b))
    file = deque(n for n in noeuds if degre_entrant[n] == 0)
    visites = 0
    while file:
        n = file.popleft()
        visites += 1
        for v in voisins[n]:
            degre_entrant[v] -= 1
            if degre_entrant[v] == 0:
                file.append(v)
    return visites != len(noeuds)


def valider(d: dict[str, list[dict]]) -> list[str]:
    """Retourne la liste des erreurs (liste vide = données valides)."""
    err: list[str] = []

    # --- volumes minimaux ---
    for cle, minimum in (("metiers", MIN_METIERS), ("competences", MIN_COMPETENCES),
                         ("formations", MIN_FORMATIONS), ("parcours", MIN_PARCOURS)):
        if len(d[cle]) < minimum:
            err.append(f"{cle} : {len(d[cle])} lignes (minimum {minimum})")

    # --- identifiants, unicité, champs obligatoires ---
    ids: dict[str, set[str]] = {}
    champs = {
        "metiers": ("nom", "secteur", "description"),
        "competences": ("nom", "categorie", "description"),
        "formations": ("nom", "organisme", "niveau", "modalite", "description"),
        "parcours": ("nom", "description"),
    }
    for cle, pattern in PATTERNS_ID.items():
        vus: set[str] = set()
        noms: set[str] = set()
        for r in d[cle]:
            if not pattern.match(r["id"]):
                err.append(f"{cle} : identifiant invalide '{r['id']}'")
            if r["id"] in vus:
                err.append(f"{cle} : identifiant dupliqué '{r['id']}'")
            vus.add(r["id"])
            for champ in champs[cle]:
                if not r.get(champ):
                    err.append(f"{cle} {r['id']} : champ '{champ}' vide")
            if r["nom"] in noms:
                err.append(f"{cle} : nom dupliqué '{r['nom']}'")
            noms.add(r["nom"])
        ids[cle] = vus

    # --- bornes et énumérations ---
    for r in d["formations"]:
        if not 1 <= r["duree_heures"] <= 500:
            err.append(f"formation {r['id']} : duree_heures hors [1,500]")
        if r["niveau"] not in NIVEAUX:
            err.append(f"formation {r['id']} : niveau '{r['niveau']}' inconnu")
        if r["modalite"] not in MODALITES:
            err.append(f"formation {r['id']} : modalité '{r['modalite']}' inconnue")
    for r in d["parcours"]:
        if r["duree_mois"] < 1:
            err.append(f"parcours {r['id']} : duree_mois < 1")
    for r in d["requiert"]:
        if not 1 <= r["importance"] <= 5:
            err.append(f"REQUIERT {r['metier_id']}->{r['competence_id']} : importance hors [1,5]")
    for r in d["developpe"]:
        if not 1 <= r["niveau_acquis"] <= 3:
            err.append(f"DEVELOPPE {r['formation_id']}->{r['competence_id']} : niveau_acquis hors [1,3]")

    # --- intégrité référentielle et doublons de relations ---
    def verifier(cle_rel, col_a, type_a, col_b, type_b):
        vus: set[tuple[str, str]] = set()
        for r in d[cle_rel]:
            a, b = r[col_a], r[col_b]
            if a not in ids[type_a]:
                err.append(f"{cle_rel} : {col_a} '{a}' inconnu")
            if b not in ids[type_b]:
                err.append(f"{cle_rel} : {col_b} '{b}' inconnu")
            if (a, b) in vus:
                err.append(f"{cle_rel} : relation dupliquée {a}->{b}")
            vus.add((a, b))

    verifier("requiert", "metier_id", "metiers", "competence_id", "competences")
    verifier("developpe", "formation_id", "formations", "competence_id", "competences")
    verifier("prerequis", "competence_id", "competences", "prerequis_id", "competences")
    verifier("mene_a", "parcours_id", "parcours", "metier_id", "metiers")
    verifier("parcours_formations", "parcours_id", "parcours", "formation_id", "formations")

    # --- PREREQUIS : pas de boucle ni de cycle ---
    aretes = [(r["competence_id"], r["prerequis_id"]) for r in d["prerequis"]]
    for a, b in aretes:
        if a == b:
            err.append(f"PREREQUIS : {a} est son propre prérequis")
    if a_un_cycle(aretes):
        err.append("PREREQUIS : le graphe des prérequis contient un cycle")

    # --- couverture du référentiel ---
    metiers_avec_comp = {r["metier_id"] for r in d["requiert"]}
    for m in sorted(ids["metiers"] - metiers_avec_comp):
        err.append(f"métier {m} : aucune compétence requise")
    comp_avec_formation = {r["competence_id"] for r in d["developpe"]}
    for c in sorted(ids["competences"] - comp_avec_formation):
        err.append(f"compétence {c} : aucune formation ne la développe")
    parcours_avec_metier = {r["parcours_id"] for r in d["mene_a"]}
    for p in sorted(ids["parcours"] - parcours_avec_metier):
        err.append(f"parcours {p} : aucun métier cible (MENE_A)")
    ordres: dict[str, list[int]] = defaultdict(list)
    for r in d["parcours_formations"]:
        ordres[r["parcours_id"]].append(r["ordre"])
    for p, liste in ordres.items():
        if sorted(liste) != list(range(1, len(liste) + 1)):
            err.append(f"parcours {p} : les numéros d'ordre doivent être 1..{len(liste)} sans trou")
    return err


# ---------------------------------------------------------------------------
# 2. Neo4j
# ---------------------------------------------------------------------------
def lire_instructions(chemin: Path) -> list[str]:
    """Découpe un fichier .cypher en instructions (commentaires // ignorés)."""
    lignes = [l for l in chemin.read_text(encoding="utf-8").splitlines() if not l.strip().startswith("//")]
    return [s.strip() for s in "\n".join(lignes).split(";") if s.strip()]


def connecter(attente_max: int = 90):
    """Ouvre le driver Neo4j. Les identifiants viennent exclusivement de l'environnement."""
    from neo4j import GraphDatabase
    from neo4j.exceptions import AuthError, ServiceUnavailable

    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD")
    if not password:
        sys.exit("Erreur : NEO4J_PASSWORD est absent. Copiez .env.example en .env et renseignez-le.")

    driver = GraphDatabase.driver(uri, auth=(user, password))
    fin = time.time() + attente_max
    while True:
        try:
            driver.verify_connectivity()
            return driver
        except AuthError:
            driver.close()
            sys.exit("Erreur d'authentification Neo4j : vérifiez NEO4J_USER / NEO4J_PASSWORD dans .env")
        except (ServiceUnavailable, OSError) as exc:
            if time.time() > fin:
                driver.close()
                sys.exit(f"Neo4j injoignable sur {uri} ({exc}). Lancez : docker compose up -d")
            print("… en attente de Neo4j")
            time.sleep(3)


NOEUDS = [
    ("Metier", "metiers", "UNWIND $rows AS row MERGE (n:Metier {id: row.id}) SET n += row"),
    ("Competence", "competences", "UNWIND $rows AS row MERGE (n:Competence {id: row.id}) SET n += row"),
    ("Formation", "formations", "UNWIND $rows AS row MERGE (n:Formation {id: row.id}) SET n += row"),
    ("Parcours", "parcours", "UNWIND $rows AS row MERGE (n:Parcours {id: row.id}) SET n += row"),
]

RELATIONS = [
    ("REQUIERT", "requiert", """
        UNWIND $rows AS row
        MATCH (m:Metier {id: row.metier_id}), (c:Competence {id: row.competence_id})
        MERGE (m)-[r:REQUIERT]->(c) SET r.importance = row.importance"""),
    ("DEVELOPPE", "developpe", """
        UNWIND $rows AS row
        MATCH (f:Formation {id: row.formation_id}), (c:Competence {id: row.competence_id})
        MERGE (f)-[d:DEVELOPPE]->(c) SET d.niveau_acquis = row.niveau_acquis"""),
    ("PREREQUIS", "prerequis", """
        UNWIND $rows AS row
        MATCH (c:Competence {id: row.competence_id}), (p:Competence {id: row.prerequis_id})
        MERGE (c)-[:PREREQUIS]->(p)"""),
    ("MENE_A", "mene_a", """
        UNWIND $rows AS row
        MATCH (p:Parcours {id: row.parcours_id}), (m:Metier {id: row.metier_id})
        MERGE (p)-[:MENE_A]->(m)"""),
    ("INCLUT", "parcours_formations", """
        UNWIND $rows AS row
        MATCH (p:Parcours {id: row.parcours_id}), (f:Formation {id: row.formation_id})
        MERGE (p)-[i:INCLUT]->(f) SET i.ordre = row.ordre"""),
]


def charger(driver, database: str, d: dict[str, list[dict]], reset: bool) -> None:
    with driver.session(database=database) as session:
        if reset:
            session.run("MATCH (n) DETACH DELETE n").consume()
            print("Base vidée.")
        for instruction in lire_instructions(SCHEMA_FILE):
            session.run(instruction).consume()
        print(f"Schéma appliqué ({SCHEMA_FILE.name}).")
        for label, cle, requete in NOEUDS:
            session.execute_write(lambda tx, q=requete, r=d[cle]: tx.run(q, rows=r).consume())
            print(f"  ✓ {len(d[cle]):>3} nœuds {label}")
        for type_rel, cle, requete in RELATIONS:
            session.execute_write(lambda tx, q=requete, r=d[cle]: tx.run(q, rows=r).consume())
            print(f"  ✓ {len(d[cle]):>3} relations {type_rel}")


def recapitulatif(driver, database: str) -> None:
    with driver.session(database=database) as session:
        noeuds = session.run("MATCH (n) RETURN labels(n)[0] AS label, count(n) AS n ORDER BY label").data()
        rels = session.run("MATCH ()-[r]->() RETURN type(r) AS type, count(r) AS n ORDER BY type").data()
        cycles = session.run(
            "MATCH p=(c:Competence)-[:PREREQUIS*1..10]->(c) RETURN count(p) AS n").single()["n"]
    print("\nRécapitulatif :")
    for r in noeuds:
        print(f"  (:{r['label']}) : {r['n']}")
    for r in rels:
        print(f"  [:{r['type']}] : {r['n']}")
    print(f"  Cycles PREREQUIS détectés : {cycles}")
    if cycles:
        sys.exit("Le graphe des prérequis contient un cycle : corrigez data/prerequis.csv")


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialise la base Neo4j du projet P30")
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR, help="dossier des CSV")
    parser.add_argument("--reset", action="store_true", help="supprime tous les nœuds avant chargement")
    parser.add_argument("--valider-seulement", action="store_true", help="valide les CSV sans écrire dans Neo4j")
    args = parser.parse_args()

    load_dotenv(RACINE / ".env")
    try:
        donnees = charger_donnees(args.data_dir)
    except DonneesInvalides as exc:
        sys.exit(f"Erreur de lecture des données : {exc}")

    erreurs = valider(donnees)
    if erreurs:
        print("Données invalides :", file=sys.stderr)
        for e in erreurs:
            print(f"  - {e}", file=sys.stderr)
        sys.exit(1)
    print(f"Données valides : {len(donnees['metiers'])} métiers, {len(donnees['competences'])} compétences, "
          f"{len(donnees['formations'])} formations, {len(donnees['parcours'])} parcours.")
    if args.valider_seulement:
        return

    database = os.getenv("NEO4J_DATABASE", "neo4j")
    driver = connecter()
    try:
        charger(driver, database, donnees, args.reset)
        recapitulatif(driver, database)
    finally:
        driver.close()


if __name__ == "__main__":
    main()
