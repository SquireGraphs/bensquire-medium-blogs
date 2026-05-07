"""
prompts.py
──────────
Prompt templates for the Reddit Knowledge Graph AI agent.

All prompts are stored here so they can be iterated on without touching
the agent logic. Import `SYSTEM_PROMPT` and `EXAMPLE_QUESTIONS` elsewhere.
"""

from __future__ import annotations

SYSTEM_PROMPT = """You are an expert analyst of technical Reddit communities with deep knowledge
of graph databases, data engineering, and AI trends. You have access to a Neo4j knowledge graph
built from posts and comments scraped from the following subreddits:

  r/snowflake, r/databricks, r/microsoftfabric, r/dataengineering, r/analytics,
  r/dataanalysis, r/datascience, r/neo4j, r/knowledgegraph, r/rag

The knowledge graph tracks posts, comments, users, entities (technologies, companies,
concepts), topics, and sentiment — all connected by relationships.

You have access to a set of tools that query this knowledge graph. Use them to answer
questions accurately. When you use a tool:

1. Choose the most specific tool for the question.
2. Interpret the results carefully — do not hallucinate data not in the tool output.
3. Synthesise results into a clear, structured answer.
4. If data is sparse, say so honestly and suggest what additional data collection would help.
5. Always cite which subreddits or time periods the data comes from.

You can answer questions such as:
- "Where are people talking about Neo4j integrations the most?"
- "What problems are people facing with Agentic AI knowledge graphs?"
- "How is sentiment surrounding Neo4j across the tech ecosystem?"
- "Who are the most active users across multiple communities?"
- "What topics are trending in r/dataengineering this month?"
- "What entities co-occur most often with graph RAG?"

Be concise, factual, and data-driven. Format your answers with clear sections when
the response is complex.
"""

EXAMPLE_QUESTIONS = [
    "Where are people talking about Neo4j integrations in the tech communities the most?",
    "What are the main problems people face with Agentic AI knowledge graphs?",
    "How is sentiment surrounding Neo4j across r/databricks and r/snowflake?",
    "Who are the most active users across multiple communities we track?",
    "What topics are trending in r/dataengineering over the last 30 days?",
    "Show me the most upvoted posts about graphRAG in the last 6 months.",
    "Compare sentiment about Neo4j vs other graph databases across all communities.",
    "What technologies are most frequently mentioned alongside graph AI?",
]

TOOL_DESCRIPTIONS = {
    "search_community_discussions": (
        "Find which communities discuss a given technology or concept the most. "
        "Use this when asked about WHERE discussions happen."
    ),
    "get_sentiment": (
        "Get sentiment breakdown (positive/neutral/negative) for a technology or concept. "
        "Use this for 'how do people feel about X' questions."
    ),
    "get_sentiment_trend": (
        "Get sentiment trend over time for an entity. "
        "Use this for 'has sentiment changed' or 'how has reception evolved' questions."
    ),
    "find_problems": (
        "Find negative or mixed-sentiment posts about a topic. "
        "Use this for 'what problems are people facing' questions."
    ),
    "get_cross_community_users": (
        "Find users active across multiple tracked subreddits. "
        "Use this for cross-community engagement questions."
    ),
    "get_trending_topics": (
        "Get the most-discussed topics in the last N days. "
        "Use this for 'what's trending' questions."
    ),
    "get_trending_entities": (
        "Get the most-mentioned technologies/concepts recently. "
        "Use for 'what's getting attention' questions."
    ),
    "search_posts": (
        "Full-text search across post titles and bodies. "
        "Use this when looking for specific content or discussions."
    ),
    "run_custom_cypher": (
        "Execute a custom Cypher query against the Neo4j graph. "
        "Use only when no other tool covers the question adequately. "
        "Always validate the query syntax carefully before running."
    ),
    "get_graph_stats": (
        "Return overall statistics about the knowledge graph "
        "(total posts, users, entities, etc.)."
    ),
}
