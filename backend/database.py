"""Accès à Neo4j : un driver partagé et deux helpers (lecture / écriture).

Toutes les requêtes sont paramétrées ($param) : aucune valeur utilisateur
n'est concaténée dans le Cypher (protection contre l'injection Cypher).
"""
from neo4j import READ_ACCESS, WRITE_ACCESS, Driver, GraphDatabase

from config import get_settings

_driver: Driver | None = None


def get_driver() -> Driver:
    global _driver
    if _driver is None:
        s = get_settings()
        _driver = GraphDatabase.driver(s.neo4j_uri, auth=(s.neo4j_user, s.neo4j_password))
    return _driver


def verifier_connexion() -> None:
    get_driver().verify_connectivity()


def fermer_driver() -> None:
    global _driver
    if _driver is not None:
        _driver.close()
        _driver = None


def lire(requete: str, **params) -> list[dict]:
    """Exécute une requête en lecture (transaction managée, avec nouvelles tentatives)."""
    with get_driver().session(database=get_settings().neo4j_database, default_access_mode=READ_ACCESS) as session:
        return session.execute_read(lambda tx: [r.data() for r in tx.run(requete, params)])


def ecrire(requete: str, **params) -> list[dict]:
    """Exécute une requête en écriture (transaction managée)."""
    with get_driver().session(database=get_settings().neo4j_database, default_access_mode=WRITE_ACCESS) as session:
        return session.execute_write(lambda tx: [r.data() for r in tx.run(requete, params)])
