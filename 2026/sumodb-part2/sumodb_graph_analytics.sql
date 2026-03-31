Create or replace table sumodb.public.rikishi_basho_2511 AS
SELECT Distinct rikishi_id NODEID FROM 
(SELECT left_id rikishi_id
FROM 
  "SUMODB"."PUBLIC"."SUMO_BOUTS_2603"
  WHERE BASHO_ID = 202511 
UNION 
SELECT right_id rikishi_id
FROM 
  "SUMODB"."PUBLIC"."SUMO_BOUTS_2603"
  WHERE BASHO_ID = 202511 )

Create or replace table sumodb.public.rikishi_bouts_2511 AS 
(SELECT DISTINCT 
winner_id SOURCENODEID,
loser_id TARGETNODEID
FROM 
"SUMODB"."PUBLIC"."SUMO_BOUTS_2603"
WHERE BASHO_ID = 202511 
)

-- run as a privileged role, e.g. ACCOUNTADMIN
GRANT USAGE ON DATABASE SUMODB TO APPLICATION Neo4j_Graph_Analytics;
GRANT USAGE ON SCHEMA SUMODB.PUBLIC TO APPLICATION Neo4j_Graph_Analytics;

GRANT SELECT ON TABLE SUMODB.PUBLIC.RIKISHI_BASHO_2511 TO APPLICATION Neo4j_Graph_Analytics;
GRANT SELECT ON TABLE SUMODB.PUBLIC.RIKISHI_BOUTS_2511 TO APPLICATION Neo4j_Graph_Analytics;

-- run as a privileged role, e.g. ACCOUNTADMIN
GRANT USAGE ON DATABASE SUMODB TO APPLICATION Neo4j_Graph_Analytics;
GRANT USAGE ON SCHEMA SUMODB.PUBLIC TO APPLICATION Neo4j_Graph_Analytics;

GRANT CREATE TABLE ON SCHEMA SUMODB.PUBLIC TO APPLICATION Neo4j_Graph_Analytics;

CREATE ROLE IF NOT EXISTS NEO4J_GA_USER;
GRANT APPLICATION ROLE Neo4j_Graph_Analytics.app_user TO ROLE NEO4J_GA_USER;

CREATE ROLE IF NOT EXISTS NEO4J_GA_ADMIN;
GRANT APPLICATION ROLE Neo4j_Graph_Analytics.app_admin TO ROLE NEO4J_GA_ADMIN;

-- confirm the app exists
SHOW APPLICATIONS LIKE 'NEO4J_GRAPH_ANALYTICS';

CALL Neo4j_Graph_Analytics.graph.show_available_compute_pools();

SHOW GRANTS TO APPLICATION NEO4J_GRAPH_ANALYTICS

USE DATABASE Neo4j_Graph_Analytics;

-- 1) Make sure the app finished creating internal pools
CALL NEO4J_GRAPH_ANALYTICS.internal.grant_callback(['CREATE WAREHOUSE', 'CREATE COMPUTE POOL']);

-- 2) See which selectors actually exist
CALL NEO4J_GRAPH_ANALYTICS.graph.show_available_compute_pools();


GRANT SELECT ON FUTURE TABLES IN SCHEMA SUMODB.PUBLIC TO DATABASE ROLE BENSQUIRE;
GRANT SELECT ON FUTURE VIEWS IN SCHEMA SUMODB.PUBLIC TO DATABASE ROLE BENSQUIRE;

CALL Neo4j_Graph_Analytics.graph.louvain(
  'CPU_X64_XS',
  {
    'defaultTablePrefix': 'SUMODB.PUBLIC',
    'project': {
      'nodeTables': [ 'RIKISHI_BASHO_2511' ],
      'relationshipTables': {
        'RIKISHI_BOUTS_2511': {
          'sourceTable': 'RIKISHI_BASHO_2511',
          'targetTable': 'RIKISHI_BASHO_2511',
          'orientation': 'UNDIRECTED'
        }
      }
    },
    'compute': {
      'resultProperty': 'community_id'
    },
    'write': [{
      'nodeLabel': 'RIKISHI_BASHO_2511',
      'outputTable': 'RIKISHI_BASHO_2511_LOUVAIN',
      'nodeProperty': 'community_id'
    }]
  }
);
