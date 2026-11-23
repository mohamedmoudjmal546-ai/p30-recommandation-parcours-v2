// =====================================================================
// 00_load_csv.cypher : chargement alternatif depuis Neo4j Browser
// (équivalent de init_neo4j.py). Exécuter d'abord 01_schema.cypher.
//
// docker-compose.yml monte ./data dans le dossier "import" de Neo4j,
// d'où les URLs file:///nom.csv. Exécuter les blocs un par un (ou tout
// le fichier avec cypher-shell -f). MERGE rend le chargement idempotent.
// =====================================================================

LOAD CSV WITH HEADERS FROM 'file:///metiers.csv' AS row
MERGE (m:Metier {id: row.id})
SET m.nom = row.nom, m.secteur = row.secteur, m.description = row.description;

LOAD CSV WITH HEADERS FROM 'file:///competences.csv' AS row
MERGE (c:Competence {id: row.id})
SET c.nom = row.nom, c.categorie = row.categorie, c.description = row.description;

LOAD CSV WITH HEADERS FROM 'file:///formations.csv' AS row
MERGE (f:Formation {id: row.id})
SET f.nom = row.nom, f.organisme = row.organisme,
    f.duree_heures = toInteger(row.duree_heures), f.niveau = row.niveau,
    f.modalite = row.modalite, f.description = row.description;

LOAD CSV WITH HEADERS FROM 'file:///parcours.csv' AS row
MERGE (p:Parcours {id: row.id})
SET p.nom = row.nom, p.description = row.description, p.duree_mois = toInteger(row.duree_mois);

LOAD CSV WITH HEADERS FROM 'file:///requiert.csv' AS row
MATCH (m:Metier {id: row.metier_id}), (c:Competence {id: row.competence_id})
MERGE (m)-[r:REQUIERT]->(c)
SET r.importance = toInteger(row.importance);

LOAD CSV WITH HEADERS FROM 'file:///developpe.csv' AS row
MATCH (f:Formation {id: row.formation_id}), (c:Competence {id: row.competence_id})
MERGE (f)-[d:DEVELOPPE]->(c)
SET d.niveau_acquis = toInteger(row.niveau_acquis);

LOAD CSV WITH HEADERS FROM 'file:///prerequis.csv' AS row
MATCH (c:Competence {id: row.competence_id}), (p:Competence {id: row.prerequis_id})
MERGE (c)-[:PREREQUIS]->(p);

LOAD CSV WITH HEADERS FROM 'file:///mene_a.csv' AS row
MATCH (p:Parcours {id: row.parcours_id}), (m:Metier {id: row.metier_id})
MERGE (p)-[:MENE_A]->(m);

LOAD CSV WITH HEADERS FROM 'file:///parcours_formations.csv' AS row
MATCH (p:Parcours {id: row.parcours_id}), (f:Formation {id: row.formation_id})
MERGE (p)-[i:INCLUT]->(f)
SET i.ordre = toInteger(row.ordre);
