# Rapport technique — Projet P30
## Conception d'un système de recommandation de parcours de formation par compétences

**Module** : Bases de données NoSQL — **Technologie imposée** : Neo4j
**Auteur(s)** : [Nom Prénom] (et [Nom Prénom du binôme, avec sa contribution])
**Date** : [à compléter] — **Dépôt Git** : [lien GitHub/GitLab]

> **Notes de finalisation (à supprimer avant remise).**
> Les passages `[Capture : …]` sont à remplacer par vos captures d'écran réelles.
> Les valeurs de la section 9 ont été recalculées en Python à partir des CSV, avec la même logique que les requêtes Cypher ;
> remplacez-les par les sorties réelles de Neo4j Browser une fois la base chargée et vérifiez qu'elles concordent.
> Mentionnez en section 10 l'usage d'outils d'IA générative (exigé par les consignes) et soyez prêt à expliquer chaque requête.

---

## 1. Introduction et contexte professionnel

Le marché de l'emploi numérique exprime ses besoins en **compétences** (Python, SQL, Docker, machine learning…), alors que l'offre de formation est présentée sous forme de **cursus et de modules**. Un étudiant ou un jeune diplômé doit donc traduire lui-même un métier visé en liste de compétences, puis retrouver les formations qui les développent, en respectant l'ordre logique d'acquisition (on n'aborde pas le deep learning avant la statistique ni Python).

Ce projet construit un **graphe de connaissances** qui relie métiers, compétences, formations et parcours, et un **moteur de recommandation** qui, à partir des compétences déjà acquises d'un utilisateur et d'un métier cible, produit un parcours de formation ordonné. La solution comprend une base Neo4j, une API REST FastAPI et une interface Streamlit.

Les données sont **fictives** (référentiel de 15 métiers, 50 compétences, 30 formations, 5 parcours ; organismes de formation inventés). Aucune donnée personnelle n'est utilisée, conformément aux consignes.

## 2. Présentation de la problématique

> *Les étudiants et jeunes diplômés rencontrent des difficultés pour identifier les formations correspondant aux compétences nécessaires à un métier.*

La question se décompose en quatre sous-problèmes :

1. **Traduire** un métier en compétences, avec un niveau d'importance.
2. **Identifier les écarts** entre ce que l'étudiant maîtrise et ce que le métier exige.
3. **Retrouver les prérequis cachés** : une compétence manquante en suppose souvent d'autres (Deep Learning → Machine Learning → Pandas → Python).
4. **Choisir et ordonner** un nombre limité de formations qui comblent l'écart au meilleur coût en heures.

Ces sous-problèmes sont tous des questions de **cheminement dans un réseau de relations**, ce qui oriente naturellement vers une base orientée graphe.

## 3. Analyse des besoins fonctionnels

| Réf. | Besoin | Réalisation |
|---|---|---|
| F1 | Consulter métiers, compétences, formations | `GET /metiers`, `/competences`, `/formations` (filtres, recherche, pagination) |
| F2 | Créer, modifier, supprimer ces éléments | CRUD complet, suppression protégée (409 sans `force=true`) |
| F3 | Gérer les relations `REQUIERT`, `DEVELOPPE`, `PREREQUIS` | routes `PUT/DELETE` dédiées, refus des cycles de prérequis |
| F4 | Identifier les compétences manquantes pour un métier | Q3, `POST /recommandation` |
| F5 | Retrouver les prérequis transitifs d'une compétence | Q1, `GET /competences/{id}/prerequis?profondeur=1..4` |
| F6 | Trouver le lien le plus court entre deux éléments | Q2, `GET /chemin` |
| F7 | Recommander et ordonner des formations | Q4, Q6 + algorithme de planification |
| F8 | Comparer l'étudiant à tous les métiers | Q5, `POST /analyses/couverture` |
| F9 | Proposer des parcours personnalisés prédéfinis | 5 parcours (Q10) |
| F10 | Visualiser le graphe | sous-graphe d'un métier (Graphviz dans Streamlit) |

**Exigences non fonctionnelles** : validation des entrées, gestion des erreurs, aucun secret dans le code (`.env`), démarrage reproductible (Docker + script d'initialisation), code organisé et testé.

## 4. Justification du choix de la technologie NoSQL

Neo4j est imposé par la fiche du projet, mais il est aussi le choix pertinent pour les données traitées :

- **Les relations sont la donnée.** Les questions posées (prérequis transitifs, plus court chemin, compétences communes entre métiers) sont des parcours de graphe. En SQL, elles exigent des jointures récursives (`WITH RECURSIVE`) lourdes à écrire et à maintenir ; en Cypher, `PREREQUIS*1..4` suffit.
- **Profondeur variable.** Le nombre de niveaux de prérequis n'est pas connu à l'avance ; le graphe s'interroge sans modifier le schéma.
- **Schéma souple.** Ajouter un type de relation (par exemple `INCLUT`, introduit en cours de conception pour ordonner les parcours) ne nécessite aucune migration.
- **Fonctionnalités natives** : `shortestPath`, chemins de longueur variable, contraintes d'unicité, index.

*Limites assumées* : sur un petit référentiel (100 nœuds), la base relationnelle serait aussi viable ; l'avantage de Neo4j est de rester lisible et performant quand le référentiel grandit (milliers de compétences, relations multiples).

## 5. Architecture technique de la solution

```
data/*.csv ─► init_neo4j.py ─► Neo4j 5 ◄─ requêtes Cypher ◄─ FastAPI ◄─ Streamlit
(référentiel)  validation+MERGE  (Docker)   (moteur de reco)   (REST)    (interface)
```

| Couche | Technologie | Rôle |
|---|---|---|
| Base | Neo4j 5.26 Community (Docker) | graphe, contraintes, index |
| Initialisation | `init_neo4j.py` | valide les CSV, applique `01_schema.cypher`, charge via `UNWIND … MERGE` (idempotent) |
| Backend | FastAPI, driver `neo4j` | API REST, validation Pydantic, moteur de recommandation |
| Frontend | Streamlit, Graphviz | interface ; ne dialogue qu'avec l'API |
| Configuration | `.env` (python-dotenv) | identifiants Neo4j, clé d'API (jamais versionnés) |

**Organisation du backend** : `models.py` (validation), `crud.py` (CRUD générique et relations), `recommender.py` (requêtes du moteur), `planification.py` (logique pure testable sans base), `database.py` (driver partagé), `config.py` (environnement), `main.py` (routes et gestion d'erreurs).

**Installation et exécution** (Docker et Python 3.10+) :

```bash
cp .env.example .env            # renseigner NEO4J_PASSWORD et API_KEY
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
docker compose up -d            # Neo4j Browser : http://localhost:7474
python init_neo4j.py            # --reset pour repartir d'une base vide
uvicorn backend.main:app --port 8000     # documentation : http://localhost:8000/docs
streamlit run frontend/app.py            # http://localhost:8501
```

**Sécurité** : mot de passe et clé d'API lus dans `.env` ; écritures protégées par l'en-tête `X-API-Key` (comparaison à temps constant) ; requêtes Cypher paramétrées (seule la borne de profondeur, entier validé entre 1 et 4, est insérée dans le texte car Neo4j n'accepte pas de paramètre à cet endroit) ; erreurs Neo4j traduites en 409, 503 ou 500 sans fuite d'information interne.

## 6. Conception et modélisation de la base de données

### 6.1 Modèle de graphe

```
(Metier)-[:REQUIERT {importance 1..5}]->(Competence)<-[:DEVELOPPE {niveau_acquis 1..3}]-(Formation)
(Competence)-[:PREREQUIS]->(Competence)       A -> B : « A exige B au préalable »
(Parcours)-[:MENE_A]->(Metier)
(Parcours)-[:INCLUT {ordre}]->(Formation)
```

| Nœud | Propriétés |
|---|---|
| `Metier` | id, nom, secteur, description |
| `Competence` | id, nom, categorie, description |
| `Formation` | id, nom, organisme, duree_heures, niveau, modalite, description |
| `Parcours` | id, nom, description, duree_mois |

### 6.2 Choix de modélisation justifiés

- **Les compétences sont le pivot** : métiers et formations ne sont jamais reliés directement. Le lien métier ↔ formation se déduit par la compétence, ce qui évite la redondance et permet de comparer formations et métiers sur une même échelle.
- **Propriétés sur les relations** : l'`importance` d'une compétence dépend du métier, le `niveau_acquis` dépend de la formation. Ce ne sont des propriétés ni du métier, ni de la compétence, ni de la formation : elles appartiennent à la relation.
- **Sens de `PREREQUIS`** : `(A)-[:PREREQUIS]->(B)` se lit « A a pour prérequis B ». Le graphe doit rester **acyclique** ; ce contrôle est fait au chargement (tri topologique de Kahn), à chaque ajout via l'API (`EXISTS { (b)-[:PREREQUIS*1..20]->(a) }`) et par la requête Q9.
- **`INCLUT {ordre}`** : relation ajoutée au-delà des quatre relations de la fiche, pour représenter la composition ordonnée d'un parcours prédéfini ; `MENE_A` relie le parcours à son métier cible.
- **Contraintes** : unicité de `id` et de `nom` pour chaque label (les contraintes d'existence sont réservées à l'édition Enterprise ; la présence des propriétés est donc validée par Pydantic et par le script d'initialisation) ; index sur `Competence.categorie`, `Formation.niveau`, `Metier.secteur`.

### 6.3 Jeu de données

| Élément | Volume | Fichier |
|---|---|---|
| Métiers | 15 (Data Analyst, Data Scientist, Data Engineer, DevOps, Ingénieur Cloud, Dév. Backend/Frontend/Full Stack, Ingénieur ML, DBA, Architecte, Cybersécurité, Chef de projet IT, Analyste BI, Ingénieur QA) | `metiers.csv` |
| Compétences | 50, réparties en 14 catégories (Programmation, Data, IA, Bases de données, DevOps, Cloud, Web, Sécurité…) | `competences.csv` |
| Formations | 30 (de 25 à 60 heures, trois niveaux, trois modalités) | `formations.csv` |
| Parcours | 5 (Data Analyst, Data Scientist, DevOps, Full Stack, Cybersécurité) | `parcours.csv` |
| `REQUIERT` | 138 relations | `requiert.csv` |
| `DEVELOPPE` | 58 relations | `developpe.csv` |
| `PREREQUIS` | 51 relations (graphe acyclique, profondeur maximale 3) | `prerequis.csv` |
| `MENE_A` / `INCLUT` | 5 / 36 relations | `mene_a.csv`, `parcours_formations.csv` |

Le graphe compte **100 nœuds et 288 relations**. Le script d'initialisation refuse de charger des données incohérentes (volumes minimaux, identifiants dupliqués, références inconnues, bornes, cycle, compétence sans formation, numéros d'ordre de parcours non contigus).

## 7. Principales requêtes Cypher et algorithme de recommandation

Les requêtes complètes et commentées figurent dans `cypher/02_requetes_5_obligatoires.cypher` ; l'API exécute les mêmes requêtes en version paramétrée. Dans les exemples, `acquises = ['C01','C02','C05','C06']` (Python, SQL, Linux, Git).

### 7.1 Q1 — Parcours de graphe `*1..4` (fonctionnalité Neo4j n°1)

Toutes les compétences à maîtriser avant le Deep Learning, de façon transitive.

```cypher
MATCH p = (c:Competence {id: 'C15'})-[:PREREQUIS*1..4]->(pre:Competence)
WITH pre, min(length(p)) AS distance
RETURN pre.id AS id, pre.nom AS prerequis, distance
ORDER BY distance, prerequis;
```
Résultat attendu : Machine Learning (1), Pandas (2), Statistiques (2), Python (3), Mathématiques (3). `min(length(p))` retient le chemin le plus court quand une compétence est atteignable de plusieurs façons.

### 7.2 Q2 — `shortestPath` (fonctionnalité Neo4j n°2)

```cypher
MATCH (m:Metier {id: 'M02'}), (f:Formation {id: 'F20'})
MATCH p = shortestPath((m)-[:REQUIERT|PREREQUIS|DEVELOPPE*..6]-(f))
RETURN [n IN nodes(p) | coalesce(n.nom, n.id)] AS noeuds,
       [r IN relationships(p) | type(r)] AS relations, length(p) AS longueur;
```
Résultat attendu (longueur 4) : *Data Scientist* —REQUIERT→ *SQL* ←PREREQUIS— *Modélisation de données* ←PREREQUIS— *Neo4j et Cypher* ←DEVELOPPE— *formation Neo4j*. Le chemin explique **pourquoi** une formation est utile à un métier. Une seconde variante cherche la chaîne de prérequis la plus courte entre Microservices et Algorithmique (longueur 3).

### 7.3 Q3 — Compétences manquantes (filtre et tri)

```cypher
WITH ['C01','C02','C05','C06'] AS acquises
MATCH (m:Metier {id: 'M02'})-[r:REQUIERT]->(c:Competence)
WHERE NOT c.id IN acquises
RETURN c.nom AS competence_manquante, r.importance AS importance
ORDER BY importance DESC;
```

### 7.4 Q4 — Score des formations (agrégation)

```cypher
MATCH (m:Metier {id: 'M02'})-[r:REQUIERT]->(c:Competence)
WHERE NOT c.id IN acquises
MATCH (f:Formation)-[d:DEVELOPPE]->(c)
WITH f, collect(c.nom) AS competences_couvertes, count(c) AS nb,
     sum(r.importance * d.niveau_acquis) AS score
RETURN f.nom, nb, competences_couvertes, score,
       round(1.0 * score / f.duree_heures * 10, 2) AS efficacite_pour_10h
ORDER BY score DESC;
```
Le score d'une formation est la somme, sur les compétences manquantes qu'elle développe, de *importance du métier × niveau acquis en formation*.

### 7.5 Q5 — Couverture pondérée par métier (agrégation conditionnelle)

```cypher
MATCH (m:Metier)-[r:REQUIERT]->(c:Competence)
WITH m, count(c) AS nb_requises, sum(r.importance) AS poids_total,
     sum(CASE WHEN c.id IN acquises THEN r.importance ELSE 0 END) AS poids_acquis
RETURN m.nom, round(100.0 * poids_acquis / poids_total, 1) AS couverture_pct
ORDER BY couverture_pct DESC;
```

### 7.6 Requêtes complémentaires

- **Q6** : ordre d'apprentissage. `PREREQUIS*0..4` (0 = la compétence elle-même) remonte les prérequis non acquis ; `max(length(p))` mesure la profondeur de chaque compétence : plus elle est grande, plus la compétence est une fondation.
- **Q7** : compétences pivot (demandées par le plus de métiers). **Q8** : métiers proches par indice de Jaccard. **Q9** : détection de cycles. **Q10** : parcours prédéfinis avec leurs formations ordonnées.

### 7.7 Algorithme de recommandation

Le moteur (`recommender.py` + `planification.py`) enchaîne :

1. **Fermeture des acquis** : les prérequis des compétences déclarées sont considérés acquis (qui sait faire du Machine Learning sait Python).
2. **Écarts directs** (Q3) et **couverture pondérée** = 100 × (1 − poids manquant / poids total).
3. **Besoins** (Q6) : compétences cibles non acquises *et* leurs prérequis manquants, avec profondeur et poids (importance maximale du métier qui en dépend).
4. **Classement** des formations (Q4) pour affichage.
5. **Sélection gloutonne** : à chaque tour, on retient la formation qui maximise `gain / durée`, avec `gain = Σ poids × niveau acquis` sur les besoins encore non couverts ; on s'arrête quand tout est couvert ou que la limite de formations est atteinte.
6. **Ordonnancement** : tri topologique des formations choisies (une formation qui apporte un prérequis précède celle qui en dépend) ; à égalité, les fondations (profondeur élevée) passent d'abord, puis les formations les plus courtes. Si un cycle apparaît entre formations (cas rare), le tri retombe sur la profondeur.

La sélection gloutonne est une heuristique : elle ne garantit pas le nombre minimal d'heures (problème de couverture d'ensemble, NP-difficile en général) mais donne un résultat explicable et rapide.

## 8. Fonctionnalités développées et captures d'écran

| Page Streamlit | Fonctionnalités | Capture |
|---|---|---|
| **Recommandation** | choix du métier et des acquis ; indicateurs (couverture, lacunes, nombre de formations, durée) ; parcours en étapes avec graphe ; compétences manquantes et prérequis indirects ; formations classées ; graphe du métier | [Capture : page Recommandation, scénario Data Scientist] |
| **Explorer le graphe** | prérequis `*1..4` avec curseur de profondeur ; plus court chemin entre deux nœuds ; graphe d'un métier ; 5 parcours prédéfinis | [Capture : chemin M02 → F20] |
| **Analyses** | compétences pivot, couverture de tous les métiers, métiers proches, contrôle d'intégrité et statistiques | [Capture : couverture par métier] |
| **Gestion des données** | CRUD des trois entités, gestion des relations `REQUIERT`, `DEVELOPPE`, `PREREQUIS` | [Capture : création d'une compétence ; refus d'un cycle] |
| **API** (`/docs`) | documentation OpenAPI interactive | [Capture : Swagger] |
| **Neo4j Browser** | graphe complet, Q1 et Q2 | [Capture : `MATCH (n) RETURN n LIMIT 100`, résultat de Q2] |

## 9. Tests, validation et résultats obtenus

### 9.1 Tests automatisés (`pytest`, sans Neo4j) — 48 tests

- **Données** : volumes (15/50/30/5), validité du référentiel, absence de cycle, détection d'une référence inconnue, d'une importance hors bornes et d'un cycle injecté ; vérification indépendante des résultats annoncés pour Q1, Q2 (variantes a et b).
- **Validation** (`test_models.py`) : durée hors bornes, niveau ou modalité inconnus, balises `<script>` et caractères de contrôle, champs inconnus, nettoyage des espaces, déduplication des acquis.
- **Planification** (`test_planification.py`) : pour **chacun des 15 métiers** partant sans acquis, toutes les compétences sont couvertes et aucun prérequis n'est placé après la compétence qui en dépend ; respect de la limite de formations ; cas d'un métier déjà couvert.

### 9.2 Scénario de test fonctionnel : étudiant visant *Data Scientist*

Acquis : Python, SQL, Linux, Git. Résultats recalculés à partir des CSV avec la logique des requêtes ; à confirmer par vos captures Neo4j.

- **Couverture du métier : 21,1 %** (8 points d'importance acquis sur 38 ; 30 points manquants).
- **Compétences manquantes (8)** : Statistiques (5), Pandas (5), Machine Learning (5), Mathématiques (4), Visualisation de données (4), Deep Learning (3), NLP (2), Big Data avec Spark (2).
- **Formations classées (Q4)** : Analyse et visualisation de données (score 27, 6,75 pts/10 h), Mathématiques et statistiques (27, 5,4), Machine Learning (15, 3,0), Deep Learning et NLP (15, 2,5), Big Data avec Spark (6, 1,33).
- **Parcours proposé (245 h, aucune compétence non couverte)** :

| Étape | Formation | Durée | Compétences visées |
|---|---|---|---|
| 1 | Mathématiques et statistiques pour la data | 50 h | Mathématiques, Statistiques |
| 2 | Analyse et visualisation de données | 40 h | Pandas, Visualisation |
| 3 | Machine Learning avec scikit-learn | 50 h | Machine Learning |
| 4 | Big Data avec Spark | 45 h | Big Data avec Spark |
| 5 | Deep Learning et NLP | 60 h | Deep Learning, NLP |

La formation Mathématiques arrive en premier car *Mathématiques* est la compétence la plus profonde (profondeur 3 : Deep Learning → ML → Statistiques → Mathématiques). Machine Learning précède Deep Learning, conformément à `PREREQUIS`.

- **Couverture des autres métiers avec les mêmes acquis (Q5)** : Data Engineer 32,5 %, Développeur Backend 32,4 %, DBA 28,1 %, DevOps 27,5 %, Data Analyst 26,5 % … Architecte Logiciel et Chef de projet IT 0 %. Les métiers les plus accessibles sont donc ceux de l'écosystème data et backend, ce qui est cohérent avec les acquis déclarés.

### 9.3 Tests de robustesse à réaliser en démonstration

| Test | Résultat attendu |
|---|---|
| Créer une formation avec `duree_heures = 0` | 422, message de validation |
| Écrire sans `X-API-Key` | 401 |
| Créer deux compétences au même nom | 409 |
| Ajouter un prérequis créant un cycle (ex. Python → Deep Learning) | 409 |
| Supprimer un métier relié à des compétences, sans `force` | 409 |
| Arrêter Neo4j puis appeler `/health` | 503, message générique |

## 10. Difficultés rencontrées, limites et perspectives

**Difficultés et solutions**
- *Borne de profondeur non paramétrable* : Neo4j n'accepte pas `*1..$n` ; la borne est validée (entier 1 à 4) puis insérée dans le texte, tout le reste restant paramétré.
- *Éviter les cycles de prérequis* : contrôle triple (chargement, API, requête Q9).
- *Ordonner des formations et non des compétences* : une formation couvre plusieurs compétences de profondeurs différentes ; le tri topologique sur les formations, avec repli sur la profondeur, résout ce cas.
- *Contraintes d'existence indisponibles en Community* : compensées par la validation applicative.

**Limites**
- Données fictives et de petite taille ; importances et niveaux fixés à la main, sans calibrage sur des offres d'emploi réelles.
- La sélection gloutonne est une heuristique, non optimale.
- Le niveau de maîtrise de l'utilisateur est binaire (acquis ou non) ; l'`importance` n'a pas d'échelle de niveau requis.
- Pas de comptes utilisateurs : une seule clé d'API partagée protège les écritures.
- Les requêtes ont été vérifiées sur le jeu actuel ; aucun test de montée en charge.

**Perspectives**
- Niveaux de compétence (débutant à expert) des deux côtés de la relation.
- Alimenter le référentiel depuis des sources ouvertes (par exemple une taxonomie européenne de compétences, sous réserve de licence).
- Prise en compte du budget, de la modalité et du temps disponible dans la sélection.
- Algorithmes de la bibliothèque Graph Data Science (centralité, similarité) pour remplacer les calculs Jaccard et pivot.
- Authentification par utilisateur, historique et suivi de progression.
- Conteneurisation de l'API et du frontend dans le `docker-compose.yml`.

**Usage de l'IA générative.** [À compléter : indiquer les outils utilisés, pour quelles parties (génération initiale du code, données, relecture) et ce que vous avez vérifié, modifié ou compris par vous-même.]

## 11. Conclusion

Le projet répond à la mission de la fiche P30 : un graphe de connaissances Neo4j relie 15 métiers, 50 compétences, 30 formations et 5 parcours, et un moteur de recommandation transforme un objectif professionnel et des acquis en un parcours ordonné, justifié par les prérequis. Les deux fonctionnalités spécifiques demandées sont exploitées : le parcours à profondeur variable (`PREREQUIS*1..4`) pour révéler les prérequis cachés, et `shortestPath` pour expliquer le lien entre un métier et une formation. L'application offre un CRUD validé, une gestion d'erreurs centralisée et aucun secret dans le code.

Le choix du graphe a rendu simples des questions qui auraient exigé des jointures récursives en relationnel, et la séparation entre requêtes Cypher, logique de planification pure et interface a permis de tester l'essentiel sans base. Les principales évolutions à mener concernent la richesse du référentiel (niveaux, sources réelles) et l'optimisation du choix des formations.

---

### Annexe — Contribution des membres *(si binôme)*

| Membre | Contributions |
|---|---|
| [Nom 1] | [ex. modélisation, requêtes Cypher, init_neo4j.py] |
| [Nom 2] | [ex. API FastAPI, interface Streamlit, tests] |
