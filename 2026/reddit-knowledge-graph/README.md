# Reddit Knowledge Graph

> Build a **Neo4j knowledge graph** from Reddit communities — then query it with a **Claude-powered AI agent** that answers questions about sentiment, trends, and cross-community discussions.

[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue)](https://python.org)
[![Neo4j 5.x](https://img.shields.io/badge/Neo4j-5.x-green)](https://neo4j.com)
[![Claude](https://img.shields.io/badge/LLM-Anthropic%20Claude-orange)](https://anthropic.com)
[![LangGraph](https://img.shields.io/badge/Agent-LangGraph-purple)](https://langchain-ai.github.io/langgraph/)

---

## What this project does

1. **Scrapes** posts and comments from 10 data/AI subreddits using the Reddit API (PRAW).
2. **Filters** content to keyword matches (`Neo4j`, `graphRAG`, `agentic AI`, etc.) from the last 3 years.
3. **Enriches** each post and comment with Claude — extracting named entities, topics, and sentiment.
4. **Builds** a Neo4j property graph connecting posts, comments, users, entities, and topics.
5. **Answers** natural-language questions via a LangGraph AI agent backed by Cypher queries.

### Example questions the agent can answer

- *"Where are people talking about Neo4j integrations in the tech communities the most?"*
- *"What problems are people facing with Agentic AI knowledge graphs?"*
- *"How is sentiment surrounding Neo4j across r/databricks and r/snowflake?"*
- *"Who is active across multiple communities we follow?"*
- *"What topics are trending in r/dataengineering this month?"*

---

## Quick Start

### Prerequisites

| Requirement | Version |
|------------|---------|
| Python | 3.11 or higher |
| Docker & Docker Compose | Any recent version |
| Reddit developer account | [Create here](https://www.reddit.com/prefs/apps) |
| Anthropic API key | [Get here](https://console.anthropic.com) |

### 1. Clone and install

```bash
git clone https://github.com/SquireGraphs/bensquire-medium-blogs/reddit-knowledge-graph.git
cd reddit-knowledge-graph
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env with your Reddit API credentials and Anthropic API key
```

The minimum required variables are:

```env
REDDIT_CLIENT_ID=your_client_id
REDDIT_CLIENT_SECRET=your_client_secret
ANTHROPIC_API_KEY=sk-ant-...
```

See `.env.example` for all options with explanations.

### 3. Start Neo4j

```bash
docker compose up -d
```

Neo4j Browser will be available at **http://localhost:7474** (user: `neo4j`, password: `password123`).

Wait ~30 seconds for Neo4j to initialise before proceeding.

### 4. Initialise the schema

```bash
python scripts/setup_schema.py
```

This creates all node constraints, property indexes, and full-text search indexes.

### 5. Run the pipeline

```bash
# Full run (all 10 subreddits)
python scripts/run_pipeline.py

# Test with a single subreddit first
python scripts/run_pipeline.py --subreddit neo4j

# Dry-run to verify credentials before writing to Neo4j
python scripts/run_pipeline.py --dry-run
```

### 6. Ask the AI agent

```bash
# Interactive REPL
python scripts/run_agent.py

# Single question
python scripts/run_agent.py --question "Where is Neo4j discussed most?"

# Streaming mode (see tool calls live)
python scripts/run_agent.py --stream
```

---

## Project Structure

```
reddit-knowledge-graph/
│
├── src/
│   ├── config.py                # Centralised settings (pydantic-settings)
│   │
│   ├── ingestion/               # Reddit data collection
│   │   ├── reddit_client.py     # PRAW wrapper
│   │   ├── scraper.py           # Keyword-filtered post/comment scraper
│   │   └── models.py            # Pydantic models: RedditPost, RedditComment
│   │
│   ├── processing/              # NLP enrichment via Claude
│   │   ├── entity_extractor.py  # Entity extraction, sentiment, topics
│   │   └── models.py            # EnrichedContent, SentimentResult, etc.
│   │
│   ├── graph/                   # Neo4j layer
│   │   ├── neo4j_client.py      # Driver wrapper with batch helpers
│   │   ├── schema.py            # Constraints, indexes, full-text indexes
│   │   ├── ingester.py          # MERGE-based upsert logic
│   │   └── queries.py           # Cypher query library (12 queries)
│   │
│   ├── agent/                   # AI agent
│   │   ├── graph_agent.py       # LangGraph ReAct agent
│   │   ├── tools.py             # 12 LangChain tools wrapping Cypher queries
│   │   └── prompts.py           # System prompt and example questions
│   │
│   └── pipeline/
│       └── orchestrator.py      # End-to-end pipeline orchestration
│
├── scripts/
│   ├── setup_schema.py          # CLI: initialise Neo4j schema
│   ├── run_pipeline.py          # CLI: run the ingestion pipeline
│   └── run_agent.py             # CLI: interactive AI agent
│
├── tests/                       # Unit tests
├── docs/                        # Extended documentation
├── docker-compose.yml           # Neo4j local stack
├── .env.example                 # Environment variable template
├── requirements.txt
└── pyproject.toml
```

---

## Knowledge Graph Schema

See [docs/data-model.md](docs/data-model.md) for the full schema diagram and property reference.

**Node labels:** `Post`, `Comment`, `User`, `Subreddit`, `Entity`, `Topic`

**Relationship types:**
`POSTED`, `COMMENTED`, `IN_SUBREDDIT`, `ON_POST`, `REPLY_TO`, `MENTIONS`, `COVERS`, `RELATED_TO`, `ACTIVE_IN`

---

## Tracked Communities

| Subreddit | Focus |
|-----------|-------|
| r/neo4j | Graph database discussions |
| r/knowledgegraph | Knowledge graph concepts |
| r/rag | Retrieval-Augmented Generation |
| r/snowflake | Snowflake data platform |
| r/databricks | Databricks / Spark |
| r/microsoftfabric | Microsoft Fabric |
| r/dataengineering | Data engineering broadly |
| r/analytics | Analytics and BI |
| r/dataanalysis | Data analysis techniques |
| r/datascience | Data science & ML |

---

## Filter Keywords

Posts and comments are only ingested if they contain at least one of:

`Neo4j` · `graph database` · `graphRAG` · `graph AI` · `graph integrations` · `connected components` · `path finding` · `agentic AI`

Customise these in `.env` — see [docs/customization.md](docs/customization.md).

---

## Adapting for Your Own Communities

This project is designed to be reused. See **[docs/customization.md](docs/customization.md)** for a step-by-step guide to:

- Monitoring different subreddits
- Changing the filter keywords
- Extending the graph schema with new node types
- Adding new agent tools for new query patterns

---

## Documentation

| Document | Description |
|----------|-------------|
| [docs/setup.md](docs/setup.md) | Detailed setup guide |
| [docs/architecture.md](docs/architecture.md) | System design and data flow |
| [docs/data-model.md](docs/data-model.md) | Graph schema reference |
| [docs/customization.md](docs/customization.md) | How to adapt the pipeline |

---

## Future Integrations

This project is the foundation for a broader data platform integration:

- **Snowflake** — export the graph as structured tables for dashboarding and SQL analytics
- **Databricks** — run batch NLP over the graph data using Spark
- **Community forums** — extend ingestion to `community.snowflake.com`, `community.databricks.com`, `community.neo4j.com`

---

## License

MIT
