"""
queries.py
──────────
Pre-built Cypher query library used by the AI agent tools.

Each function accepts a Neo4jClient and typed parameters, runs a Cypher
query, and returns plain Python dicts/lists ready for the LLM to consume.

Adding new queries
──────────────────
1. Write a function following the pattern: `get_*` or `search_*`.
2. Accept `client: Neo4jClient` as the first argument.
3. Return `List[Dict[str, Any]]`.
4. Register the function as a tool in `src/agent/tools.py`.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from src.graph.neo4j_client import Neo4jClient

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Community / cross-subreddit queries
# ─────────────────────────────────────────────────────────────────────────────

def get_entity_discussion_by_community(
    client: Neo4jClient,
    entity_name: str,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """
    Find which communities discuss a given entity the most.

    Example question: "Where are people talking about Neo4j integrations
    in the tech communities the most?"
    """
    return client.query(
        """
        MATCH (e:Entity)-[:RELATED_TO|MENTIONS]-(content)-[:IN_SUBREDDIT|ON_POST*1..2]->(s:Subreddit)
        WHERE toLower(e.name) CONTAINS toLower($entity_name)
        WITH s.name AS subreddit, count(DISTINCT content) AS mention_count
        ORDER BY mention_count DESC
        LIMIT $limit
        RETURN subreddit, mention_count
        """,
        {"entity_name": entity_name, "limit": limit},
    )


def get_top_posts_mentioning_entity(
    client: Neo4jClient,
    entity_name: str,
    subreddit: Optional[str] = None,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """Return the highest-scored posts mentioning a given entity."""
    subreddit_filter = "AND p.subreddit = toLower($subreddit)" if subreddit else ""
    return client.query(
        f"""
        MATCH (p:Post)-[:MENTIONS]->(e:Entity)
        WHERE toLower(e.name) CONTAINS toLower($entity_name)
        {subreddit_filter}
        RETURN p.id        AS id,
               p.title     AS title,
               p.subreddit AS subreddit,
               p.score     AS score,
               p.permalink AS permalink,
               p.created_utc AS created_utc,
               p.summary   AS summary
        ORDER BY p.score DESC
        LIMIT $limit
        """,
        {"entity_name": entity_name, "subreddit": subreddit, "limit": limit},
    )


# ─────────────────────────────────────────────────────────────────────────────
# Sentiment queries
# ─────────────────────────────────────────────────────────────────────────────

def get_sentiment_summary_for_entity(
    client: Neo4jClient,
    entity_name: str,
) -> List[Dict[str, Any]]:
    """
    Aggregate sentiment across all posts & comments mentioning an entity.

    Example question: "How is sentiment surrounding Neo4j in the broader
    tech ecosystem?"
    """
    return client.query(
        """
        MATCH (n)-[:MENTIONS]->(e:Entity)
        WHERE toLower(e.name) CONTAINS toLower($entity_name)
          AND n.sentiment_label IS NOT NULL
        WITH n.sentiment_label AS label,
             avg(n.sentiment_score) AS avg_score,
             count(*) AS count
        ORDER BY count DESC
        RETURN label, round(avg_score, 3) AS avg_score, count
        """,
        {"entity_name": entity_name},
    )


def get_sentiment_by_subreddit(
    client: Neo4jClient,
    entity_name: str,
) -> List[Dict[str, Any]]:
    """Sentiment breakdown per subreddit for a given entity."""
    return client.query(
        """
        MATCH (p:Post)-[:MENTIONS]->(e:Entity),
              (p)-[:IN_SUBREDDIT]->(s:Subreddit)
        WHERE toLower(e.name) CONTAINS toLower($entity_name)
          AND p.sentiment_label IS NOT NULL
        WITH s.name AS subreddit,
             p.sentiment_label AS label,
             avg(p.sentiment_score) AS avg_score,
             count(p) AS post_count
        ORDER BY subreddit, post_count DESC
        RETURN subreddit, label, round(avg_score, 3) AS avg_score, post_count
        """,
        {"entity_name": entity_name},
    )


def get_sentiment_trend_over_time(
    client: Neo4jClient,
    entity_name: str,
    granularity: str = "month",
) -> List[Dict[str, Any]]:
    """
    Sentiment trend over time for an entity (month or week granularity).
    """
    date_trunc = (
        "substring(p.created_utc, 0, 7)"  # YYYY-MM
        if granularity == "month"
        else "substring(p.created_utc, 0, 10)"  # YYYY-MM-DD
    )
    return client.query(
        f"""
        MATCH (p:Post)-[:MENTIONS]->(e:Entity)
        WHERE toLower(e.name) CONTAINS toLower($entity_name)
          AND p.sentiment_score IS NOT NULL
        WITH {date_trunc} AS period,
             avg(p.sentiment_score) AS avg_sentiment,
             count(p) AS post_count
        ORDER BY period
        RETURN period, round(avg_sentiment, 3) AS avg_sentiment, post_count
        """,
        {"entity_name": entity_name},
    )


# ─────────────────────────────────────────────────────────────────────────────
# Problem / pain-point detection
# ─────────────────────────────────────────────────────────────────────────────

def get_negative_posts_by_topic(
    client: Neo4jClient,
    topic_keyword: str,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """
    Find posts with negative sentiment about a topic.

    Example question: "What are problems people are facing with Agentic AI
    knowledge graphs?"
    """
    return client.query(
        """
        MATCH (p:Post)-[:COVERS]->(t:Topic)
        WHERE toLower(t.name) CONTAINS toLower($topic_keyword)
          AND p.sentiment_label IN ['negative', 'mixed']
        RETURN p.id           AS id,
               p.title        AS title,
               p.subreddit    AS subreddit,
               p.score        AS score,
               p.summary      AS summary,
               p.sentiment_score AS sentiment_score,
               p.permalink    AS permalink
        ORDER BY p.sentiment_score ASC, p.score DESC
        LIMIT $limit
        """,
        {"topic_keyword": topic_keyword, "limit": limit},
    )


def get_common_problems_for_entity(
    client: Neo4jClient,
    entity_name: str,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """Return the most-discussed topics in negative posts about an entity."""
    return client.query(
        """
        MATCH (p:Post)-[:MENTIONS]->(e:Entity),
              (p)-[:COVERS]->(t:Topic)
        WHERE toLower(e.name) CONTAINS toLower($entity_name)
          AND p.sentiment_label IN ['negative', 'mixed']
        WITH t.name AS topic, count(p) AS neg_post_count
        ORDER BY neg_post_count DESC
        LIMIT $limit
        RETURN topic, neg_post_count
        """,
        {"entity_name": entity_name, "limit": limit},
    )


# ─────────────────────────────────────────────────────────────────────────────
# Cross-community user tracking
# ─────────────────────────────────────────────────────────────────────────────

def get_cross_community_power_users(
    client: Neo4jClient,
    min_communities: int = 2,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """
    Find users active across multiple tracked communities.

    Example question: "Who is posting/commenting in multiple communities
    we are following?"
    """
    return client.query(
        """
        MATCH (u:User)-[:ACTIVE_IN]->(s:Subreddit)
        WITH u.username AS username,
             collect(s.name) AS communities,
             count(s) AS community_count,
             sum([(u)-[r:ACTIVE_IN]->(s) | r.activity_count][0]) AS total_activity
        WHERE community_count >= $min_communities
        ORDER BY community_count DESC, total_activity DESC
        LIMIT $limit
        RETURN username, communities, community_count, total_activity
        """,
        {"min_communities": min_communities, "limit": limit},
    )


def get_user_activity_profile(
    client: Neo4jClient,
    username: str,
) -> List[Dict[str, Any]]:
    """Return a detailed activity profile for a specific user."""
    return client.query(
        """
        MATCH (u:User {username: $username})
        OPTIONAL MATCH (u)-[:ACTIVE_IN]->(s:Subreddit)
        OPTIONAL MATCH (u)-[:POSTED]->(p:Post)
        OPTIONAL MATCH (u)-[:COMMENTED]->(c:Comment)
        RETURN u.username AS username,
               collect(DISTINCT s.name) AS subreddits,
               count(DISTINCT p) AS post_count,
               count(DISTINCT c) AS comment_count
        """,
        {"username": username},
    )


# ─────────────────────────────────────────────────────────────────────────────
# Trending topics
# ─────────────────────────────────────────────────────────────────────────────

def get_trending_topics(
    client: Neo4jClient,
    days: int = 30,
    subreddit: Optional[str] = None,
    limit: int = 15,
) -> List[Dict[str, Any]]:
    """Return the most-discussed topics in the last N days."""
    subreddit_filter = "AND p.subreddit = toLower($subreddit)" if subreddit else ""
    cutoff = f"datetime() - duration('P{days}D')"
    return client.query(
        f"""
        MATCH (p:Post)-[:COVERS]->(t:Topic)
        WHERE datetime(p.created_utc) > {cutoff}
        {subreddit_filter}
        WITH t.name AS topic, count(p) AS post_count,
             avg(p.score) AS avg_score
        ORDER BY post_count DESC
        LIMIT $limit
        RETURN topic, post_count, round(avg_score, 1) AS avg_score
        """,
        {"subreddit": subreddit, "limit": limit},
    )


def get_trending_entities(
    client: Neo4jClient,
    days: int = 30,
    entity_type: Optional[str] = None,
    limit: int = 15,
) -> List[Dict[str, Any]]:
    """Return the most-mentioned entities in the last N days."""
    type_filter = "AND e.type = $entity_type" if entity_type else ""
    cutoff = f"datetime() - duration('P{days}D')"
    return client.query(
        f"""
        MATCH (p:Post)-[r:MENTIONS]->(e:Entity)
        WHERE datetime(p.created_utc) > {cutoff}
        {type_filter}
        WITH e.name AS entity, e.type AS type,
             count(p) AS post_count, sum(r.mentions) AS total_mentions
        ORDER BY total_mentions DESC
        LIMIT $limit
        RETURN entity, type, post_count, total_mentions
        """,
        {"entity_type": entity_type, "limit": limit},
    )


# ─────────────────────────────────────────────────────────────────────────────
# Full-text search
# ─────────────────────────────────────────────────────────────────────────────

def fulltext_search_posts(
    client: Neo4jClient,
    query_string: str,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """
    Full-text search over post titles and bodies using the Neo4j FTS index.
    """
    return client.query(
        """
        CALL db.index.fulltext.queryNodes('post_fulltext', $query)
        YIELD node AS p, score
        RETURN p.id        AS id,
               p.title     AS title,
               p.subreddit AS subreddit,
               p.score     AS reddit_score,
               p.summary   AS summary,
               p.permalink AS permalink,
               round(score, 3) AS relevance_score
        ORDER BY relevance_score DESC
        LIMIT $limit
        """,
        {"query": query_string, "limit": limit},
    )


# ─────────────────────────────────────────────────────────────────────────────
# Graph statistics
# ─────────────────────────────────────────────────────────────────────────────

def get_graph_stats(client: Neo4jClient) -> Dict[str, int]:
    """Return high-level node and relationship counts for the knowledge graph."""
    results = client.query(
        """
        MATCH (p:Post)    WITH count(p) AS posts
        MATCH (c:Comment) WITH posts, count(c) AS comments
        MATCH (u:User)    WITH posts, comments, count(u) AS users
        MATCH (e:Entity)  WITH posts, comments, users, count(e) AS entities
        MATCH (t:Topic)   WITH posts, comments, users, entities, count(t) AS topics
        MATCH (s:Subreddit) WITH posts, comments, users, entities, topics, count(s) AS subreddits
        RETURN posts, comments, users, entities, topics, subreddits
        """
    )
    return results[0] if results else {}
