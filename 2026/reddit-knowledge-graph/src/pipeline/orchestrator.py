"""
orchestrator.py
───────────────
The main pipeline orchestrator that ties all layers together:

    Reddit (PRAW)  →  Scraper  →  EntityExtractor  →  GraphIngester  →  Neo4j

Run order
─────────
1. Seed subreddit metadata nodes.
2. Scrape posts (keyword-filtered, date-bounded).
3. For each post:
   a. Extract entities + topics + sentiment from the post.
   b. Extract entities + sentiment from each comment.
   c. Write post, comments, and enrichments to Neo4j.
4. Log a completion summary.

The pipeline is designed to be:
- **Idempotent**: Re-running for the same data only updates existing nodes.
- **Resumable**: Each post is committed independently; a crash mid-run
  loses only the current post (not all previous work).
- **Observable**: Rich logging at each stage; progress bars via tqdm.

Usage
─────
    from src.pipeline.orchestrator import Pipeline
    Pipeline().run()
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import List

from tqdm import tqdm

from src.config import settings
from src.graph.ingester import GraphIngester
from src.graph.neo4j_client import Neo4jClient
from src.graph.schema import apply_schema
from src.ingestion.models import RedditPost
from src.ingestion.reddit_client import get_reddit
from src.ingestion.scraper import RedditScraper
from src.processing.entity_extractor import EntityExtractor

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Run statistics
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class PipelineStats:
    """Counts of items processed during a pipeline run."""

    posts_scraped: int = 0
    posts_ingested: int = 0
    posts_failed: int = 0
    comments_ingested: int = 0
    entities_created: int = 0
    start_time: float = field(default_factory=time.time)

    def elapsed_seconds(self) -> float:
        return time.time() - self.start_time

    def summary(self) -> str:
        elapsed = self.elapsed_seconds()
        return (
            f"\n{'─'*55}\n"
            f"  Pipeline run complete\n"
            f"{'─'*55}\n"
            f"  Posts scraped   : {self.posts_scraped}\n"
            f"  Posts ingested  : {self.posts_ingested}\n"
            f"  Posts failed    : {self.posts_failed}\n"
            f"  Comments written: {self.comments_ingested}\n"
            f"  Duration        : {elapsed:.1f}s\n"
            f"{'─'*55}\n"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline
# ─────────────────────────────────────────────────────────────────────────────

class Pipeline:
    """
    End-to-end Reddit → Neo4j knowledge graph pipeline.

    Parameters
    ----------
    neo4j_client : Neo4jClient | None
        Optional pre-built Neo4j client. Created from settings if not provided.
    apply_schema_on_start : bool
        Whether to apply/verify the Neo4j schema before ingesting data.
        Default True — safe to leave on for all runs.
    """

    def __init__(
        self,
        neo4j_client: Neo4jClient | None = None,
        apply_schema_on_start: bool = True,
    ) -> None:
        self._neo4j_client = neo4j_client or Neo4jClient()
        self._apply_schema = apply_schema_on_start
        self._ingester = GraphIngester(self._neo4j_client)
        self._extractor = EntityExtractor()
        self._reddit = get_reddit()
        self._scraper = RedditScraper(self._reddit)

    # ─────────────────────────────────────────────────────────────────────────
    # Public interface
    # ─────────────────────────────────────────────────────────────────────────

    def run(self) -> PipelineStats:
        """
        Execute the full pipeline: scrape → enrich → ingest.

        Returns
        -------
        PipelineStats
            A summary of what was processed during this run.
        """
        stats = PipelineStats()
        settings.configure_logging()

        logger.info("=" * 55)
        logger.info("  Reddit Knowledge Graph Pipeline starting")
        logger.info("  Target subreddits : %s", settings.target_subreddits)
        logger.info("  Filter keywords   : %s", settings.filter_keywords)
        logger.info("  Lookback months   : %d", settings.lookback_months)
        logger.info("=" * 55)

        # ── Step 1: Schema ────────────────────────────────────────────────────
        if self._apply_schema:
            logger.info("[1/4] Applying Neo4j schema...")
            apply_schema(self._neo4j_client)

        # ── Step 2: Seed subreddit nodes ──────────────────────────────────────
        logger.info("[2/4] Seeding subreddit metadata...")
        self._seed_subreddits()

        # ── Step 3: Scrape posts ──────────────────────────────────────────────
        logger.info("[3/4] Scraping Reddit posts...")
        posts = self._scraper.scrape_all()
        stats.posts_scraped = len(posts)
        logger.info("  → %d qualifying posts collected.", stats.posts_scraped)

        if not posts:
            logger.warning("No posts found. Check your keywords and API credentials.")
            return stats

        # ── Step 4: Enrich and ingest ─────────────────────────────────────────
        logger.info("[4/4] Enriching and ingesting posts...")
        self._process_posts(posts, stats)

        # ── Done ──────────────────────────────────────────────────────────────
        logger.info(stats.summary())
        return stats

    def run_for_subreddit(self, subreddit_name: str) -> PipelineStats:
        """
        Run the pipeline for a single subreddit only.

        Useful for testing or incremental updates.
        """
        stats = PipelineStats()
        # Override target subreddits temporarily
        original = settings.target_subreddits
        settings.target_subreddits = [subreddit_name]
        try:
            self._seed_subreddits()
            posts = self._scraper.scrape_all()
            stats.posts_scraped = len(posts)
            self._process_posts(posts, stats)
        finally:
            settings.target_subreddits = original
        return stats

    # ─────────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _seed_subreddits(self) -> None:
        """
        Fetch subreddit metadata and upsert Subreddit nodes into Neo4j.

        This must happen before posts are written (posts have IN_SUBREDDIT edges).
        """
        for name in settings.target_subreddits:
            try:
                meta = self._scraper.get_subreddit_meta(name)
                self._ingester.upsert_subreddit(meta)
                logger.debug("  Seeded r/%s (%d subscribers)", name, meta.subscribers)
            except Exception as exc:
                logger.warning("Could not fetch metadata for r/%s: %s", name, exc)
                # Create a minimal placeholder so posts can still be linked
                from src.ingestion.models import SubredditMeta
                self._ingester.upsert_subreddit(
                    SubredditMeta(name=name, display_name=f"r/{name}")
                )

    def _process_posts(self, posts: List[RedditPost], stats: PipelineStats) -> None:
        """Enrich and ingest a list of posts with a progress bar."""
        for post in tqdm(posts, desc="Processing posts", unit="post"):
            try:
                self._process_single_post(post, stats)
                stats.posts_ingested += 1
            except Exception as exc:
                logger.error(
                    "Failed to process post %s (%s): %s",
                    post.id, post.title[:60], exc,
                    exc_info=True,
                )
                stats.posts_failed += 1

    def _process_single_post(self, post: RedditPost, stats: PipelineStats) -> None:
        """Enrich a single post + comments and write everything to Neo4j."""
        # Enrich post and comments via Claude
        post_enrichment, comment_enrichments = self._extractor.enrich_post_with_comments(post)

        # Write to Neo4j
        self._ingester.ingest_full_post(post, post_enrichment, comment_enrichments)

        stats.comments_ingested += len(post.comments)
        stats.entities_created += sum(
            len(e.entities) for e in [post_enrichment] + comment_enrichments
        )

        logger.debug(
            "Processed post %s | %d comments | %d entities",
            post.id, len(post.comments), len(post_enrichment.entities),
        )
