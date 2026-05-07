# Architecture

## Overview

The Reddit Knowledge Graph is a three-layer system:

```
┌─────────────────────────────────────────────────────────────┐
│                     Ingestion Layer                          │
│  Reddit API (PRAW)  →  Scraper  →  Keyword Filter           │
└─────────────────────────────┬───────────────────────────────┘
                              │  RedditPost objects
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Processing Layer                          │
│  Anthropic Claude  →  Entity Extraction  →  Sentiment        │
└─────────────────────────────┬───────────────────────────────┘
                              │  EnrichedContent objects
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                     Graph Layer (Neo4j)                      │
│  Ingester (MERGE)  →  Nodes  →  Relationships  →  Indexes   │
└─────────────────────────────┬───────────────────────────────┘
                              │  Cypher queries
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      Agent Layer                             │
│  LangGraph  →  Claude (ReAct)  →  Tools  →  Natural Language│
└─────────────────────────────────────────────────────────────┘
```

---

## Data Flow

### 1. Ingestion

`RedditScraper` uses PRAW to call the Reddit API. For each subreddit it calls `.new()` to get the most recent posts, iterating backwards in time until it reaches the cutoff date (3 years by default).

Each post is checked against the keyword list. A post qualifies if **any** of the target keywords appears (case-insensitive) in the title, body, OR any top-level comment.

PRAW handles Reddit's OAuth 2.0 flow automatically. Authenticated requests get 60 requests/minute; unauthenticated get 10. The scraper adds a 2-second sleep between subreddits.

### 2. Processing

`EntityExtractor` sends each qualifying post to Claude using the Messages API. A single API call per post returns a structured JSON response with:

- **Entities**: Named technologies, companies, concepts (e.g., "Neo4j", "LangChain", "graph RAG")
- **Topics**: High-level topic labels (e.g., "performance tuning", "Cypher queries")
- **Sentiment**: Label (positive/neutral/negative/mixed) + score (-1.0 to +1.0)
- **Summary**: 1-3 sentence summary of the post

Comments are enriched individually. Claude is instructed to return raw JSON only (no markdown), and the output is validated by Pydantic models before proceeding.

Tenacity provides automatic retry with exponential backoff for API rate limits.

### 3. Graph Ingestion

`GraphIngester` writes all data to Neo4j using `MERGE` (upsert) patterns, making the pipeline fully idempotent. Running the pipeline twice on the same data only updates existing nodes.

The ingestion order matters for referential integrity:
1. Subreddit nodes (seeded first)
2. User nodes (MERGE on username)
3. Post nodes + `IN_SUBREDDIT` / `POSTED` edges
4. Comment nodes + `ON_POST` / `REPLY_TO` / `COMMENTED` edges
5. Entity nodes + `MENTIONS` edges
6. Topic nodes + `COVERS` edges
7. Entity co-occurrence `RELATED_TO` edges

### 4. Agent

The AI agent uses LangGraph's `StateGraph` to implement a ReAct (Reason + Act) loop:

```
START → LLM → (tools condition) → Tool Node → LLM → ... → END
```

Claude receives the user's question, decides which of 12 tools to call, receives the query results, and synthesises a final answer. Multi-hop queries are supported (e.g., first find which communities discuss an entity, then get sentiment for that entity in those communities).

---

## Key Design Decisions

### MERGE over INSERT
All Neo4j writes use `MERGE` rather than `CREATE`. This makes the pipeline idempotent — you can run it daily and it will update existing nodes rather than create duplicates.

### Sentiment as node properties
Sentiment score and label are stored as properties on `Post` and `Comment` nodes rather than as separate `Sentiment` nodes. This enables fast aggregation queries without joins and keeps the graph schema clean.

### Entity deduplication
Entities are identified by `(name, type)` pair. This means "Neo4j" as a `technology` and "Neo4j" as a `company` would be separate nodes, but all variants of "Neo4j" as a technology (e.g., "neo4j", "Neo4J") are normalised by Claude before ingestion.

### Cross-community user tracking
`User` nodes are global — a single user appearing in r/neo4j and r/databricks shares one `User` node. The `ACTIVE_IN` relationship to each `Subreddit` has an `activity_count` property that increments with each post or comment, making it easy to rank users by cross-community engagement.

### Stateless agent
The LangGraph agent is stateless per query — it builds a fresh LLM instance on each call. This means it's safe to run multiple agents in parallel, and there's no session state to manage. Conversation history can be added by persisting messages to a checkpointer (LangGraph supports this natively with SQLite or Redis).

---

## Rate Limits and Cost Estimates

### Reddit API
- Authenticated (with username/password): 60 requests/minute
- Unauthenticated (read-only): 10 requests/minute
- Hard limit on `/new` listings: 1,000 posts per subreddit
- Typical full backfill (10 subreddits, 500 posts each): ~20–30 minutes

### Anthropic API
- Model: `claude-3-5-haiku-20241022` (fastest, cheapest)
- Cost per post enrichment: ~$0.001–0.003
- Full backfill (5,000 posts): ~$5–15
- Ongoing daily incremental runs: < $1/day

### Neo4j
- Local Docker: free
- Neo4j AuraDB free tier: 50k nodes, 175k relationships (sufficient for initial builds)
- AuraDB Professional: scales with usage
