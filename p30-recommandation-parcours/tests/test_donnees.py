"""Tests du référentiel CSV (n'exigent pas Neo4j)."""
import copy
from collections import deque

import pytest

import init_neo4j as init


@pytest.fixture(scope="module")
def donnees():
    return init.charger_donnees()


def test_volumes_imposes(donnees):
    assert len(donnees["metiers"]) == 15
    assert len(donnees["competences"]) == 50
    assert len(donnees["formations"]) == 30
    assert len(donnees["parcours"]) == 5


def test_referentiel_valide(donnees):
    assert init.valider(donnees) == []


def test_prerequis_sans_cycle(donnees):
    aretes = [(r["competence_id"], r["prerequis_id"]) for r in donnees["prerequis"]]
    assert not init.a_un_cycle(aretes)


def test_cycle_detecte():
    assert init.a_un_cycle([("A", "B"), ("B", "C"), ("C", "A")])
    assert not init.a_un_cycle([("A", "B"), ("B", "C"), ("A", "C")])


def test_reference_inconnue_detectee(donnees):
    d = copy.deepcopy(donnees)
    d["requiert"].append({"metier_id": "M99", "competence_id": "C01", "importance": 3})
    assert any("M99" in e for e in init.valider(d))


def test_importance_hors_bornes_detectee(donnees):
    d = copy.deepcopy(donnees)
    d["requiert"][0]["importance"] = 9
    assert any("importance" in e for e in init.valider(d))


def test_cycle_dans_prerequis_detecte(donnees):
    d = copy.deepcopy(donnees)
    d["prerequis"].append({"competence_id": "C01", "prerequis_id": "C15"})  # C15 -> C14 -> C12 -> C01
    assert any("cycle" in e for e in init.valider(d))


def test_chaque_metier_a_au_moins_cinq_competences(donnees):
    nb = {}
    for r in donnees["requiert"]:
        nb[r["metier_id"]] = nb.get(r["metier_id"], 0) + 1
    assert min(nb.values()) >= 5


# --- Vérification des résultats annoncés dans cypher/02_requetes_5_obligatoires.cypher ---
def _prerequis(donnees):
    g = {}
    for r in donnees["prerequis"]:
        g.setdefault(r["competence_id"], []).append(r["prerequis_id"])
    return g


def _distances(g, depart, max_prof):
    """Équivalent de MATCH p=(c)-[:PREREQUIS*1..N]->(pre) WITH pre, min(length(p))."""
    res, file = {}, deque([(depart, 0)])
    while file:
        noeud, d = file.popleft()
        if d == max_prof:
            continue
        for p in g.get(noeud, []):
            if p not in res or d + 1 < res[p]:
                res[p] = d + 1
                file.append((p, d + 1))
    return res


def test_q1_prerequis_du_deep_learning(donnees):
    dist = _distances(_prerequis(donnees), "C15", 4)
    assert dist == {"C14": 1, "C12": 2, "C11": 2, "C01": 3, "C10": 3}


def test_q2a_chemin_microservices_algorithmique(donnees):
    assert _distances(_prerequis(donnees), "C50", 6)["C07"] == 3


def test_q2b_chemin_data_scientist_vers_formation_neo4j(donnees):
    """shortestPath non orienté sur REQUIERT|PREREQUIS|DEVELOPPE entre M02 et F20."""
    adj = {}

    def lier(a, b):
        adj.setdefault(a, set()).add(b)
        adj.setdefault(b, set()).add(a)

    for r in donnees["requiert"]:
        lier(r["metier_id"], r["competence_id"])
    for r in donnees["developpe"]:
        lier(r["formation_id"], r["competence_id"])
    for r in donnees["prerequis"]:
        lier(r["competence_id"], r["prerequis_id"])
    vus, file = {"M02": 0}, deque(["M02"])
    while file:
        n = file.popleft()
        for v in adj[n]:
            if v not in vus:
                vus[v] = vus[n] + 1
                file.append(v)
    assert vus["F20"] == 4
