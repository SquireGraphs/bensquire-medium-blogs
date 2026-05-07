"""
schema.py
─────────
Defines and applies the Neo4j graph schema for the reddit-knowledge-graph.

Node labels and relationship types
────────────────────────────────────

  ┌──────────────┐   POSTED      ┌──────────┐   IN_SUBREDDIT  ┌────────────┐
  │    User      │──────────────►│   Post   │────────────────►│ Subreddit  │
  └──────────────┘               └──────────┘                 └────────────┘
         │                            │ │
   COMMENTED                    MENTIONS │ COVERS
         │                            │ │
         ▼                            ▼ ▼
  ┌──────────────┐             ┌────────┐ ┌───────┐
  │   Comment    │──MENTIONS──►│ Entity │ │ Topic │
  └──────────────┘             └────────┘ └───────┘
         │        ON_POST           ▲
         └─────────────────────────►│  (via Post or Comment)
                                  RELATED_TO (Entity↔Entity co-occurrence)

Run `python scripts/setup_schema.py` to apply this schema to a running Neo4j
instance. The setup is idempotent — safe to re-run at any time.
"""

from __future__ import annotations

import logging
from typing import List

from src.graph.neo4j_client import Neo4jClient

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Constraints  (enforce uniqueness + create implicit indexes)
# ─────────────────────────────────────────────────────────────────────────────

CONSTRAINTS: List[str] = [
    # Each Reddit post is uniquely identified by its Reddit ID
    "CREATE CONSTRAINT post_id_unique IF NOT EXISTS FOR (p:Post) REQUIRE p.id IS UNIQUE",
    # Each comment is uniquely identified by its Reddit ID
    "CREATE CONSTRAINT comment_id_unique IF NOT EXISTS FOR (c:Comment) REQUIRE c.id IS UNIQUE",
    # Usernames are unique on Reddit
    "CREATE CONSTRAINT user_username_unique IF NOT EXISTS FOR (u:User) REQUIRE u.username IS UNIQUE",
    # Subreddit names are unique
    "CREATE CONSTRAINT subreddit_name_unique IF NOT EXISTS FOR (s:Subreddit) REQUIRE s.name IS UNIQUE",
    # Entities are deduplicated by (name, type) pair
    "CREATE CONSTRAINT entity_name_type_unique IF NOT EXISTS FOR (e:Entity) REQUIRE (e.name, e.type) IS UNIQUE",
    # Topics are deduplicated by name
    "CREATE CONSTRAINT topic_name_unique IF NOT EXISTS FOR (t:Topic) REQUIRE t.name IS UNIQUE",
]

# ─────────────────────────────────────────────────────────────────────────────
# Indexes  (speed up common lookups and full-text search)
# ─────────────────────────────────────────────────────────────────────────────

INDEXES: List[str] = [
    # Temporal lookups — very common in analytics queries
    "CREATE INDEX post_created_idx IF NOT EXISTS FOR (p:Post) ON (p.created_utc)",
    "CREATE INDEX comment_created_idx IF NOT EXISTS FOR (c:Comment) ON (c.created_utc)",
    # Sentiment score range queries
    "CREATE INDEX post_sentiment_idx IF NOT EXISTS FOR (p:Post) ON (p.sentiment_score)",
    "CREATE INDEX comment_sentiment_idx IF NOT EXISTS FOR (c:Comment) ON (c.sentiment_score)",
    # Subreddit filtering
    "CREATE INDEX post_subreddit_idx IF NOT EXISTS FOR (p:Post) ON (p.subreddit)",
    # Entity type filtering
    "CREATE INDEX entity_type_idx IF NOT EXISTS FOR (e:Entity) ON (e.type)",
    # Score / upvote sorting
    "CREATE INDEX post_score_idx IF NOT EXISTS FOR (p:Post) ON (p.score)",
    "CREATE INDEX comment_score_idx IF NOT EXISTS FOR (c:Comment) ON (c.score)",
]

# ─────────────────────────────────────────────────────────────────────────────
# Full-text search indexes  (power semantic search over post bodies)
# ─────────────────────────────────────────────────────────────────────────────

FULLTEXT_INDEXES: List[str] = [
    """CREATE FULLTEXT INDEX post_fulltext IF NOT EXISTS
       FOR (p:Post) ON EACH [p.title, p.body]
       OPTIONS {indexConfig: {`fulltext.analyzer`: 'english'}}""",
    """CREATE FULLTEXT INDEX comment_fulltext IF NOT EXISTS
       FOR (c:Comment) ON EACH [c.body]
       OPTIONS {indexConfig: {`fulltext.analyzer`: 'english'}}""",
    """CREATE FULLTEXT INDEX entity_fulltext IF NOT EXISTS
       FOR (e:Entity) ON EACH [e.name]""",
]


# ─────────────────────────────────────────────────────────────────────────────
# Schema application
# ─────────────────────────────────────────────────────────────────────────────

def apply_schema(client: Neo4jClient) -> None:
    """
    Apply all constraints, indexes, and full-text indexes to Neo4j.

    This function is idempotent — all statements use ``IF NOT EXISTS``.

    Parameters
    ----------
    client : Neo4jClient
        An open Neo4j client connected to the target database.
    """
    logger.info("Applying Neo4j schema...")

    _apply_statements(client, CONSTRAINTS, label="constraint")
    _apply_statements(client, INDEXES, label="index")
    _apply_statements(client, FULLTEXT_INDEXES, label="fulltext index")

    logger.info("Schema applied successfully.")


def drop_schema(client: Neo4jClient) -> None:
    """
    Drop ALL constraints and indexes (useful for a clean rebuild).

    WARNING: This destroys all schema metadata. Data nodes remain intact.
    """
    logger.warning("Dropping all constraints and indexes...")
    client.query("CALL apoc.schema.assert({}, {})")
    logger.warning("Schema dropped.")


def _apply_statements(client: Neo4jClient, statements: List[str], label: str) -> None:
    """Execute a list of DDL statements, logging each one."""
    for stmt in statements:
        short = stmt.strip().split("\n")[0][:80]
        try:
            client.query(stmt)
            logger.debug("  ✓ %s: %s...", label, short)
        except Exception as exc:
            # Some Neo4j versions raise on duplicate constraint names even with
            # IF NOT EXISTS — log and continue rather than aborting.
            logger.warning("  ⚠ %s skipped (%s): %s...", label, exc, short)
