// =====================================================================
// P30 - 02_requetes_5_obligatoires.cypher
// Requêtes Cypher significatives (non CRUD) du moteur de recommandation.
//
// Exécution : Neo4j Browser (un bloc à la fois) après init_neo4j.py.
// Les paramètres sont remplacés par des valeurs littérales pour pouvoir
// copier/coller directement ; l'API utilise les mêmes requêtes paramétrées.
//
// Scénario de démonstration : un étudiant maîtrise déjà Python (C01),
// SQL (C02), Git (C06) et Linux (C05) et vise "Data Scientist" (M02).
//
//   Q1  Parcours de graphe  *1..4        prérequis transitifs d'une compétence
//   Q2  shortestPath                      plus court chemin entre deux nœuds
//   Q3  Agrégation + filtre NOT IN        compétences manquantes d'un métier
//   Q4  Agrégation pondérée               formations les plus utiles (score)
//   Q5  Agrégation conditionnelle (CASE)  métiers les plus accessibles
//   Q6  *0..4 + agrégation (bonus)        ordre d'apprentissage (fondations d'abord)
//   Q7  Agrégation (bonus)                compétences "pivot" du référentiel
//   Q8  Motif partagé + Jaccard (bonus)   métiers proches
//   Q9  Contrôle d'intégrité (bonus)      détection de cycles PREREQUIS
//   Q10 Lecture des parcours (bonus)      5 parcours prédéfinis
// =====================================================================


// ---------------------------------------------------------------------
// Q1 - PARCOURS DE GRAPHE *1..4 : toutes les compétences à maîtriser
// avant le Deep Learning (C15), de façon transitive, jusqu'à 4 niveaux.
// Fonctionnalité Neo4j n°1 : chemins de longueur variable.
// ---------------------------------------------------------------------
MATCH p = (c:Competence {id: 'C15'})-[:PREREQUIS*1..4]->(pre:Competence)
WITH pre, min(length(p)) AS distance          // distance = niveau de profondeur le plus proche
RETURN pre.id AS id, pre.nom AS prerequis, pre.categorie AS categorie, distance
ORDER BY distance, prerequis;
// Résultat attendu : Machine Learning (1), Pandas (2), Statistiques (2),
//                    Python (3), Mathématiques (3)


// ---------------------------------------------------------------------
// Q2 - shortestPath (a) : chaîne de prérequis la plus courte entre
// Microservices (C50) et Algorithmique (C07).
// Fonctionnalité Neo4j n°2 : algorithme de plus court chemin intégré.
// ---------------------------------------------------------------------
MATCH (a:Competence {id: 'C50'}), (b:Competence {id: 'C07'})
MATCH p = shortestPath((a)-[:PREREQUIS*..6]->(b))
RETURN [n IN nodes(p) | n.nom] AS chaine, length(p) AS longueur;
// Résultat attendu : Microservices -> Architecture logicielle ->
//                    Programmation orientée objet -> Algorithmique (longueur 3)

// Q2 - shortestPath (b) : lien le plus court entre un métier et une formation,
// en traversant REQUIERT, PREREQUIS et DEVELOPPE sans tenir compte du sens.
// "Pourquoi la formation Neo4j (F20) est-elle utile à un Data Scientist (M02) ?"
MATCH (m:Metier {id: 'M02'}), (f:Formation {id: 'F20'})
MATCH p = shortestPath((m)-[:REQUIERT|PREREQUIS|DEVELOPPE*..6]-(f))
RETURN [n IN nodes(p) | coalesce(n.nom, n.id)] AS noeuds,
       [r IN relationships(p) | type(r)] AS relations,
       length(p) AS longueur;
// Résultat attendu : Data Scientist -REQUIERT-> SQL <-PREREQUIS- Modélisation de
//                    données <-PREREQUIS- Neo4j et Cypher <-DEVELOPPE- formation Neo4j


// ---------------------------------------------------------------------
// Q3 - COMPÉTENCES MANQUANTES : ce que l'étudiant doit encore acquérir
// pour devenir Data Scientist (M02), classées par importance.
// ---------------------------------------------------------------------
WITH ['C01', 'C02', 'C05', 'C06'] AS acquises
MATCH (m:Metier {id: 'M02'})-[r:REQUIERT]->(c:Competence)
WHERE NOT c.id IN acquises
RETURN c.id AS id, c.nom AS competence_manquante, c.categorie AS categorie, r.importance AS importance
ORDER BY importance DESC, competence_manquante;


// ---------------------------------------------------------------------
// Q4 - RECOMMANDATION DE FORMATIONS : chaque formation est notée par
//   score = somme( importance de la compétence x niveau acquis en formation )
// sur les compétences encore manquantes ; l'efficacité rapporte ce score
// à la durée (points pour 10 heures).
// ---------------------------------------------------------------------
WITH ['C01', 'C02', 'C05', 'C06'] AS acquises
MATCH (m:Metier {id: 'M02'})-[r:REQUIERT]->(c:Competence)
WHERE NOT c.id IN acquises
MATCH (f:Formation)-[d:DEVELOPPE]->(c)
WITH f, collect(c.nom) AS competences_couvertes, count(c) AS nb_competences,
     sum(r.importance * d.niveau_acquis) AS score
RETURN f.id AS id, f.nom AS formation, f.niveau AS niveau, f.duree_heures AS heures,
       nb_competences, competences_couvertes, score,
       round(1.0 * score / f.duree_heures * 10, 2) AS efficacite_pour_10h
ORDER BY score DESC, heures ASC
LIMIT 10;


// ---------------------------------------------------------------------
// Q5 - MÉTIERS LES PLUS ACCESSIBLES : taux de couverture pondéré par
// l'importance, pour chacun des 15 métiers, selon les acquis de l'étudiant.
// ---------------------------------------------------------------------
WITH ['C01', 'C02', 'C05', 'C06'] AS acquises
MATCH (m:Metier)-[r:REQUIERT]->(c:Competence)
WITH m, count(c) AS nb_requises, sum(r.importance) AS poids_total,
     sum(CASE WHEN c.id IN acquises THEN 1 ELSE 0 END) AS nb_acquises,
     sum(CASE WHEN c.id IN acquises THEN r.importance ELSE 0 END) AS poids_acquis
RETURN m.id AS id, m.nom AS metier, nb_acquises, nb_requises,
       round(100.0 * poids_acquis / poids_total, 1) AS couverture_pct
ORDER BY couverture_pct DESC, metier;


// ---------------------------------------------------------------------
// Q6 (bonus) - ORDRE D'APPRENTISSAGE : pour devenir Data Scientist, on
// remonte jusqu'à 4 niveaux de prérequis (*0..4 : 0 = la compétence elle-même)
// et on garde ceux qui manquent. Plus la profondeur est grande, plus la
// compétence est une fondation : on l'apprend en premier. On regroupe
// ensuite par formation.
// ---------------------------------------------------------------------
WITH ['C01', 'C02', 'C05', 'C06'] AS acquises
MATCH (m:Metier {id: 'M02'})-[r:REQUIERT]->(c:Competence)
MATCH p = (c)-[:PREREQUIS*0..4]->(besoin:Competence)
WHERE NOT besoin.id IN acquises
WITH besoin, max(length(p)) AS profondeur, max(r.importance) AS poids
MATCH (f:Formation)-[d:DEVELOPPE]->(besoin)
WITH f, collect(DISTINCT besoin.nom) AS competences, max(profondeur) AS niveau_fondation,
     sum(poids * d.niveau_acquis) AS score
RETURN f.id AS id, f.nom AS formation, f.duree_heures AS heures, niveau_fondation, competences, score
ORDER BY niveau_fondation DESC, score DESC;


// ---------------------------------------------------------------------
// Q7 (bonus) - COMPÉTENCES PIVOT : demandées par le plus de métiers,
// avec le nombre de formations disponibles pour les acquérir.
// ---------------------------------------------------------------------
MATCH (m:Metier)-[r:REQUIERT]->(c:Competence)
WITH c, count(DISTINCT m) AS nb_metiers, round(avg(r.importance), 2) AS importance_moyenne
OPTIONAL MATCH (f:Formation)-[:DEVELOPPE]->(c)
RETURN c.id AS id, c.nom AS competence, nb_metiers, importance_moyenne,
       count(DISTINCT f) AS nb_formations
ORDER BY nb_metiers DESC, importance_moyenne DESC, competence
LIMIT 10;


// ---------------------------------------------------------------------
// Q8 (bonus) - MÉTIERS PROCHES du Data Analyst (M01) : indice de Jaccard
// sur les compétences requises (communes / union).
// ---------------------------------------------------------------------
MATCH (a:Metier {id: 'M01'})-[:REQUIERT]->(c:Competence)<-[:REQUIERT]-(b:Metier)
WITH a, b, collect(c.nom) AS communes, count(c) AS nb_communes
MATCH (a)-[:REQUIERT]->(ca:Competence)
WITH a, b, communes, nb_communes, count(ca) AS na
MATCH (b)-[:REQUIERT]->(cb:Competence)
WITH a, b, communes, nb_communes, na, count(cb) AS nb
RETURN b.id AS id, b.nom AS metier, nb_communes,
       round(1.0 * nb_communes / (na + nb - nb_communes), 2) AS jaccard, communes
ORDER BY jaccard DESC
LIMIT 5;


// ---------------------------------------------------------------------
// Q9 (bonus) - INTÉGRITÉ : aucun cycle ne doit exister dans PREREQUIS.
// Doit retourner 0 ligne.
// ---------------------------------------------------------------------
MATCH p = (c:Competence)-[:PREREQUIS*1..10]->(c)
RETURN c.id AS competence_en_cycle, length(p) AS longueur
LIMIT 5;


// ---------------------------------------------------------------------
// Q10 (bonus) - LES 5 PARCOURS PRÉDÉFINIS : métier visé, formations dans
// l'ordre et durée totale.
// ---------------------------------------------------------------------
MATCH (p:Parcours)-[:MENE_A]->(m:Metier)
MATCH (p)-[i:INCLUT]->(f:Formation)
WITH p, m, i, f ORDER BY i.ordre
RETURN p.id AS id, p.nom AS parcours, m.nom AS metier,
       collect(f.nom) AS formations_dans_lordre, sum(f.duree_heures) AS heures_totales
ORDER BY id;
