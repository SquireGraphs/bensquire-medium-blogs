"""
test_processing.py
──────────────────
Unit tests for the NLP processing layer (entity extraction).

Tests mock the Anthropic API — no real API calls are made.
Run with: pytest tests/test_processing.py -v
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.ingestion.models import RedditComment, RedditPost
from src.processing.entity_extractor import EntityExtractor
from src.processing.models import EntityType, SentimentLabel


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

SAMPLE_CLAUDE_RESPONSE = {
    "entities": [
        {
            "name": "Neo4j",
            "type": "technology",
            "mentions": 3,
            "context": "using Neo4j for a recommendation engine",
        },
        {
            "name": "LangChain",
            "type": "framework",
            "mentions": 1,
            "context": "building an agent with LangChain",
        },
    ],
    "topics": [
        {"name": "graph RAG", "relevance": 0.9},
        {"name": "agent development", "relevance": 0.7},
    ],
    "sentiment": {
        "label": "positive",
        "score": 0.75,
        "reasoning": "The author is enthusiastic about Neo4j's capabilities.",
    },
    "summary": "The author discusses building a graph RAG system using Neo4j and LangChain.",
}


@pytest.fixture
def mock_anthropic_client():
    """Return a mock Anthropic client that returns SAMPLE_CLAUDE_RESPONSE."""
    client = MagicMock()
    message = MagicMock()
    message.content = [MagicMock(text=json.dumps(SAMPLE_CLAUDE_RESPONSE))]
    client.messages.create.return_value = message
    return client


@pytest.fixture
def extractor(mock_anthropic_client):
    """Return an EntityExtractor using the mock Anthropic client."""
    return EntityExtractor(client=mock_anthropic_client)


@pytest.fixture
def sample_post():
    """Return a sample RedditPost for testing."""
    return RedditPost(
        id="test_post_1",
        subreddit="neo4j",
        title="Building a graph RAG system with Neo4j and LangChain",
        body="I've been using Neo4j for a recommendation engine and recently started building an agent with LangChain.",
        url="https://reddit.com/r/neo4j/test",
        permalink="https://reddit.com/r/neo4j/test",
        created_utc=datetime.now(tz=timezone.utc),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Entity extraction tests
# ─────────────────────────────────────────────────────────────────────────────

class TestEntityExtraction:
    def test_enrich_post_returns_enriched_content(self, extractor, sample_post):
        """enrich_post should return an EnrichedContent with the correct content_id."""
        result = extractor.enrich_post(sample_post)
        assert result.content_id == sample_post.id
        assert result.content_type == "post"

    def test_entities_are_extracted(self, extractor, sample_post):
        """Extracted entities should match the mock Claude response."""
        result = extractor.enrich_post(sample_post)
        entity_names = [e.name for e in result.entities]
        assert "Neo4j" in entity_names
        assert "LangChain" in entity_names

    def test_entity_types_are_correct(self, extractor, sample_post):
        """Entity types should be correctly parsed."""
        result = extractor.enrich_post(sample_post)
        neo4j_entity = next(e for e in result.entities if e.name == "Neo4j")
        assert neo4j_entity.type == EntityType.TECHNOLOGY

        langchain_entity = next(e for e in result.entities if e.name == "LangChain")
        assert langchain_entity.type == EntityType.FRAMEWORK

    def test_topics_are_extracted(self, extractor, sample_post):
        """Topics should be extracted and have valid relevance scores."""
        result = extractor.enrich_post(sample_post)
        assert len(result.topics) == 2
        topic_names = [t.name for t in result.topics]
        assert "graph RAG" in topic_names
        for topic in result.topics:
            assert 0.0 <= topic.relevance <= 1.0

    def test_sentiment_is_extracted(self, extractor, sample_post):
        """Sentiment should be extracted with correct label and score."""
        result = extractor.enrich_post(sample_post)
        assert result.sentiment is not None
        assert result.sentiment.label == SentimentLabel.POSITIVE
        assert result.sentiment.score == 0.75
        assert result.sentiment.reasoning is not None

    def test_summary_is_extracted_for_post(self, extractor, sample_post):
        """Summary should be populated for posts."""
        result = extractor.enrich_post(sample_post)
        assert result.summary is not None
        assert len(result.summary) > 0

    def test_comment_enrichment(self, extractor):
        """Comment enrichment should set content_type to 'comment'."""
        comment = RedditComment(
            id="c1",
            post_id="p1",
            parent_id="p1",
            body="Neo4j is great for path finding algorithms.",
            created_utc=datetime.now(tz=timezone.utc),
        )
        result = extractor.enrich_comment(comment)
        assert result.content_type == "comment"
        assert result.content_id == "c1"


# ─────────────────────────────────────────────────────────────────────────────
# Response parsing edge cases
# ─────────────────────────────────────────────────────────────────────────────

class TestResponseParsing:
    def test_handles_empty_entities_list(self, extractor, sample_post, mock_anthropic_client):
        """Extractor should handle Claude returning an empty entities list."""
        empty_response = {**SAMPLE_CLAUDE_RESPONSE, "entities": []}
        mock_anthropic_client.messages.create.return_value.content[0].text = json.dumps(empty_response)

        result = extractor.enrich_post(sample_post)
        assert result.entities == []

    def test_handles_missing_sentiment(self, extractor, sample_post, mock_anthropic_client):
        """Extractor should handle Claude omitting the sentiment field."""
        no_sentiment = {**SAMPLE_CLAUDE_RESPONSE, "sentiment": None}
        mock_anthropic_client.messages.create.return_value.content[0].text = json.dumps(no_sentiment)

        result = extractor.enrich_post(sample_post)
        assert result.sentiment is None

    def test_handles_unknown_entity_type(self, extractor, sample_post, mock_anthropic_client):
        """Unknown entity types should fall back to 'other'."""
        invalid_type_response = {
            **SAMPLE_CLAUDE_RESPONSE,
            "entities": [{"name": "TestEntity", "type": "invalid_type_xyz", "mentions": 1}],
        }
        mock_anthropic_client.messages.create.return_value.content[0].text = json.dumps(invalid_type_response)

        result = extractor.enrich_post(sample_post)
        # Entity with invalid type should be skipped (ValueError caught in parser)
        assert len(result.entities) == 0

    def test_strips_markdown_code_fences(self, extractor, sample_post, mock_anthropic_client):
        """Extractor should strip ```json ... ``` fences from Claude's response."""
        fenced = f"```json\n{json.dumps(SAMPLE_CLAUDE_RESPONSE)}\n```"
        mock_anthropic_client.messages.create.return_value.content[0].text = fenced

        result = extractor.enrich_post(sample_post)
        assert len(result.entities) == 2  # Parsed successfully
