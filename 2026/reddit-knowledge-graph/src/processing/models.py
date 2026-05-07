"""
models.py  (processing layer)
──────────────────────────────
Pydantic models representing the output of Claude's NLP analysis.

These are the enriched versions of raw Reddit data — they carry extracted
entities, topics, and sentiment scores that get written into Neo4j.
"""

from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class SentimentLabel(str, Enum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"
    MIXED = "mixed"


class EntityType(str, Enum):
    TECHNOLOGY = "technology"      # e.g. Neo4j, Spark, dbt
    CONCEPT = "concept"            # e.g. graph RAG, vector search
    COMPANY = "company"            # e.g. Databricks, Snowflake
    PERSON = "person"              # e.g. developer names, authors
    PRODUCT = "product"            # e.g. Aura, ArangoDB
    FRAMEWORK = "framework"        # e.g. LangChain, LlamaIndex
    LANGUAGE = "language"          # e.g. Python, Cypher
    OTHER = "other"


class ExtractedEntity(BaseModel):
    """A named entity extracted from a post or comment."""

    name: str = Field(..., description="Canonical entity name (title-cased)")
    type: EntityType = Field(..., description="Category of the entity")
    mentions: int = Field(default=1, description="How many times this entity was mentioned in the text")
    context: Optional[str] = Field(
        default=None,
        description="Short (≤20 word) snippet showing the entity in context",
    )


class TopicTag(BaseModel):
    """A high-level topic label assigned to a post or comment."""

    name: str = Field(..., description="Short topic label, e.g. 'graph RAG', 'performance tuning'")
    relevance: float = Field(
        ..., ge=0.0, le=1.0, description="Relevance score 0–1"
    )


class SentimentResult(BaseModel):
    """Sentiment analysis result for a single piece of text."""

    label: SentimentLabel
    score: float = Field(..., ge=-1.0, le=1.0, description="Score: -1 very negative → +1 very positive")
    reasoning: Optional[str] = Field(
        default=None, description="1-2 sentence explanation from Claude"
    )


class EnrichedContent(BaseModel):
    """
    The full NLP enrichment result for a post or comment.

    Produced by `EntityExtractor.enrich()` and passed to the graph ingester.
    """

    content_id: str              # Reddit post or comment ID
    content_type: str            # "post" or "comment"
    entities: List[ExtractedEntity] = Field(default_factory=list)
    topics: List[TopicTag] = Field(default_factory=list)
    sentiment: Optional[SentimentResult] = None
    summary: Optional[str] = Field(
        default=None,
        description="1-3 sentence plain-language summary of the content (posts only)",
    )
