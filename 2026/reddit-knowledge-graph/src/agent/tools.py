"""
tools.py
────────
LangChain-compatible tool definitions for the Reddit Knowledge Graph agent.

Each tool wraps a function from `src.graph.queries` and exposes it to the
LangGraph agent via a typed `@tool` decorator.

Adding a new tool
─────────────────
1. Write the query function in `src/graph/queries.py`.
2. Add a `@tool` decorated function here that calls it.
3. Add the tool to the `ALL_TOOLS` list at the bottom.
4. Register a description in `src/agent/prompts.py`.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from langchain_core.tools import tool

from src.graph import queries
from src.graph.neo4j_client import get_client

logger = logging.getLogger(__name__)


def _client():
    """Lazily return the Neo4j client singleton."""
    return get_client()


# ─────────────────────────────────────────────────────────────────────────────
# Tool definitions
# ─────────────────────────────────────────────────────────────────────────────

@tool
def search_community_discussions(entity_name: str, limit: int = 10) -> str:
    """
    Find which subreddits discuss a given technology, product, or concept the most.

    Use this tool when asked WHERE discussions about a topic happen.

    Args:
        entity_name: The technology or concept to search for (e.g. 'Neo4j', 'graphRAG').
        limit: Maximum number of communities to return.

    Returns:
        JSON string with subreddit names and mention counts.
    """
    results = queries.get_entity_discussion_by_community(_client(), entity_name, limit)
    return json.dumps(results, indent=2)


@tool
def get_sentiment(entity_name: str) -> str:
    """
    Get overall sentiment breakdown for a technology or concept across all communities.

    Use this when asked 'how do people feel about X' or 'what is the sentiment
    around X'.

    Args:
        entity_name: The entity to analyse sentiment for (e.g. 'Neo4j', 'Agentic AI').

    Returns:
        JSON with sentiment labels (positive/neutral/negative/mixed), average scores,
        and mention counts.
    """
    overall = queries.get_sentiment_summary_for_entity(_client(), entity_name)
    by_community = queries.get_sentiment_by_subreddit(_client(), entity_name)
    return json.dumps({"overall": overall, "by_subreddit": by_community}, indent=2)


@tool
def get_sentiment_trend(entity_name: str, granularity: str = "month") -> str:
    """
    Get sentiment trend over time for a technology or concept.

    Use this when asked how sentiment has changed or evolved over time.

    Args:
        entity_name: The entity to track sentiment for.
        granularity: Time granularity — 'month' (default) or 'week'.

    Returns:
        JSON list of {period, avg_sentiment, post_count} sorted chronologically.
    """
    results = queries.get_sentiment_trend_over_time(_client(), entity_name, granularity)
    return json.dumps(results, indent=2)


@tool
def find_problems(topic_keyword: str, limit: int = 10) -> str:
    """
    Find posts with negative or mixed sentiment about a specific topic.

    Use this when asked 'what problems are people facing with X' or
    'what are the pain points around X'.

    Args:
        topic_keyword: Topic to search for (e.g. 'agentic AI', 'knowledge graph').
        limit: Maximum number of posts to return.

    Returns:
        JSON list of negative/mixed posts with titles, subreddits, and summaries.
    """
    posts = queries.get_negative_posts_by_topic(_client(), topic_keyword, limit)
    common_topics = queries.get_common_problems_for_entity(_client(), topic_keyword)
    return json.dumps({"problem_posts": posts, "common_problem_topics": common_topics}, indent=2)


@tool
def get_cross_community_users(min_communities: int = 2, limit: int = 20) -> str:
    """
    Find users who are active across multiple tracked subreddits.

    Use this when asked about cross-community engagement or to identify
    influential contributors who span multiple communities.

    Args:
        min_communities: Minimum number of communities a user must be active in.
        limit: Maximum number of users to return.

    Returns:
        JSON list of users with their active communities and activity counts.
    """
    results = queries.get_cross_community_power_users(_client(), min_communities, limit)
    return json.dumps(results, indent=2)


@tool
def get_user_profile(username: str) -> str:
    """
    Get the activity profile for a specific Reddit user across all tracked communities.

    Args:
        username: Reddit username (without u/ prefix).

    Returns:
        JSON with the user's active subreddits, post count, and comment count.
    """
    results = queries.get_user_activity_profile(_client(), username)
    return json.dumps(results, indent=2)


@tool
def get_trending_topics(days: int = 30, subreddit: Optional[str] = None, limit: int = 15) -> str:
    """
    Get the most-discussed topics in the knowledge graph over the last N days.

    Use this for 'what's trending', 'what are people talking about', or
    'what topics are popular' questions.

    Args:
        days: Look-back window in days (default 30).
        subreddit: Optional — filter to a specific subreddit (e.g. 'dataengineering').
        limit: Maximum number of topics to return.

    Returns:
        JSON list of topics with post counts and average engagement scores.
    """
    results = queries.get_trending_topics(_client(), days, subreddit, limit)
    return json.dumps(results, indent=2)


@tool
def get_trending_entities(
    days: int = 30, entity_type: Optional[str] = None, limit: int = 15
) -> str:
    """
    Get the most-mentioned technologies, companies, or concepts recently.

    Use this for 'what technologies are getting attention' or 'what's buzzing'
    questions.

    Args:
        days: Look-back window in days (default 30).
        entity_type: Optional filter — one of: technology, concept, company,
                     person, product, framework, language, other.
        limit: Maximum number of entities to return.

    Returns:
        JSON list of entities with mention counts.
    """
    results = queries.get_trending_entities(_client(), days, entity_type, limit)
    return json.dumps(results, indent=2)


@tool
def search_posts(query_string: str, limit: int = 10) -> str:
    """
    Full-text search across Reddit post titles and bodies in the knowledge graph.

    Use this when looking for specific discussions, phrases, or keywords.

    Args:
        query_string: Search terms (supports Lucene syntax for Neo4j FTS).
        limit: Maximum number of posts to return.

    Returns:
        JSON list of matching posts with relevance scores.
    """
    results = queries.fulltext_search_posts(_client(), query_string, limit)
    return json.dumps(results, indent=2)


@tool
def get_top_posts(entity_name: str, subreddit: Optional[str] = None, limit: int = 10) -> str:
    """
    Get the highest-scored posts mentioning a specific entity.

    Args:
        entity_name: Technology or concept to look up.
        subreddit: Optional subreddit filter.
        limit: Maximum posts to return.

    Returns:
        JSON list of top posts with scores, summaries, and permalinks.
    """
    results = queries.get_top_posts_mentioning_entity(_client(), entity_name, subreddit, limit)
    return json.dumps(results, indent=2)


@tool
def run_custom_cypher(cypher: str) -> str:
    """
    Execute a custom read-only Cypher query against the Neo4j knowledge graph.

    Use this ONLY when no other tool covers the required query. The query
    must be a read-only MATCH/RETURN statement. Do NOT use CREATE, MERGE,
    DELETE, or SET.

    Args:
        cypher: A valid Cypher READ query.

    Returns:
        JSON list of result records, or an error message if the query fails.
    """
    if any(kw in cypher.upper() for kw in ("CREATE", "MERGE", "DELETE", "SET", "REMOVE")):
        return json.dumps({"error": "Only read-only queries are permitted via this tool."})
    try:
        results = _client().query(cypher)
        return json.dumps(results, indent=2, default=str)
    except Exception as exc:
        logger.error("Custom Cypher query failed: %s", exc)
        return json.dumps({"error": str(exc)})


@tool
def get_graph_stats() -> str:
    """
    Return overall statistics about the knowledge graph.

    Use this when asked 'how much data do we have' or to give the user a
    high-level overview of the graph contents.

    Returns:
        JSON dict with counts of posts, comments, users, entities, topics, subreddits.
    """
    results = queries.get_graph_stats(_client())
    return json.dumps(results, indent=2)


# ─────────────────────────────────────────────────────────────────────────────
# Tool registry  — import this list into graph_agent.py
# ─────────────────────────────────────────────────────────────────────────────

ALL_TOOLS = [
    search_community_discussions,
    get_sentiment,
    get_sentiment_trend,
    find_problems,
    get_cross_community_users,
    get_user_profile,
    get_trending_topics,
    get_trending_entities,
    search_posts,
    get_top_posts,
    run_custom_cypher,
    get_graph_stats,
]
