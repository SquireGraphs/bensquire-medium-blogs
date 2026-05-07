# Customization Guide

This project is designed to be reused. This guide explains how to adapt the pipeline for any Reddit communities and keywords you want to track.

---

## Changing the target subreddits

Edit the `.env` file:

```env
TARGET_SUBREDDITS=learnpython,MachineLearning,LocalLLaMA,singularity
```

Or override at runtime:

```bash
python scripts/run_pipeline.py --subreddit learnpython
```

No code changes required — the scraper reads from `settings.target_subreddits`.

---

## Changing the filter keywords

Edit the `.env` file:

```env
FILTER_KEYWORDS=LangChain,LlamaIndex,vector database,embedding,RAG pipeline
```

Keywords are matched case-insensitively against post titles, bodies, and comments. A post is kept if **any** keyword matches.

To match **all** keywords (AND logic instead of OR), edit `src/ingestion/scraper.py`:

```python
# Change this line in _post_matches_keywords():
return any(keyword in combined for keyword in self._keywords)
# To:
return all(keyword in combined for keyword in self._keywords)
```

---

## Extending the graph schema

### Adding a new node type

For example, to add a `Company` node tracking which companies are mentioned:

1. **Add a Cypher constraint in `src/graph/schema.py`:**

```python
CONSTRAINTS.append(
    "CREATE CONSTRAINT company_name_unique IF NOT EXISTS FOR (c:Company) REQUIRE c.name IS UNIQUE"
)
```

2. **Add ingestion logic in `src/graph/ingester.py`:**

```python
def upsert_company(self, name: str, description: str = "") -> None:
    self.client.query(
        """
        MERGE (c:Company {name: $name})
        SET c.description = $description,
            c.last_updated = $now
        """,
        {"name": name, "description": description, "now": datetime.utcnow().isoformat()},
    )
```

3. **Add a query function in `src/graph/queries.py`** and a tool in `src/agent/tools.py`.

---

## Adding new agent tools

1. Write a query function in `src/graph/queries.py`:

```python
def get_posts_by_author(
    client: Neo4jClient, username: str, limit: int = 10
) -> List[Dict[str, Any]]:
    return client.query(
        """
        MATCH (u:User {username: $username})-[:POSTED]->(p:Post)
        RETURN p.id, p.title, p.subreddit, p.score, p.created_utc
        ORDER BY p.score DESC LIMIT $limit
        """,
        {"username": username, "limit": limit},
    )
```

2. Add a `@tool` function in `src/agent/tools.py`:

```python
@tool
def get_posts_by_author(username: str, limit: int = 10) -> str:
    """
    Get the top posts by a specific Reddit user in the tracked communities.

    Args:
        username: Reddit username (without u/ prefix).
        limit: Maximum posts to return.
    """
    results = queries.get_posts_by_author(_client(), username, limit)
    return json.dumps(results, indent=2)
```

3. Add the tool to `ALL_TOOLS` at the bottom of `tools.py`:

```python
ALL_TOOLS = [
    ...,
    get_posts_by_author,  # Add here
]
```

---

## Integrating community forums (future)

To add `community.snowflake.com`, `community.databricks.com`, or `community.neo4j.com`:

1. Create `src/ingestion/forum_scraper.py` following the same pattern as `scraper.py`.
2. The forum scraper should return the same `RedditPost` / `RedditComment` data models (or a unified base model).
3. Add a `Platform` property to `Post` nodes to distinguish Reddit posts from forum posts.
4. The rest of the pipeline (processing, graph, agent) works unchanged.

---

## Connecting to Snowflake or Databricks (future)

### Export to Snowflake

```python
# src/export/snowflake_exporter.py (to be built)
# Query Neo4j → flatten to DataFrames → write to Snowflake via snowflake-connector-python

from neo4j import GraphDatabase
import snowflake.connector

def export_posts_to_snowflake(neo4j_uri, neo4j_auth, sf_conn_params):
    driver = GraphDatabase.driver(neo4j_uri, auth=neo4j_auth)
    with driver.session() as session:
        records = session.run("MATCH (p:Post) RETURN p {.*}").data()
    
    # Write to Snowflake...
```

### Export to Databricks

Use the `databricks-sdk` or write to Delta Lake via Spark:

```python
# Export Neo4j results to Parquet, then read into Databricks
import pandas as pd
records = neo4j_client.query("MATCH (p:Post) RETURN p {.*}")
df = pd.DataFrame(records)
df.to_parquet("posts.parquet")
# Upload to Databricks DBFS or S3
```

---

## Changing the LLM

The LLM is configured entirely through environment variables. To switch providers:

```env
# To use OpenAI GPT-4o (requires langchain-openai package):
# Change src/agent/graph_agent.py build_llm() to use ChatOpenAI
```

Or to make it fully configurable, install `langchain-openai` and modify `build_llm()`:

```python
# src/agent/graph_agent.py
def build_llm():
    if settings.llm_provider == "openai":
        from langchain_openai import ChatOpenAI
        llm = ChatOpenAI(model="gpt-4o", temperature=0)
    else:
        from langchain_anthropic import ChatAnthropic
        llm = ChatAnthropic(model=settings.anthropic_model, temperature=0)
    return llm.bind_tools(ALL_TOOLS)
```

---

## Running at scale

For large datasets (100k+ posts), consider:

1. **Parallel enrichment**: Use `concurrent.futures.ThreadPoolExecutor` in `orchestrator.py` to call Claude for multiple posts simultaneously (stay within rate limits).

2. **Queue-based architecture**: Replace the in-memory list of posts with a Redis or RabbitMQ queue. The scraper pushes post IDs; worker processes consume from the queue and enrich/ingest independently.

3. **Checkpoint table**: Add a Neo4j or SQLite table recording which post IDs have been ingested. The pipeline checks this before re-processing, enabling true resumability.

4. **Neo4j AuraDB**: Swap local Docker for AuraDB by changing `NEO4J_URI` to your Aura connection string. Everything else is identical.
