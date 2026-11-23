// =====================================================================
// P30 - Recommandation de parcours de formation par compétences
// 01_schema.cypher : contraintes et index (idempotent : IF NOT EXISTS)
//
// MODÈLE DE GRAPHE
//   (:Metier      {id, nom, secteur, description})
//   (:Competence  {id, nom, categorie, description})
//   (:Formation   {id, nom, organisme, duree_heures, niveau, modalite, description})
//   (:Parcours    {id, nom, description, duree_mois})
//
//   (Metier)-[:REQUIERT   {importance 1..5}]->(Competence)
//   (Formation)-[:DEVELOPPE {niveau_acquis 1..3}]->(Competence)
//   (Competence)-[:PREREQUIS]->(Competence)      A -> B : "A exige B au préalable"
//   (Parcours)-[:MENE_A]->(Metier)
//   (Parcours)-[:INCLUT   {ordre}]->(Formation)  composition ordonnée d'un parcours
//
// Exécution : python init_neo4j.py   (ou copier/coller dans Neo4j Browser)
// Remarque : les contraintes d'existence (IS NOT NULL) sont réservées à
// l'édition Enterprise ; la validation des propriétés est donc faite par
// l'API (Pydantic) et par le script d'initialisation.
// =====================================================================

// --- Unicité des identifiants (crée aussi un index) ---
CREATE CONSTRAINT metier_id IF NOT EXISTS FOR (m:Metier) REQUIRE m.id IS UNIQUE;
CREATE CONSTRAINT competence_id IF NOT EXISTS FOR (c:Competence) REQUIRE c.id IS UNIQUE;
CREATE CONSTRAINT formation_id IF NOT EXISTS FOR (f:Formation) REQUIRE f.id IS UNIQUE;
CREATE CONSTRAINT parcours_id IF NOT EXISTS FOR (p:Parcours) REQUIRE p.id IS UNIQUE;

// --- Unicité des noms (évite les doublons créés via le CRUD) ---
CREATE CONSTRAINT metier_nom IF NOT EXISTS FOR (m:Metier) REQUIRE m.nom IS UNIQUE;
CREATE CONSTRAINT competence_nom IF NOT EXISTS FOR (c:Competence) REQUIRE c.nom IS UNIQUE;
CREATE CONSTRAINT formation_nom IF NOT EXISTS FOR (f:Formation) REQUIRE f.nom IS UNIQUE;
CREATE CONSTRAINT parcours_nom IF NOT EXISTS FOR (p:Parcours) REQUIRE p.nom IS UNIQUE;

// --- Index de recherche / filtrage ---
CREATE INDEX competence_categorie IF NOT EXISTS FOR (c:Competence) ON (c.categorie);
CREATE INDEX formation_niveau IF NOT EXISTS FOR (f:Formation) ON (f.niveau);
CREATE INDEX metier_secteur IF NOT EXISTS FOR (m:Metier) ON (m.secteur);
