"""
run_pipeline.py
───────────────
CLI entry point for the Reddit → Neo4j ingestion pipeline.

Usage
─────
    # Full run across all configured subreddits
    python scripts/run_pipeline.py

    # Single subreddit (useful for testing)
    python scripts/run_pipeline.py --subreddit neo4j

    # Dry-run: scrape and enrich but skip Neo4j writes
    python scripts/run_pipeline.py --dry-run

    # Skip schema setup (if already applied)
    python scripts/run_pipeline.py --no-schema

Options
───────
    --subreddit TEXT    Run for a single subreddit only.
    --dry-run           Scrape + enrich but do NOT write to Neo4j.
    --no-schema         Skip the schema apply step.
    --limit INT         Override max posts per subreddit for this run.
"""

from __future__ import annotations

import logging
from typing import Optional

import typer
from rich.console import Console

from src.config import settings
from src.pipeline.orchestrator import Pipeline

app = typer.Typer(help="Run the Reddit Knowledge Graph ingestion pipeline.")
console = Console()
logger = logging.getLogger(__name__)


@app.command()
def main(
    subreddit: Optional[str] = typer.Option(
        None, "--subreddit", "-s", help="Run for a single subreddit only (no r/ prefix)."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Scrape and enrich but do NOT write to Neo4j."
    ),
    no_schema: bool = typer.Option(
        False, "--no-schema", help="Skip the schema apply step."
    ),
    limit: Optional[int] = typer.Option(
        None, "--limit", "-l", help="Override max posts per subreddit for this run."
    ),
) -> None:
    """Run the Reddit → Neo4j knowledge graph ingestion pipeline."""
    settings.configure_logging()

    console.print("\n[bold cyan]Reddit Knowledge Graph — Ingestion Pipeline[/bold cyan]\n")

    # Apply CLI overrides
    if limit is not None:
        settings.max_posts_per_subreddit = limit
        console.print(f"  Post limit overridden to {limit} per subreddit")

    if dry_run:
        console.print("[yellow]  DRY RUN mode — no data will be written to Neo4j[/yellow]")
        _run_dry(subreddit)
        return

    # Normal run
    pipeline = Pipeline(apply_schema_on_start=not no_schema)

    if subreddit:
        console.print(f"  Running for single subreddit: r/{subreddit}\n")
        stats = pipeline.run_for_subreddit(subreddit)
    else:
        console.print(f"  Subreddits : {settings.target_subreddits}\n")
        stats = pipeline.run()

    console.print(stats.summary())
    console.print("[bold green]Pipeline complete.[/bold green]")


def _run_dry(subreddit: Optional[str]) -> None:
    """
    Dry-run: scrape and enrich only, no Neo4j writes.

    Useful for verifying credentials and inspecting Claude's extraction
    output before committing data.
    """
    from src.ingestion.reddit_client import get_reddit
    from src.ingestion.scraper import RedditScraper
    from src.processing.entity_extractor import EntityExtractor

    reddit = get_reddit()
    scraper = RedditScraper(reddit)
    extractor = EntityExtractor()

    if subreddit:
        target = [subreddit]
    else:
        target = settings.target_subreddits[:2]  # Limit in dry-run

    console.print(f"[dim]Dry-running for: {target}[/dim]")

    original = settings.target_subreddits
    settings.target_subreddits = target
    posts = scraper.scrape_all()
    settings.target_subreddits = original

    console.print(f"  → {len(posts)} posts scraped")

    for post in posts[:3]:  # Show first 3 enrichments
        enrichment, comment_enrichments = extractor.enrich_post_with_comments(post)
        console.print(f"\n  Post: [bold]{post.title[:70]}[/bold]")
        console.print(f"    Entities : {[e.name for e in enrichment.entities[:5]]}")
        console.print(f"    Topics   : {[t.name for t in enrichment.topics]}")
        if enrichment.sentiment:
            console.print(
                f"    Sentiment: {enrichment.sentiment.label.value} "
                f"(score={enrichment.sentiment.score:.2f})"
            )
        console.print(f"    Summary  : {(enrichment.summary or '')[:100]}...")

    console.print("\n[green]Dry run complete. No data written to Neo4j.[/green]")


if __name__ == "__main__":
    app()
