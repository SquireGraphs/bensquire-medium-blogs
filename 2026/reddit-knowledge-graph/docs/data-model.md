# Graph Data Model

## Schema Diagram

```
            POSTED           IN_SUBREDDIT
  ┌────────┐──────────►┌──────┐──────────────►┌───────────┐
  │  User  │           │ Post │               │ Subreddit │
  └────────┘◄──────────└──────┘               └───────────┘
      │       COMMENTED   │ │
      │                   │ │  MENTIONS ──────►┌────────┐
      │                   │ └────────────────► │ Entity │
      │                   │                    └────────┘
      │                   │  COVERS ──────────►┌───────┐
      │                   └────────────────►   │ Topic │
      │                                        └───────┘
      │       COMMENTED  ┌─────────┐
      └─────────────────►│ Comment │
                         └─────────┘
                              │
                        ON_POST (back to Post)
                        REPLY_TO (to parent Comment)
                        MENTIONS → Entity
                        COVERS → Topic

  Entity ──RELATED_TO──► Entity  (co-occurrence)
  User ──ACTIVE_IN──────► Subreddit (cross-community)
```

---

## Node Labels

### Post

Represents a Reddit submission.

| Property | Type | Description |
|----------|------|-------------|
| `id` | String | Reddit post ID (unique) |
| `title` | String | Post title |
| `body` | String | Selftext body (empty for link posts) |
| `url` | String | URL of the post |
| `permalink` | String | Full Reddit permalink |
| `subreddit` | String | Subreddit name (lowercase, denormalised for fast filtering) |
| `score` | Integer | Net upvotes |
| `upvote_ratio` | Float | Ratio of upvotes to total votes (0.0–1.0) |
| `num_comments` | Integer | Total comment count (from Reddit) |
| `flair` | String | Post flair text (nullable) |
| `created_utc` | String | ISO 8601 UTC timestamp |
| `is_self` | Boolean | True = text post, False = link post |
| `summary` | String | Claude-generated 1-3 sentence summary |
| `sentiment_label` | String | `positive` / `neutral` / `negative` / `mixed` |
| `sentiment_score` | Float | Score from -1.0 (most negative) to +1.0 (most positive) |
| `sentiment_reasoning` | String | Claude's explanation for the sentiment |
| `last_updated` | String | When this node was last written |

### Comment

Represents a Reddit comment.

| Property | Type | Description |
|----------|------|-------------|
| `id` | String | Reddit comment ID (unique) |
| `body` | String | Comment text |
| `score` | Integer | Net upvotes |
| `created_utc` | String | ISO 8601 UTC timestamp |
| `depth` | Integer | Nesting depth (0 = direct reply to post) |
| `permalink` | String | Full Reddit permalink |
| `is_top_level` | Boolean | True if direct reply to the post |
| `sentiment_label` | String | Same as Post |
| `sentiment_score` | Float | Same as Post |

### User

Represents a Reddit account.

| Property | Type | Description |
|----------|------|-------------|
| `username` | String | Reddit username (unique) |
| `first_seen` | String | When first observed in the dataset |
| `last_seen` | String | When last observed in the dataset |

> **Note:** User karma and account creation date are only available via authenticated requests and are intentionally omitted to keep ingestion fast.

### Subreddit

| Property | Type | Description |
|----------|------|-------------|
| `name` | String | Lowercase subreddit name (unique) |
| `display_name` | String | e.g. `r/neo4j` |
| `subscribers` | Integer | Subscriber count at time of seeding |
| `description` | String | Public subreddit description |
| `created_utc` | String | Subreddit creation date |
| `last_updated` | String | When last refreshed |

### Entity

A named technology, company, concept, person, or other domain entity extracted by Claude.

| Property | Type | Description |
|----------|------|-------------|
| `name` | String | Canonical entity name (title-cased) |
| `type` | String | One of: `technology`, `concept`, `company`, `person`, `product`, `framework`, `language`, `other` |
| `first_seen` | String | First appearance in the dataset |
| `last_seen` | String | Most recent appearance |

Entities are deduplicated on `(name, type)` — the combination is unique.

### Topic

A high-level topic label assigned to posts and comments by Claude.

| Property | Type | Description |
|----------|------|-------------|
| `name` | String | Short topic label, e.g. `"graph RAG"`, `"performance tuning"` (unique) |
| `first_seen` | String | First appearance |
| `last_seen` | String | Most recent appearance |

---

## Relationship Types

| Relationship | From → To | Properties | Description |
|-------------|-----------|------------|-------------|
| `POSTED` | User → Post | — | User authored this post |
| `COMMENTED` | User → Comment | — | User authored this comment |
| `IN_SUBREDDIT` | Post → Subreddit | — | Post belongs to this community |
| `ON_POST` | Comment → Post | — | Comment is on this post |
| `REPLY_TO` | Comment → Comment | — | Comment replies to another comment |
| `MENTIONS` | Post/Comment → Entity | `mentions` (int), `context` (string) | Content mentions this entity |
| `COVERS` | Post/Comment → Topic | `relevance` (float 0–1) | Content is about this topic |
| `RELATED_TO` | Entity ↔ Entity | `co_occurrence_count` (int) | Entities appear together in the same content |
| `ACTIVE_IN` | User → Subreddit | `activity_count` (int) | User has posted/commented in this community |

---

## Example Cypher Queries

### Find where Neo4j is discussed most
```cypher
MATCH (p:Post)-[:MENTIONS]->(e:Entity),
      (p)-[:IN_SUBREDDIT]->(s:Subreddit)
WHERE toLower(e.name) CONTAINS 'neo4j'
RETURN s.name AS subreddit, count(p) AS post_count
ORDER BY post_count DESC
LIMIT 10
```

### Find cross-community users
```cypher
MATCH (u:User)-[:ACTIVE_IN]->(s:Subreddit)
WITH u, collect(s.name) AS communities, count(s) AS count
WHERE count >= 3
RETURN u.username, communities, count
ORDER BY count DESC
LIMIT 20
```

### Sentiment trend for Neo4j over time
```cypher
MATCH (p:Post)-[:MENTIONS]->(e:Entity)
WHERE toLower(e.name) CONTAINS 'neo4j'
  AND p.sentiment_score IS NOT NULL
WITH substring(p.created_utc, 0, 7) AS month,
     avg(p.sentiment_score) AS avg_sentiment,
     count(p) AS post_count
ORDER BY month
RETURN month, round(avg_sentiment, 3) AS avg_sentiment, post_count
```

### Most common problems with knowledge graphs
```cypher
MATCH (p:Post)-[:COVERS]->(t:Topic),
      (p)-[:MENTIONS]->(e:Entity)
WHERE toLower(e.name) CONTAINS 'knowledge graph'
  AND p.sentiment_label IN ['negative', 'mixed']
WITH t.name AS topic, count(p) AS negative_posts
ORDER BY negative_posts DESC
LIMIT 10
RETURN topic, negative_posts
```

### Find entities that co-occur with graphRAG
```cypher
MATCH (e1:Entity)-[r:RELATED_TO]-(e2:Entity)
WHERE toLower(e1.name) CONTAINS 'graphrag'
RETURN e2.name AS related_entity, e2.type, r.co_occurrence_count
ORDER BY r.co_occurrence_count DESC
LIMIT 15
```
