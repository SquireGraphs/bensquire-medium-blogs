"""
test_ingestion.py
─────────────────
Unit tests for the ingestion layer.

Tests use mocked PRAW objects — no real Reddit API calls are made.
Run with: pytest tests/test_ingestion.py -v
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.ingestion.models import RedditComment, RedditPost, SubredditMeta
from src.ingestion.scraper import RedditScraper


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_reddit():
    """Return a MagicMock simulating a praw.Reddit instance."""
    return MagicMock()


@pytest.fixture
def scraper(mock_reddit):
    """Return a RedditScraper using a mock Reddit instance."""
    with patch("src.ingestion.scraper.settings") as mock_settings:
        mock_settings.target_subreddits = ["neo4j"]
        mock_settings.max_posts_per_subreddit = 10
        mock_settings.max_comments_per_post = 5
        mock_settings.lookback_months = 36
        mock_settings.keywords_lower = ["neo4j", "graph database"]
        return RedditScraper(mock_reddit)


def _make_submission(
    post_id: str = "abc123",
    title: str = "How to use Neo4j with Python",
    selftext: str = "I love graph databases",
    score: int = 100,
    created_offset: int = 0,  # seconds from now
) -> MagicMock:
    """Helper to build a mock PRAW submission."""
    sub = MagicMock()
    sub.id = post_id
    sub.title = title
    sub.selftext = selftext
    sub.url = f"https://reddit.com/r/neo4j/comments/{post_id}"
    sub.permalink = f"/r/neo4j/comments/{post_id}/test_post/"
    sub.score = score
    sub.upvote_ratio = 0.95
    sub.num_comments = 5
    sub.link_flair_text = None
    sub.is_self = True
    sub.author = MagicMock()
    sub.author.name = "test_user"
    # Recent post (within 3 year window)
    from datetime import datetime, timezone
    sub.created_utc = (datetime.now(tz=timezone.utc).timestamp() - created_offset)
    sub.comments = MagicMock()
    sub.comments.__getitem__ = MagicMock(return_value=[])
    sub.comments.replace_more = MagicMock()
    sub.comments.__iter__ = MagicMock(return_value=iter([]))
    return sub


# ─────────────────────────────────────────────────────────────────────────────
# RedditPost model tests
# ─────────────────────────────────────────────────────────────────────────────

class TestRedditPostModel:
    def test_post_creation(self):
        """RedditPost can be created with all required fields."""
        post = RedditPost(
            id="test123",
            subreddit="neo4j",
            title="Test Post",
            url="https://reddit.com/test",
            permalink="https://reddit.com/r/neo4j/test",
            created_utc=datetime.now(tz=timezone.utc),
        )
        assert post.id == "test123"
        assert post.subreddit == "neo4j"
        assert post.comments == []

    def test_post_defaults(self):
        """RedditPost has sensible defaults for optional fields."""
        post = RedditPost(
            id="x",
            subreddit="neo4j",
            title="T",
            url="http://x.com",
            permalink="http://x.com/p",
            created_utc=datetime.now(tz=timezone.utc),
        )
        assert post.score == 0
        assert post.upvote_ratio == 0.0
        assert post.author is None
        assert post.body == ""


class TestRedditCommentModel:
    def test_comment_creation(self):
        """RedditComment can be created with required fields."""
        comment = RedditComment(
            id="c1",
            post_id="p1",
            parent_id="p1",
            body="This is a great post about Neo4j!",
            created_utc=datetime.now(tz=timezone.utc),
        )
        assert comment.id == "c1"
        assert comment.is_top_level is True

    def test_nested_comment(self):
        """Nested comments have is_top_level=False."""
        comment = RedditComment(
            id="c2",
            post_id="p1",
            parent_id="c1",
            body="Reply",
            created_utc=datetime.now(tz=timezone.utc),
            depth=1,
            is_top_level=False,
        )
        assert comment.depth == 1
        assert comment.is_top_level is False


# ─────────────────────────────────────────────────────────────────────────────
# Scraper keyword filtering tests
# ─────────────────────────────────────────────────────────────────────────────

class TestKeywordFiltering:
    def test_post_with_keyword_in_title_matches(self, scraper):
        """A post whose title contains a keyword should match."""
        post = RedditPost(
            id="1",
            subreddit="neo4j",
            title="Best practices for Neo4j schema design",
            url="https://r.com",
            permalink="https://r.com/p",
            created_utc=datetime.now(tz=timezone.utc),
        )
        assert scraper._post_matches_keywords(post) is True

    def test_post_with_keyword_in_body_matches(self, scraper):
        """A post whose body contains a keyword should match."""
        post = RedditPost(
            id="2",
            subreddit="dataengineering",
            title="Pipeline tools comparison",
            body="We've been evaluating graph database options for our team.",
            url="https://r.com",
            permalink="https://r.com/p",
            created_utc=datetime.now(tz=timezone.utc),
        )
        assert scraper._post_matches_keywords(post) is True

    def test_post_without_keyword_does_not_match(self, scraper):
        """A post with no relevant keywords should not match."""
        post = RedditPost(
            id="3",
            subreddit="analytics",
            title="Tableau dashboard tips",
            body="Here are my top 10 Tableau tips for 2024.",
            url="https://r.com",
            permalink="https://r.com/p",
            created_utc=datetime.now(tz=timezone.utc),
        )
        assert scraper._post_matches_keywords(post) is False

    def test_keyword_match_is_case_insensitive(self, scraper):
        """Keyword matching should be case-insensitive."""
        post = RedditPost(
            id="4",
            subreddit="neo4j",
            title="NEO4J IS AMAZING",
            url="https://r.com",
            permalink="https://r.com/p",
            created_utc=datetime.now(tz=timezone.utc),
        )
        assert scraper._post_matches_keywords(post) is True

    def test_keyword_match_in_comment(self, scraper):
        """A post that only matches via a comment body should qualify."""
        post = RedditPost(
            id="5",
            subreddit="dataengineering",
            title="Weekly discussion thread",
            body="Share what you're working on.",
            url="https://r.com",
            permalink="https://r.com/p",
            created_utc=datetime.now(tz=timezone.utc),
            comments=[
                RedditComment(
                    id="c1",
                    post_id="5",
                    parent_id="5",
                    body="I've been using Neo4j for a recommendation engine.",
                    created_utc=datetime.now(tz=timezone.utc),
                )
            ],
        )
        assert scraper._post_matches_keywords(post) is True


# ─────────────────────────────────────────────────────────────────────────────
# Cutoff date tests
# ─────────────────────────────────────────────────────────────────────────────

class TestCutoffDate:
    def test_cutoff_is_approximately_lookback_months_ago(self, scraper):
        """The cutoff date should be roughly lookback_months * 30 days ago."""
        from datetime import timedelta
        cutoff = scraper._cutoff_utc
        now = datetime.now(tz=timezone.utc)
        # Should be between 35*30 and 37*30 days ago (allowing for leap years)
        expected_min = now - timedelta(days=37 * 30)
        expected_max = now - timedelta(days=35 * 30)
        assert expected_min < cutoff < expected_max
