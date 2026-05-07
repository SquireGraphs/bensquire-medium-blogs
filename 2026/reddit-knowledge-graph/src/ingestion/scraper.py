"""
scraper.py
──────────
Keyword-filtered Reddit scraper built on top of PRAW.

Design
──────
- Iterates through `settings.target_subreddits`.
- For each subreddit fetches the newest posts up to `settings.max_posts_per_subreddit`.
- Filters posts to those created within `settings.lookback_months` months.
- Keeps a post (and its comments) only if at least one configured keyword
  appears in the post title, body, OR any top-level comment body (case-
  insensitive).
- Returns structured `RedditPost` objects (with nested `RedditComment` objects).

Rate limiting
─────────────
PRAW automatically handles Reddit's burst rate limits. We add a small
configurable sleep between subreddits to be polite and avoid 429s during
large back-fills.  See `INTER_SUBREDDIT_SLEEP_SECONDS`.

Usage
─────
    from src.ingestion.scraper import RedditScraper
    from src.ingestion.reddit_client import get_reddit

    scraper = RedditScraper(get_reddit())
    posts = scraper.scrape_all()
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Generator, List, Optional

import praw
import praw.models
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.config import settings
from src.ingestion.models import RedditComment, RedditPost, RedditUser, SubredditMeta

logger = logging.getLogger(__name__)

# Seconds to sleep between subreddits during a full scrape pass.
# At 60 req/min authenticated, this helps avoid burst limits on large runs.
INTER_SUBREDDIT_SLEEP_SECONDS = 2.0

# Maximum comment-tree depth to traverse (Reddit can be deeply nested)
MAX_COMMENT_DEPTH = 3


class RedditScraper:
    """
    Fetches, filters, and structures Reddit posts and comments.

    Parameters
    ----------
    reddit : praw.Reddit
        An authenticated or read-only PRAW Reddit instance.
    """

    def __init__(self, reddit: praw.Reddit) -> None:
        self.reddit = reddit
        self._cutoff_utc: datetime = self._compute_cutoff()
        self._keywords: List[str] = settings.keywords_lower
        logger.info(
            "RedditScraper initialised | cutoff=%s | keywords=%s",
            self._cutoff_utc.date(),
            self._keywords,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────────────

    def scrape_all(self) -> List[RedditPost]:
        """
        Scrape all configured subreddits and return filtered posts.

        Returns
        -------
        List[RedditPost]
            All keyword-matching posts from all configured subreddits.
        """
        all_posts: List[RedditPost] = []

        for idx, subreddit_name in enumerate(settings.target_subreddits):
            logger.info(
                "Scraping r/%s (%d/%d)...",
                subreddit_name,
                idx + 1,
                len(settings.target_subreddits),
            )
            try:
                posts = list(self._scrape_subreddit(subreddit_name))
                all_posts.extend(posts)
                logger.info("  → %d qualifying posts from r/%s", len(posts), subreddit_name)
            except Exception as exc:
                logger.error("Failed to scrape r/%s: %s", subreddit_name, exc, exc_info=True)

            # Be polite between subreddits
            if idx < len(settings.target_subreddits) - 1:
                time.sleep(INTER_SUBREDDIT_SLEEP_SECONDS)

        logger.info("Scrape complete. Total qualifying posts: %d", len(all_posts))
        return all_posts

    def get_subreddit_meta(self, subreddit_name: str) -> SubredditMeta:
        """
        Fetch basic metadata for a subreddit.

        Parameters
        ----------
        subreddit_name : str
            Subreddit name without the r/ prefix.

        Returns
        -------
        SubredditMeta
        """
        sub = self.reddit.subreddit(subreddit_name)
        return SubredditMeta(
            name=sub.display_name,
            display_name=f"r/{sub.display_name}",
            subscribers=sub.subscribers or 0,
            description=sub.public_description or "",
            created_utc=datetime.fromtimestamp(sub.created_utc, tz=timezone.utc)
            if sub.created_utc
            else None,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _compute_cutoff(self) -> datetime:
        """Return the UTC datetime `lookback_months` months ago."""
        now = datetime.now(tz=timezone.utc)
        # timedelta doesn't support months; approximate as 30 days per month
        return now - timedelta(days=settings.lookback_months * 30)

    def _scrape_subreddit(self, subreddit_name: str) -> Generator[RedditPost, None, None]:
        """
        Yield keyword-matching RedditPost objects from a single subreddit.

        Iterates over the subreddit's 'new' listing (most recent first) and
        stops once posts are older than the cutoff date.
        """
        subreddit = self.reddit.subreddit(subreddit_name)

        fetched = 0
        for submission in self._fetch_submissions(subreddit):
            # Stop if we've exceeded the per-subreddit limit
            if fetched >= settings.max_posts_per_subreddit:
                break

            created = datetime.fromtimestamp(submission.created_utc, tz=timezone.utc)

            # Stop iterating once posts are older than our cutoff
            if created < self._cutoff_utc:
                logger.debug("Reached cutoff for r/%s, stopping.", subreddit_name)
                break

            fetched += 1

            # Parse the submission into a RedditPost (comments not yet loaded)
            post = self._parse_submission(submission, subreddit_name)

            # Load comments
            post.comments = self._fetch_comments(submission, post.id)

            # Only keep posts that mention at least one keyword
            if self._post_matches_keywords(post):
                yield post

    @retry(
        retry=retry_if_exception_type(Exception),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def _fetch_submissions(
        self, subreddit: praw.models.Subreddit
    ) -> praw.models.listing.generator.ListingGenerator:
        """
        Return a PRAW listing generator for new submissions.

        Wrapped in tenacity retry logic for transient network/API errors.
        """
        return subreddit.new(limit=settings.max_posts_per_subreddit)

    def _parse_submission(
        self, submission: praw.models.Submission, subreddit_name: str
    ) -> RedditPost:
        """Convert a PRAW Submission into a RedditPost model."""
        author_name: Optional[str] = None
        try:
            author_name = submission.author.name if submission.author else None
        except Exception:
            pass  # Account suspended / deleted

        return RedditPost(
            id=submission.id,
            subreddit=subreddit_name.lower(),
            title=submission.title or "",
            body=submission.selftext or "",
            url=submission.url or "",
            permalink=f"https://www.reddit.com{submission.permalink}",
            author=author_name,
            score=submission.score or 0,
            upvote_ratio=submission.upvote_ratio or 0.0,
            num_comments=submission.num_comments or 0,
            flair=submission.link_flair_text,
            created_utc=datetime.fromtimestamp(submission.created_utc, tz=timezone.utc),
            is_self=submission.is_self,
        )

    def _fetch_comments(
        self, submission: praw.models.Submission, post_id: str
    ) -> List[RedditComment]:
        """
        Fetch and parse top-level comments for a submission.

        We call `replace_more(limit=0)` to skip "load more comments" stubs
        and only get immediately available comments, keeping API cost low.
        """
        comments: List[RedditComment] = []
        try:
            submission.comments.replace_more(limit=0)
            for comment in submission.comments[:settings.max_comments_per_post]:
                parsed = self._parse_comment(comment, post_id, depth=0)
                if parsed:
                    comments.append(parsed)
        except Exception as exc:
            logger.warning("Could not fetch comments for post %s: %s", post_id, exc)

        return comments

    def _parse_comment(
        self,
        comment: praw.models.Comment,
        post_id: str,
        depth: int,
    ) -> Optional[RedditComment]:
        """Convert a PRAW Comment to a RedditComment model."""
        if depth > MAX_COMMENT_DEPTH:
            return None
        if not isinstance(comment, praw.models.Comment):
            return None  # Skip MoreComments stubs

        author_name: Optional[str] = None
        try:
            author_name = comment.author.name if comment.author else None
        except Exception:
            pass

        body = getattr(comment, "body", "") or ""
        if body in ("[deleted]", "[removed]", ""):
            return None

        return RedditComment(
            id=comment.id,
            post_id=post_id,
            parent_id=comment.parent_id.split("_", 1)[-1],  # strip "t1_" / "t3_" prefix
            author=author_name,
            body=body,
            score=comment.score or 0,
            created_utc=datetime.fromtimestamp(comment.created_utc, tz=timezone.utc),
            depth=depth,
            permalink=f"https://www.reddit.com{comment.permalink}" if comment.permalink else "",
            is_top_level=(depth == 0),
        )

    def _post_matches_keywords(self, post: RedditPost) -> bool:
        """
        Return True if any keyword appears in the post title, body, or any comment.

        Matching is case-insensitive.
        """
        # Combine all searchable text
        text_sources = [post.title.lower(), post.body.lower()]
        text_sources += [c.body.lower() for c in post.comments]

        combined = " ".join(text_sources)
        return any(keyword in combined for keyword in self._keywords)
