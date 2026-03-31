from neo4j_viz.snowflake import from_snowflake
from snowflake.snowpark.context import get_active_session
import streamlit.components.v1 as components

session = get_active_session()

project_config = {
    'nodeTables': ['SUMODB.PUBLIC.RIKISHI_BASHO_2511_LOUVAIN'],
    'relationshipTables': {
        'SUMODB.PUBLIC.RIKISHI_BOUTS_2511': {
            'sourceTable': 'SUMODB.PUBLIC.RIKISHI_BASHO_2511_LOUVAIN',
            'targetTable': 'SUMODB.PUBLIC.RIKISHI_BASHO_2511_LOUVAIN',
            'orientation': 'UNDIRECTED'
        }
    }
}

viz_graph = from_snowflake(session, project_config)
viz_graph.color_nodes(property='COMMUNITY_ID', override=True)

rendered = viz_graph.render({'max_allowed_nodes': 10000})
components.html(rendered.data, height=950)
