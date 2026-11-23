"""Modèles Pydantic : validation des données entrantes de l'API."""
import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Niveau = Literal["Débutant", "Intermédiaire", "Avancé"]
Modalite = Literal["En ligne", "Présentiel", "Hybride"]

PATTERN_METIER = r"^M\d{2,3}$"
PATTERN_COMPETENCE = r"^C\d{2,3}$"
PATTERN_FORMATION = r"^F\d{2,3}$"
PATTERN_PARCOURS = r"^P\d{2,3}$"

IdCompetence = Annotated[str, Field(pattern=PATTERN_COMPETENCE)]
_INTERDITS = re.compile(r"[<>\x00-\x08\x0b\x0c\x0e-\x1f]")


class _Base(BaseModel):
    # Espaces superflus supprimés ; champs inconnus refusés (422)
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    @field_validator("*", mode="after")
    @classmethod
    def _refuser_balises_et_caracteres_de_controle(cls, v):
        if isinstance(v, str) and _INTERDITS.search(v):
            raise ValueError("caractères interdits (<, > ou caractères de contrôle)")
        return v


# --------------------------------------------------------------------------
# Entités : création (tous les champs) et modification (champs optionnels)
# --------------------------------------------------------------------------
class MetierCreate(_Base):
    nom: str = Field(min_length=2, max_length=100)
    secteur: str = Field(min_length=2, max_length=60)
    description: str = Field(min_length=5, max_length=500)


class MetierUpdate(_Base):
    nom: str | None = Field(default=None, min_length=2, max_length=100)
    secteur: str | None = Field(default=None, min_length=2, max_length=60)
    description: str | None = Field(default=None, min_length=5, max_length=500)


class CompetenceCreate(_Base):
    nom: str = Field(min_length=2, max_length=100)
    categorie: str = Field(min_length=2, max_length=60)
    description: str = Field(min_length=5, max_length=500)


class CompetenceUpdate(_Base):
    nom: str | None = Field(default=None, min_length=2, max_length=100)
    categorie: str | None = Field(default=None, min_length=2, max_length=60)
    description: str | None = Field(default=None, min_length=5, max_length=500)


class FormationCreate(_Base):
    nom: str = Field(min_length=2, max_length=120)
    organisme: str = Field(min_length=2, max_length=100)
    duree_heures: int = Field(ge=1, le=500)
    niveau: Niveau
    modalite: Modalite
    description: str = Field(min_length=5, max_length=500)


class FormationUpdate(_Base):
    nom: str | None = Field(default=None, min_length=2, max_length=120)
    organisme: str | None = Field(default=None, min_length=2, max_length=100)
    duree_heures: int | None = Field(default=None, ge=1, le=500)
    niveau: Niveau | None = None
    modalite: Modalite | None = None
    description: str | None = Field(default=None, min_length=5, max_length=500)


# --------------------------------------------------------------------------
# Propriétés de relations
# --------------------------------------------------------------------------
class ImportanceIn(_Base):
    importance: int = Field(ge=1, le=5, description="1 = utile, 5 = indispensable")


class NiveauAcquisIn(_Base):
    niveau_acquis: int = Field(ge=1, le=3, description="1 = notions, 3 = maîtrise")


# --------------------------------------------------------------------------
# Moteur de recommandation
# --------------------------------------------------------------------------
class _AvecCompetencesAcquises(_Base):
    competences_acquises: list[IdCompetence] = Field(default_factory=list, max_length=50)

    @field_validator("competences_acquises", mode="after")
    @classmethod
    def _dedoublonner(cls, v: list[str]) -> list[str]:
        return sorted(set(v))


class RecommandationIn(_AvecCompetencesAcquises):
    metier_id: str = Field(pattern=PATTERN_METIER)
    max_formations: int = Field(default=8, ge=1, le=15)


class CouvertureIn(_AvecCompetencesAcquises):
    pass
