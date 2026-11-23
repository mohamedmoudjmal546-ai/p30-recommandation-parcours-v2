"""Configuration lue exclusivement dans l'environnement (fichier .env).

Aucun mot de passe ni clé n'est écrit dans le code source.
"""
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


@dataclass(frozen=True)
class Settings:
    neo4j_uri: str
    neo4j_user: str
    neo4j_password: str
    neo4j_database: str
    api_key: str
    cors_origins: list[str]


def origines_cors() -> list[str]:
    brut = os.getenv("CORS_ORIGINS", "http://localhost:8501")
    return [o.strip() for o in brut.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    password = os.getenv("NEO4J_PASSWORD")
    if not password:
        raise RuntimeError(
            "NEO4J_PASSWORD est absent : copiez .env.example en .env et renseignez-le."
        )
    origines = origines_cors()
    return Settings(
        neo4j_uri=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        neo4j_user=os.getenv("NEO4J_USER", "neo4j"),
        neo4j_password=password,
        neo4j_database=os.getenv("NEO4J_DATABASE", "neo4j"),
        api_key=os.getenv("API_KEY", ""),
        cors_origins=origines,
    )
