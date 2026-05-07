"""
test_graph.py
─────────────
Unit tests for the graph layer — schema and ingester.

Uses a mock Neo4jClient rather than a real database connection.
Run with: pytest tests/test_graph.py -v
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, call, patch

import pytest

from src.graph.ingester import GraphIngester
from src.ingestion.models import RedditComment, RedditPost, SubredditMeta
from src.processing.models import (
    EnrichedContent,
    EntityType,
    ExtractedEntity,
    SentimentLabel,
    SentimentResult,
    TopicTag,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_client():
    """Return a mock Neo4jClient."""
    client = MagicMock()
    client.query.return_value = []
    return client


@pytest.fixture
def ingester(mock_client):
    """Return a GraphIngester with a mock client."""
    return GraphIngester(client=mock_client)


@pytest.fixture
def sample_post():
    return RedditPost(
        id="post1",
        subreddit="neo4j",
        title="Graph RAG with Neo4j",
        body="Building a graph RAG system.",
        url="https://reddit.com/p1",
        permalink="https://reddit.com/r/neo4j/p1",
        author="alice",
        score=150,
        upvote_ratio=0.98,
        num_comments=10,
        created_utc=datetime.now(tz=timezone.utc),
    )


@pytest.fixture
def sample_comment():
    return RedditComment(
        id="comment1",
        post_id="post1",
        parent_id="post1",
        author="bob",
        body="Neo4j makes this much easier.",
        score=25,
        created_utc=datetime.now(tz=timezone.utc),
        depth=0,
        is_top_level=True,
    )


@pytest.fixture
def sample_enrichment():
    return EnrichedContent(
        content_id="post1",
        content_type="post",
        entities=[
            ExtractedEntity(name="Neo4j", type=EntityType.TECHNOLOGY, mentions=2),
            ExtractedEntity(name="LangChain", type=EntityType.FRAMEWORK, mentions=1),
        ],
        topics=[
            TopicTag(name="graph RAG", relevance=0.9),
        ],
        sentiment=SentimentResult(
            label=SentimentLabel.POSITIVE,
            score=0.8,
            reasoning="Very positive about the technology.",
        ),
        summary="Building a graph RAG system with Neo4j.",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Subreddit ingestion tests
# ─────────────────────────────────────────────────────────────────────────────

class TestSubredditIngestion:
    def test_upsert_subreddit_calls_query(self, ingester, mock_client):
        """upsert_subreddit should call client.query exactly once."""
        meta = SubredditMeta(
            name="neo4j",
            display_name="r/neo4j",
            subscribers=12000,
        )
        ingester.upsert_subreddit(meta)
        mock_client.query.assert_called_once()

    def test_upsert_subreddit_passes_correct_name(self, ingester, mock_client):
        """Subreddit name should be lowercased in the query parameters."""
        meta = SubredditMeta(name="Neo4j", display_name="r/Neo4j")
        ingester.upsert_subreddit(meta)
        _, kwargs_or_args = mock_client.query.call_args[0], mock_client.query.call_args
        params = mock_client.query.call_args[0][1]  # Second positional arg = params dict
        assert params["name"] == "neo4j"  # Should be lowercased


# ─────────────────────────────────────────────────────────────────────────────
# Post ingestion tests
# ─────────────────────────────────────────────────────────────────────────────

class TestPostIngestion:
    def test_upsert_post_calls_query(self, ingester, mock_client, sample_post):
        """upsert_post should call the Neo4j client."""
        ingester.upsert_post(sample_post)
        assert mock_client.query.call_count >= 1

    def test_upsert_post_with_author_links_user(self, ingester, mock_client, sample_post):
        """A post with an author should trigger user creation and POSTED link."""
        ingester.upsert_post(sample_post)
        # Should have been called multiple times: post MERGE, user MERGE, POSTED edge
        assert mock_client.query.call_count >= 3

    def test_upsert_post_without_author_does_not_link_user(self, ingester, mock_client):
        """A post with no author should not trigger user creation."""
        post = RedditPost(
            id="post_no_author",
            subreddit="neo4j",
            title="Anonymous Post",
            url="https://r.com",
            permalink="https://r.com/p",
            author=None,
            created_utc=datetime.now(tz=timezone.utc),
        )
        ingester.upsert_post(post)
        # Only the post MERGE should have been called (1 call)
        assert mock_client.query.call_count == 1


# ─────────────────────────────────────────────────────────────────────────────
# Enrichment ingestion tests
# ─────────────────────────────────────────────────────────────────────────────

class TestEnrichmentIngestion:
    def test_apply_enrichment_writes_sentiment(self, ingester, mock_client, sample_enrichment):
        """apply_enrichment should write sentiment properties."""
        ingester.apply_enrichment(sample_enrichment)
        # Find the call that writes sentiment
        calls_str = str(mock_client.query.call_args_list)
        assert "sentiment_label" in calls_str or "sentiment_score" in calls_str

    def test_apply_enrichment_creates_entity_nodes(self, ingester, mock_client, sample_enrichment):
        """apply_enrichment should create Entity nodes for each extracted entity."""
        ingester.apply_enrichment(sample_enrichment)
        # 2 entities + 1 co-occurrence + 1 topic + 1 sentiment + 1 summary = multiple calls
        assert mock_client.query.call_count >= 4

    def test_apply_enrichment_with_no_sentiment(self, ingester, mock_client):
        """apply_enrichment should handle enrichment with no sentiment gracefully."""
        enrichment = EnrichedContent(
            content_id="post2",
            content_type="post",
            entities=[],
            topics=[],
            sentiment=None,
        )
        ingester.apply_enrichment(enrichment)  # Should not raise


# ─────────────────────────────────────────────────────────────────────────────
# User tracking tests
# ─────────────────────────────────────────────────────────────────────────────

class TestUserTracking:
    def test_upsert_user_calls_query(self, ingester, mock_client):
        """upsert_user should call the client with the username."""
        ingester.upsert_user("alice")
        mock_client.query.assert_called_once()
        params = mock_client.query.call_args[0][1]
        assert params["username"] == "alice"

    def test_link_user_to_subreddit_increments_activity(self, ingester, mock_client):
        """link_user_to_subreddit should trigger an ACTIVE_IN MERGE."""
        ingester.link_user_to_subreddit("alice", "neo4j")
        mock_client.query.assert_called_once()
        cypher = mock_client.query.call_args[0][0]
        assert "ACTIVE_IN" in cypher
