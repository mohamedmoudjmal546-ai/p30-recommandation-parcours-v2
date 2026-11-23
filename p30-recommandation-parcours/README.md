# P30 - Recommandation de parcours de formation par compétences

Projet du module **Bases de données NoSQL** (technologie imposée : **Neo4j**).
Un graphe de connaissances relie **15 métiers**, **50 compétences**, **30 formations** et **5 parcours**
pour répondre à la question : *« quelles formations suivre, dans quel ordre, pour atteindre un métier cible
à partir de mes compétences actuelles ? »*

Les données sont **fictives** (aucune donnée personnelle ; organismes de formation inventés).

## Architecture

```
data/*.csv ──► init_neo4j.py ──► Neo4j (nœuds + relations) ◄── requêtes Cypher ◄── FastAPI ◄── Streamlit
(référentiel)  (validation+MERGE)    docker-compose            moteur de reco       backend     frontend
```

### Modèle de graphe

```
(Metier)-[:REQUIERT {importance 1..5}]->(Competence)<-[:DEVELOPPE {niveau_acquis 1..3}]-(Formation)
(Competence)-[:PREREQUIS]->(Competence)        # A -> B : "A exige B au préalable" (graphe acyclique)
(Parcours)-[:MENE_A]->(Metier)
(Parcours)-[:INCLUT {ordre}]->(Formation)      # composition ordonnée d'un parcours
```

| Nœud | Propriétés |
|---|---|
| `Metier` | id, nom, secteur, description |
| `Competence` | id, nom, categorie, description |
| `Formation` | id, nom, organisme, duree_heures, niveau, modalite, description |
| `Parcours` | id, nom, description, duree_mois |

## Arborescence

```
docker-compose.yml        Neo4j 5 (mot de passe lu dans .env)
.env.example              modèle de configuration (copier en .env)
requirements.txt
init_neo4j.py             validation des CSV + schéma + chargement idempotent
data/                     metiers, competences, formations, parcours (nœuds)
                          requiert, developpe, prerequis, mene_a, parcours_formations (relations)
cypher/00_load_csv.cypher chargement alternatif (LOAD CSV) depuis Neo4j Browser
cypher/01_schema.cypher   contraintes d'unicité et index
cypher/02_requetes_5_obligatoires.cypher   Q1..Q10 (dont *1..4 et shortestPath)
backend/                  API FastAPI (main, models, crud, recommender, planification, database, config)
frontend/app.py           interface Streamlit
tests/                    pytest (données, validation Pydantic, planification)
```

## Installation et exécution

Prérequis : Docker, Python 3.10+.

```bash
# 1. Configuration (aucun secret n'est versionné)
cp .env.example .env
#    éditer .env : NEO4J_PASSWORD (8 caractères min.) et API_KEY
#    clé aléatoire :  python -c "import secrets; print(secrets.token_urlsafe(32))"

# 2. Environnement Python
python -m venv .venv
source .venv/bin/activate          # Windows PowerShell : .venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 3. Base Neo4j
docker compose up -d               # Neo4j Browser : http://localhost:7474
python init_neo4j.py               # ajouter --reset pour repartir d'une base vide

# 4. Backend (terminal 1)
uvicorn backend.main:app --reload --port 8000     # docs : http://localhost:8000/docs

# 5. Frontend (terminal 2)
streamlit run frontend/app.py                     # http://localhost:8501
```

Tests (sans Neo4j) : `pytest -q`. Validation seule des CSV : `python init_neo4j.py --valider-seulement`.

## Requêtes Cypher (cypher/02_requetes_5_obligatoires.cypher)

| # | Objectif | Technique |
|---|---|---|
| Q1 | Prérequis transitifs d'une compétence | **parcours `PREREQUIS*1..4`** |
| Q2 | Plus court chemin entre deux nœuds | **`shortestPath`** |
| Q3 | Compétences manquantes d'un métier | filtre `NOT IN`, tri par importance |
| Q4 | Formations les plus utiles (score = importance × niveau acquis) | agrégation `collect`, `sum`, `count` |
| Q5 | Couverture pondérée de chaque métier | agrégation conditionnelle `CASE` |
| Q6 | Ordre d'apprentissage (fondations d'abord) | `PREREQUIS*0..4` + `max(length(p))` |
| Q7 | Compétences pivot (demandées par le plus de métiers) | agrégation + `OPTIONAL MATCH` |
| Q8 | Métiers proches (indice de Jaccard) | motif partagé + agrégation |
| Q9 | Contrôle d'intégrité : aucun cycle de prérequis | `(c)-[:PREREQUIS*1..10]->(c)` |
| Q10 | Les 5 parcours prédéfinis | `collect` ordonné |

Le moteur (`backend/recommender.py`) exécute ces mêmes requêtes en version paramétrée, puis
`backend/planification.py` choisit les formations (couverture gloutonne : points par heure) et les
ordonne par tri topologique sur les prérequis.

## API REST (extraits)

| Méthode | Route | Rôle |
|---|---|---|
| GET/POST | `/metiers`, `/competences`, `/formations` | lister (filtres `q`, pagination) / créer |
| GET/PUT/DELETE | `/metiers/{id}` … | lire / modifier / supprimer (`force=true` pour détacher) |
| PUT/DELETE | `/metiers/{id}/competences/{cid}` | relation REQUIERT |
| PUT/DELETE | `/formations/{id}/competences/{cid}` | relation DEVELOPPE |
| PUT/DELETE | `/competences/{id}/prerequis/{pid}` | relation PREREQUIS (cycles refusés) |
| GET | `/competences/{id}/prerequis?profondeur=4` | Q1 |
| GET | `/chemin?source=M02&cible=F20` | Q2 |
| POST | `/recommandation` | Q3 + Q4 + Q6 + parcours ordonné |
| POST | `/analyses/couverture` | Q5 |
| GET | `/analyses/competences-pivot`, `/analyses/metiers-similaires/{id}`, `/analyses/integrite` | Q7, Q8, Q9 |
| GET | `/parcours`, `/graphe/metier/{id}`, `/stats`, `/health` | Q10 et utilitaires |

Les écritures exigent l'en-tête `X-API-Key` (valeur de `API_KEY`). Exemple :

```bash
curl -X POST http://localhost:8000/recommandation -H "Content-Type: application/json" \
     -d '{"metier_id": "M02", "competences_acquises": ["C01","C02","C05","C06"], "max_formations": 8}'

curl -X POST http://localhost:8000/competences -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" \
     -d '{"nom": "Rust", "categorie": "Programmation", "description": "Langage système sûr"}'
```

## Sécurité et qualité

- Aucun secret dans le code : Neo4j et clé d'API viennent de `.env` (ignoré par Git).
- Validation Pydantic : types, bornes, énumérations, champs inconnus refusés, `<` `>` et caractères de contrôle interdits.
- Requêtes Cypher **toujours paramétrées** (seule la borne de profondeur, entier 1..4 validé, est insérée dans le texte).
- Contraintes d'unicité (id et nom), refus des cycles de prérequis, suppression protégée (409 sans `force`).
- Erreurs Neo4j converties en 409 / 503 / 500 sans fuite de détails internes.

## Scénario de démonstration

1. `docker compose up -d` puis `python init_neo4j.py` : 15 métiers, 50 compétences, 30 formations, 5 parcours.
2. Neo4j Browser : `MATCH (n) RETURN n LIMIT 100`, puis Q1 et Q2.
3. Streamlit → **Recommandation** : métier *Data Scientist*, acquis *Python, SQL, Linux, Git* → couverture, lacunes, parcours ordonné (Mathématiques → Analyse → ML → Deep Learning → Spark).
4. **Explorer le graphe** : prérequis de *Deep Learning* (`*1..4`) et plus court chemin `M02` → `F20`.
5. **Gestion** : créer une compétence, la lier à un métier, tenter un prérequis créant un cycle (refusé).

## Transparence sur l'IA

Conformément aux consignes pédagogiques, l'usage d'outils d'IA générative pour produire ce code doit être
signalé dans le rapport, et chaque partie doit pouvoir être expliquée en soutenance.
