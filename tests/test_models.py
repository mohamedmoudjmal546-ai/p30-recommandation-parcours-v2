"""Tests de validation des données entrantes (Pydantic)."""
import pytest
from pydantic import ValidationError

from backend.models import (CompetenceCreate, FormationCreate, FormationUpdate, ImportanceIn, MetierCreate,
                            RecommandationIn)

FORMATION_OK = {"nom": "Test Formation", "organisme": "Académie Test", "duree_heures": 20,
                "niveau": "Débutant", "modalite": "En ligne", "description": "Description valide"}


def test_formation_valide():
    assert FormationCreate(**FORMATION_OK).duree_heures == 20


@pytest.mark.parametrize("champ,valeur", [
    ("duree_heures", 0), ("duree_heures", 501), ("niveau", "Expert"), ("modalite", "Sur la lune"),
    ("nom", "A"), ("nom", "<script>alert(1)</script>"), ("description", "ok\x00ok ok"),
])
def test_formation_invalide(champ, valeur):
    with pytest.raises(ValidationError):
        FormationCreate(**{**FORMATION_OK, champ: valeur})


def test_champ_inconnu_refuse():
    with pytest.raises(ValidationError):
        MetierCreate(nom="Métier", secteur="Data", description="Description valide", salaire=10)


def test_espaces_supprimes():
    c = CompetenceCreate(nom="  Python  ", categorie=" Programmation ", description="Langage polyvalent")
    assert c.nom == "Python" and c.categorie == "Programmation"


def test_update_partiel():
    assert FormationUpdate(duree_heures=30).model_dump(exclude_none=True) == {"duree_heures": 30}


@pytest.mark.parametrize("valeur", [0, 6, -1])
def test_importance_hors_bornes(valeur):
    with pytest.raises(ValidationError):
        ImportanceIn(importance=valeur)


def test_recommandation_dedoublonne_et_trie():
    r = RecommandationIn(metier_id="M02", competences_acquises=["C02", "C01", "C02"])
    assert r.competences_acquises == ["C01", "C02"] and r.max_formations == 8


@pytest.mark.parametrize("donnees", [
    {"metier_id": "X02"}, {"metier_id": "M02", "competences_acquises": ["Python"]},
    {"metier_id": "M02", "max_formations": 0}, {"metier_id": "M02", "competences_acquises": ["C01"] * 2 + ["C%02d" % i for i in range(2, 53)]},
])
def test_recommandation_invalide(donnees):
    with pytest.raises(ValidationError):
        RecommandationIn(**donnees)
