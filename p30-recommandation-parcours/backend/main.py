"""API REST du projet P30 : recommandation de parcours de formation par compétences.

Lancement :  uvicorn backend.main:app --reload --port 8000
Documentation interactive : http://localhost:8000/docs

Sécurité :
  * lectures publiques ; écritures (POST/PUT/DELETE) protégées par l'en-tête X-API-Key ;
  * données entrantes validées par Pydantic (types, bornes, énumérations, extra=forbid) ;
  * erreurs Neo4j converties en réponses HTTP propres, sans fuite de détails internes.
"""
import logging
import secrets
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Path, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from neo4j.exceptions import AuthError, ConstraintError, DriverError, Neo4jError

import  crud, recommender
import  database as db
from config import get_settings, origines_cors
from models import (CompetenceCreate, CompetenceUpdate, CouvertureIn, FormationCreate, FormationUpdate,
                     ImportanceIn, MetierCreate, MetierUpdate, Modalite, NiveauAcquisIn, Niveau,
                     PATTERN_COMPETENCE, PATTERN_FORMATION, PATTERN_METIER, PATTERN_PARCOURS,
                     RecommandationIn)

log = logging.getLogger("p30.api")

IdMetier = Annotated[str, Path(pattern=PATTERN_METIER, description="Identifiant métier, ex. M01")]
IdCompetence = Annotated[str, Path(pattern=PATTERN_COMPETENCE, description="Identifiant compétence, ex. C01")]
IdFormation = Annotated[str, Path(pattern=PATTERN_FORMATION, description="Identifiant formation, ex. F01")]
IdParcours = Annotated[str, Path(pattern=PATTERN_PARCOURS, description="Identifiant parcours, ex. P01")]
Skip = Annotated[int, Query(ge=0, description="Nombre de résultats à ignorer")]
Limit = Annotated[int, Query(ge=1, le=500, description="Nombre maximal de résultats")]
Recherche = Annotated[str | None, Query(max_length=100, description="Recherche dans le nom")]
Force = Annotated[bool, Query(description="Supprimer aussi les relations rattachées")]


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()  # échoue immédiatement si .env est incomplet
    if not settings.api_key:
        log.warning("API_KEY non définie : les écritures seront refusées (503).")
    try:
        db.verifier_connexion()
        log.info("Connexion Neo4j établie (%s)", settings.neo4j_uri)
    except Exception as exc:  # l'API démarre quand même ; /health indiquera le problème
        log.warning("Neo4j injoignable au démarrage : %s", exc)
    yield
    db.fermer_driver()


app = FastAPI(
    title="P30 - Recommandation de parcours de formation",
    description="Graphe de connaissances Neo4j : Métiers -> Compétences -> Formations -> Parcours.",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=origines_cors(),
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "X-API-Key"],
)


def exiger_cle_api(x_api_key: Annotated[str | None, Header()] = None) -> None:
    """Dépendance appliquée à toutes les routes d'écriture."""
    attendue = get_settings().api_key
    if not attendue:
        raise HTTPException(503, "Écritures désactivées : API_KEY n'est pas configurée côté serveur")
    if not x_api_key or not secrets.compare_digest(x_api_key.encode(), attendue.encode()):
        raise HTTPException(401, "Clé API absente ou invalide", headers={"WWW-Authenticate": "ApiKey"})


ECRITURE = [Depends(exiger_cle_api)]


# ---------------------------------------------------------------------------
# Gestion centralisée des erreurs
# ---------------------------------------------------------------------------
def _reponse(code: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=code, content={"detail": message})


@app.exception_handler(ConstraintError)
async def _contrainte(_: Request, exc: ConstraintError):
    log.info("Contrainte Neo4j violée : %s", exc)
    return _reponse(409, "Conflit : un élément avec le même identifiant ou le même nom existe déjà")


@app.exception_handler(AuthError)
async def _auth(_: Request, exc: AuthError):
    log.error("Authentification Neo4j refusée : %s", exc)
    return _reponse(503, "Base de données indisponible (authentification refusée)")


@app.exception_handler(DriverError)
async def _driver(_: Request, exc: DriverError):
    log.error("Neo4j indisponible : %s", exc)
    return _reponse(503, "Base de données indisponible, réessayez plus tard")


@app.exception_handler(Neo4jError)
async def _neo4j(_: Request, exc: Neo4jError):
    log.exception("Erreur Neo4j : %s", exc)
    return _reponse(500, "Erreur interne de la base de données")


@app.exception_handler(Exception)
async def _inattendue(_: Request, exc: Exception):
    log.exception("Erreur inattendue : %s", exc)
    return _reponse(500, "Erreur interne du serveur")


# ---------------------------------------------------------------------------
# Santé
# ---------------------------------------------------------------------------
@app.get("/health", tags=["Santé"])
def health():
    try:
        db.lire("RETURN 1 AS ok")
    except Exception as exc:
        log.warning("health : %s", exc)
        return JSONResponse(status_code=503, content={"api": "ok", "neo4j": "indisponible"})
    return {"api": "ok", "neo4j": "ok"}


@app.get("/stats", tags=["Santé"])
def stats():
    """Nombre de nœuds par label et de relations par type."""
    return recommender.statistiques()


# ---------------------------------------------------------------------------
# CRUD Métiers
# ---------------------------------------------------------------------------
@app.get("/metiers", tags=["Métiers"])
def lister_metiers(secteur: str | None = None, q: Recherche = None, skip: Skip = 0, limit: Limit = 100):
    return crud.lister("Metier", {"secteur": secteur}, q, skip, limit)


@app.get("/metiers/{metier_id}", tags=["Métiers"])
def lire_metier(metier_id: IdMetier):
    return crud.obtenir("Metier", metier_id)


@app.post("/metiers", status_code=201, tags=["Métiers"], dependencies=ECRITURE)
def creer_metier(data: MetierCreate):
    return crud.creer("Metier", "M", data.model_dump())


@app.put("/metiers/{metier_id}", tags=["Métiers"], dependencies=ECRITURE)
def modifier_metier(metier_id: IdMetier, data: MetierUpdate):
    return crud.modifier("Metier", metier_id, data.model_dump(exclude_none=True))


@app.delete("/metiers/{metier_id}", status_code=204, tags=["Métiers"], dependencies=ECRITURE)
def supprimer_metier(metier_id: IdMetier, force: Force = False):
    crud.supprimer("Metier", metier_id, force)
    return Response(status_code=204)


@app.get("/metiers/{metier_id}/competences", tags=["Métiers"])
def competences_requises(metier_id: IdMetier):
    """Compétences requises par un métier (relation REQUIERT)."""
    return crud.competences_du_metier(metier_id)


@app.put("/metiers/{metier_id}/competences/{competence_id}", tags=["Métiers"], dependencies=ECRITURE)
def definir_competence_requise(metier_id: IdMetier, competence_id: IdCompetence, data: ImportanceIn):
    """Crée ou met à jour (Metier)-[:REQUIERT {importance}]->(Competence)."""
    return crud.definir_requiert(metier_id, competence_id, data.importance)


@app.delete("/metiers/{metier_id}/competences/{competence_id}", status_code=204, tags=["Métiers"],
            dependencies=ECRITURE)
def retirer_competence_requise(metier_id: IdMetier, competence_id: IdCompetence):
    crud.retirer_requiert(metier_id, competence_id)
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# CRUD Compétences
# ---------------------------------------------------------------------------
@app.get("/competences", tags=["Compétences"])
def lister_competences(categorie: str | None = None, q: Recherche = None, skip: Skip = 0, limit: Limit = 100):
    return crud.lister("Competence", {"categorie": categorie}, q, skip, limit)


@app.get("/competences/{competence_id}", tags=["Compétences"])
def lire_competence(competence_id: IdCompetence):
    return crud.obtenir("Competence", competence_id)


@app.post("/competences", status_code=201, tags=["Compétences"], dependencies=ECRITURE)
def creer_competence(data: CompetenceCreate):
    return crud.creer("Competence", "C", data.model_dump())


@app.put("/competences/{competence_id}", tags=["Compétences"], dependencies=ECRITURE)
def modifier_competence(competence_id: IdCompetence, data: CompetenceUpdate):
    return crud.modifier("Competence", competence_id, data.model_dump(exclude_none=True))


@app.delete("/competences/{competence_id}", status_code=204, tags=["Compétences"], dependencies=ECRITURE)
def supprimer_competence(competence_id: IdCompetence, force: Force = False):
    crud.supprimer("Competence", competence_id, force)
    return Response(status_code=204)


@app.get("/competences/{competence_id}/prerequis", tags=["Compétences"])
def prerequis_transitifs(competence_id: IdCompetence,
                         profondeur: Annotated[int, Query(ge=1, le=4, description="Profondeur *1..N")] = 4):
    """Prérequis directs et indirects (parcours de graphe PREREQUIS*1..N)."""
    return recommender.prerequis_transitifs(competence_id, profondeur)


@app.put("/competences/{competence_id}/prerequis/{prerequis_id}", tags=["Compétences"], dependencies=ECRITURE)
def ajouter_prerequis(competence_id: IdCompetence, prerequis_id: IdCompetence):
    """Crée (competence)-[:PREREQUIS]->(prerequis) ; refuse les boucles et les cycles."""
    return crud.ajouter_prerequis(competence_id, prerequis_id)


@app.delete("/competences/{competence_id}/prerequis/{prerequis_id}", status_code=204, tags=["Compétences"],
            dependencies=ECRITURE)
def retirer_prerequis(competence_id: IdCompetence, prerequis_id: IdCompetence):
    crud.retirer_prerequis(competence_id, prerequis_id)
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# CRUD Formations
# ---------------------------------------------------------------------------
@app.get("/formations", tags=["Formations"])
def lister_formations(niveau: Niveau | None = None, modalite: Modalite | None = None, q: Recherche = None,
                      skip: Skip = 0, limit: Limit = 100):
    return crud.lister("Formation", {"niveau": niveau, "modalite": modalite}, q, skip, limit)


@app.get("/formations/{formation_id}", tags=["Formations"])
def lire_formation(formation_id: IdFormation):
    return crud.obtenir("Formation", formation_id)


@app.post("/formations", status_code=201, tags=["Formations"], dependencies=ECRITURE)
def creer_formation(data: FormationCreate):
    return crud.creer("Formation", "F", data.model_dump())


@app.put("/formations/{formation_id}", tags=["Formations"], dependencies=ECRITURE)
def modifier_formation(formation_id: IdFormation, data: FormationUpdate):
    return crud.modifier("Formation", formation_id, data.model_dump(exclude_none=True))


@app.delete("/formations/{formation_id}", status_code=204, tags=["Formations"], dependencies=ECRITURE)
def supprimer_formation(formation_id: IdFormation, force: Force = False):
    crud.supprimer("Formation", formation_id, force)
    return Response(status_code=204)


@app.get("/formations/{formation_id}/competences", tags=["Formations"])
def competences_developpees(formation_id: IdFormation):
    """Compétences développées par une formation (relation DEVELOPPE)."""
    return crud.competences_de_la_formation(formation_id)


@app.put("/formations/{formation_id}/competences/{competence_id}", tags=["Formations"], dependencies=ECRITURE)
def definir_competence_developpee(formation_id: IdFormation, competence_id: IdCompetence, data: NiveauAcquisIn):
    """Crée ou met à jour (Formation)-[:DEVELOPPE {niveau_acquis}]->(Competence)."""
    return crud.definir_developpe(formation_id, competence_id, data.niveau_acquis)


@app.delete("/formations/{formation_id}/competences/{competence_id}", status_code=204, tags=["Formations"],
            dependencies=ECRITURE)
def retirer_competence_developpee(formation_id: IdFormation, competence_id: IdCompetence):
    crud.retirer_developpe(formation_id, competence_id)
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Parcours prédéfinis (lecture)
# ---------------------------------------------------------------------------
@app.get("/parcours", tags=["Parcours"])
def lister_parcours():
    """Les parcours de formation prédéfinis, avec leurs formations dans l'ordre."""
    return recommender.parcours_predefinis()


@app.get("/parcours/{parcours_id}", tags=["Parcours"])
def lire_parcours(parcours_id: IdParcours):
    return recommender.parcours_predefinis(parcours_id)[0]


# ---------------------------------------------------------------------------
# Moteur de recommandation et analyses de graphe
# ---------------------------------------------------------------------------
@app.post("/recommandation", tags=["Recommandation"])
def recommander(data: RecommandationIn):
    """Compétences manquantes, formations classées et parcours ordonné vers un métier cible."""
    return recommender.recommander(data.metier_id, data.competences_acquises, data.max_formations)


@app.get("/chemin", tags=["Graphe"])
def plus_court_chemin(source: Annotated[str, Query(pattern=r"^[MCFP]\d{2,3}$", description="Ex. M02")],
                      cible: Annotated[str, Query(pattern=r"^[MCFP]\d{2,3}$", description="Ex. F20")]):
    """Plus court chemin (shortestPath) entre deux nœuds quelconques du graphe."""
    return recommender.plus_court_chemin(source, cible)


@app.get("/graphe/metier/{metier_id}", tags=["Graphe"])
def graphe_du_metier(metier_id: IdMetier):
    """Sous-graphe (métier, compétences, prérequis, formations) pour la visualisation."""
    return recommender.graphe_metier(metier_id)


@app.post("/analyses/couverture", tags=["Analyses"])
def couverture(data: CouvertureIn):
    """Taux de couverture de chacun des métiers selon les compétences acquises."""
    return recommender.couverture_metiers(data.competences_acquises)


@app.get("/analyses/competences-pivot", tags=["Analyses"])
def competences_pivot(limite: Annotated[int, Query(ge=1, le=50)] = 10):
    return recommender.competences_pivot(limite)


@app.get("/analyses/metiers-similaires/{metier_id}", tags=["Analyses"])
def metiers_similaires(metier_id: IdMetier, limite: Annotated[int, Query(ge=1, le=14)] = 5):
    return recommender.metiers_similaires(metier_id, limite)


@app.get("/analyses/integrite", tags=["Analyses"])
def integrite():
    """Vérifie l'absence de cycle dans les prérequis."""
    return recommender.detecter_cycles()
