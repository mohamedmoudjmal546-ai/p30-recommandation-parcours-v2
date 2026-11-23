"""Teste la construction du parcours en simulant en Python les requêtes Q6 sur les CSV."""
import pytest

import init_neo4j as init
from backend.planification import construire_parcours

ACQUIS_ETUDIANT = {"C01", "C02", "C05", "C06"}  # Python, SQL, Linux, Git


@pytest.fixture(scope="module")
def d():
    return init.charger_donnees()


def _fermeture(d, ids):
    g = {}
    for r in d["prerequis"]:
        g.setdefault(r["competence_id"], []).append(r["prerequis_id"])
    res, pile = set(ids), list(ids)
    while pile:
        for p in g.get(pile.pop(), []):
            if p not in res:
                res.add(p)
                pile.append(p)
    return res


def _besoins(d, metier_id, acquis, profondeur_max=4):
    """Équivalent de Q6_BESOINS : (c)-[:PREREQUIS*0..4]->(besoin) WHERE NOT besoin IN acquis."""
    g, noms = {}, {c["id"]: c["nom"] for c in d["competences"]}
    for r in d["prerequis"]:
        g.setdefault(r["competence_id"], []).append(r["prerequis_id"])
    besoins = {}

    def parcourir(noeud, longueur, importance):
        if noeud not in acquis:
            b = besoins.setdefault(noeud, {"id": noeud, "nom": noms[noeud], "profondeur": 0, "poids": 0})
            b["profondeur"] = max(b["profondeur"], longueur)
            b["poids"] = max(b["poids"], importance)
        if longueur < profondeur_max:
            for p in g.get(noeud, []):
                parcourir(p, longueur + 1, importance)

    for r in d["requiert"]:
        if r["metier_id"] == metier_id:
            parcourir(r["competence_id"], 0, r["importance"])
    return besoins


def _candidats(d, ids):
    par_formation = {}
    for r in d["developpe"]:
        if r["competence_id"] in ids:
            par_formation.setdefault(r["formation_id"], []).append(
                {"id": r["competence_id"], "niveau": r["niveau_acquis"]})
    infos = {f["id"]: f for f in d["formations"]}
    return [{"id": fid, "nom": infos[fid]["nom"], "niveau": infos[fid]["niveau"],
             "duree_heures": infos[fid]["duree_heures"], "couvre": couvre}
            for fid, couvre in par_formation.items()]


def _plan(d, metier_id, acquis, max_formations=15):
    acq = _fermeture(d, acquis)
    besoins = _besoins(d, metier_id, acq)
    deps = [(r["competence_id"], r["prerequis_id"]) for r in d["prerequis"]
            if r["competence_id"] in besoins and r["prerequis_id"] in besoins]
    return besoins, deps, construire_parcours(besoins, _candidats(d, set(besoins)), deps, max_formations)


@pytest.mark.parametrize("metier", [m["id"] for m in init.charger_donnees()["metiers"]])
def test_tous_les_metiers_sont_couverts_et_ordonnes(d, metier):
    besoins, deps, plan = _plan(d, metier, set())
    assert plan["competences_non_couvertes"] == []
    couvert = {c["id"] for e in plan["etapes"] for c in e["competences"]}
    assert couvert == set(besoins)
    # Une compétence ne doit jamais être apprise avant son prérequis (si celui-ci est dans le plan)
    rang = {c["id"]: e["ordre"] for e in plan["etapes"] for c in e["competences"]}
    for competence, prerequis in deps:
        assert rang[prerequis] <= rang[competence], f"{prerequis} doit précéder {competence}"


def test_scenario_data_scientist(d):
    besoins, _, plan = _plan(d, "M02", ACQUIS_ETUDIANT)
    assert not (set(besoins) & _fermeture(d, ACQUIS_ETUDIANT))  # rien d'acquis dans les besoins
    ids = [e["formation_id"] for e in plan["etapes"]]
    assert "F10" in ids and "F11" in ids and "F12" in ids and "F13" in ids
    # Mathématiques/Statistiques (F10) avant Machine Learning (F12) avant Deep Learning (F13)
    assert ids.index("F10") < ids.index("F12") < ids.index("F13")
    assert plan["duree_totale_heures"] == sum(e["duree_heures"] for e in plan["etapes"])


def test_metier_deja_couvert():
    d = init.charger_donnees()
    tout = {r["competence_id"] for r in d["requiert"] if r["metier_id"] == "M13"}
    _, _, plan = _plan(d, "M13", _fermeture(d, tout))
    assert plan["etapes"] == [] and plan["competences_non_couvertes"] == []


def test_limite_de_formations(d):
    _, _, plan = _plan(d, "M08", set(), max_formations=3)
    assert plan["nb_formations"] == 3
    assert plan["competences_non_couvertes"]  # la limite laisse des compétences non couvertes
