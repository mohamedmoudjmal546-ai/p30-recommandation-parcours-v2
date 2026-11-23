# Présentation de soutenance — Projet P30
*10 diapositives · 8 à 10 minutes · démonstration en direct à la diapositive 7*

Chaque diapositive : contenu à afficher, puis **notes orales** (à ne pas projeter).

---

## Diapositive 1 — Titre

# Recommandation de parcours de formation par compétences
### Un graphe de connaissances Neo4j

- Module : Bases de données NoSQL
- [Nom Prénom] (+ [binôme]) — [date]
- Neo4j · Cypher · FastAPI · Streamlit

**Notes** : Présenter le sujet en une phrase : « Quelles formations suivre, dans quel ordre, pour viser un métier à partir de ce que je sais déjà ? »

---

## Diapositive 2 — Problématique et objectifs

**Problème** : étudiants et jeunes diplômés peinent à relier un *métier* aux *compétences* exigées, puis aux *formations* qui les développent.

**Objectifs**
- Modéliser métiers, compétences, formations et parcours dans un graphe
- Détecter les compétences manquantes et leurs **prérequis cachés**
- Recommander un **parcours ordonné** de formations
- Fournir une application utilisable (API + interface)

**Notes** : Insister sur l'exemple : pour faire du Deep Learning il faut Machine Learning, donc Pandas, donc Python. Ce sont des chemins dans un réseau.

---

## Diapositive 3 — Pourquoi Neo4j ?

| Besoin | En SQL | En Neo4j |
|---|---|---|
| Prérequis transitifs | `WITH RECURSIVE`, jointures multiples | `PREREQUIS*1..4` |
| Lien métier ↔ formation | chaîne de jointures | `shortestPath` |
| Ajouter un type de relation | migration de schéma | aucune migration |

- Les **relations sont la donnée**
- Profondeur de prérequis inconnue à l'avance
- Fonctionnalités natives : chemins variables, plus court chemin, contraintes

**Notes** : Reconnaître que sur 100 nœuds le relationnel marcherait aussi ; l'intérêt apparaît quand le référentiel grandit et que les relations se multiplient.

---

## Diapositive 4 — Architecture technique

```
CSV ─► init_neo4j.py ─► Neo4j 5 (Docker) ◄─ Cypher ◄─ FastAPI ◄─ Streamlit
      validation+MERGE                     moteur de reco   REST     interface
```

- **Aucun secret dans le code** : `.env` (ignoré par Git)
- Écritures protégées par `X-API-Key`
- Validation Pydantic · erreurs centralisées (409 / 503 / 500)
- Requêtes Cypher paramétrées

**Notes** : Le frontend ne parle jamais à Neo4j directement. La logique de planification est isolée dans un module sans base de données, donc testable.

---

## Diapositive 5 — Modèle de données

```
(Metier)-[:REQUIERT {importance 1..5}]->(Competence)
(Formation)-[:DEVELOPPE {niveau_acquis 1..3}]->(Competence)
(Competence)-[:PREREQUIS]->(Competence)
(Parcours)-[:MENE_A]->(Metier)
(Parcours)-[:INCLUT {ordre}]->(Formation)
```

**15** métiers · **50** compétences · **30** formations · **5** parcours
**138** REQUIERT · **58** DEVELOPPE · **51** PREREQUIS → 100 nœuds, 288 relations

- La **compétence est le pivot** ; importance et niveau sont des propriétés de *relation*
- Graphe de prérequis **acyclique**, contrôlé à 3 niveaux

**Notes** : Expliquer le sens de PREREQUIS (A → B : A exige B). Signaler que INCLUT a été ajoutée pour ordonner les parcours prédéfinis.

---

## Diapositive 6 — Requêtes Cypher clés

**Q1 — parcours `*1..4`**
```cypher
MATCH p = (c:Competence {id:'C15'})-[:PREREQUIS*1..4]->(pre)
RETURN pre.nom, min(length(p)) AS distance
```
→ Machine Learning (1), Pandas (2), Statistiques (2), Python (3), Mathématiques (3)

**Q2 — `shortestPath`**
```cypher
MATCH p = shortestPath((m:Metier {id:'M02'})
          -[:REQUIERT|PREREQUIS|DEVELOPPE*..6]-(f:Formation {id:'F20'}))
```
→ Data Scientist → SQL ← Modélisation ← Neo4j ← Formation Neo4j (longueur 4)

**Q4, Q5 — agrégations** : score `Σ importance × niveau acquis`, couverture pondérée par métier

**Notes** : 10 requêtes au total (Q1 à Q10), 5 obligatoires plus bonus : compétences pivot, métiers proches (Jaccard), détection de cycles, parcours prédéfinis.

---

## Diapositive 7 — Algorithme de recommandation et démonstration

1. Acquis + leurs prérequis (fermeture transitive)
2. Écarts et **couverture pondérée**
3. Besoins = cibles + prérequis manquants (`*0..4`)
4. **Sélection gloutonne** : meilleur gain par heure
5. **Tri topologique** : les prérequis d'abord

**Démo en direct** : Data Scientist avec acquis Python, SQL, Linux, Git
- Couverture **21,1 %** · 8 compétences manquantes
- Parcours : Maths-Stats → Pandas/Visualisation → ML → Spark → Deep Learning/NLP (**245 h**)

**Notes** : Ordre de démo : Neo4j Browser (graphe + Q1/Q2), puis Streamlit (Recommandation, Explorer le graphe, Gestion). Avoir les captures prêtes en secours, mais la démo réelle est exigée.

---

## Diapositive 8 — Fonctionnalités de l'application

- **Recommandation** : métrique, parcours en étapes, graphe du métier
- **Explorer** : prérequis (curseur 1–4), plus court chemin, parcours prédéfinis
- **Analyses** : compétences pivot, couverture de 15 métiers, métiers proches
- **Gestion** : CRUD des entités et des relations, refus des cycles
- **API REST** documentée (`/docs`)

[Capture : page Recommandation] · [Capture : chemin M02 → F20]

**Notes** : Montrer un refus : ajouter Python comme prérequis de Deep Learning renvoie 409 (cycle).

---

## Diapositive 9 — Tests et résultats

- **48 tests pytest** : données, validation, planification
- Les **15 métiers** produisent un parcours complet, prérequis toujours avant leur dépendant
- Robustesse : 422 (donnée invalide), 401 (clé absente), 409 (doublon, cycle, suppression protégée), 503 (Neo4j arrêté)
- Couverture avec les mêmes acquis : Data Engineer 32,5 %, Backend 32,4 %… Architecte 0 %

**Notes** : Citer un scénario de test joué en direct. Ajouter les sorties réelles de Neo4j Browser une fois exécutées.

---

## Diapositive 10 — Limites, perspectives et conclusion

**Limites** : données fictives et petites · sélection gloutonne non optimale · maîtrise binaire (acquis ou non) · clé d'API unique

**Perspectives** : niveaux de compétence · sources ouvertes de compétences · budget et modalité · bibliothèque Graph Data Science · comptes utilisateurs

**Conclusion** : un graphe Neo4j transforme « je veux devenir Data Scientist » en un parcours ordonné et justifié, avec `*1..4` et `shortestPath` au cœur du moteur.

**Notes** : Mentionner l'usage d'outils d'IA générative (exigé par les consignes) et être prêt à expliquer n'importe quelle requête ou fonction. Terminer par « Questions ? ».
