"""
config.py
─────────
Central configuration for the reddit-knowledge-graph pipeline.

All settings are read from environment variables (or a .env file).
Import `settings` from this module anywhere you need config values:

    from src.config import settings

Never hard-code credentials or URLs elsewhere in the codebase.
"""

from __future__ import annotations

import logging
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# ─────────────────────────────────────────────────────────────────────────────
# Settings model
# ─────────────────────────────────────────────────────────────────────────────

class Settings(BaseSettings):
    """
    Application settings loaded from environment variables / .env file.

    Pydantic-settings automatically reads variables from:
      1. Environment variables (case-insensitive)
      2. A .env file in the current working directory
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Reddit ────────────────────────────────────────────────────────────────
    reddit_client_id: str = Field(..., description="Reddit app client ID")
    reddit_client_secret: str = Field(..., description="Reddit app client secret")
    reddit_user_agent: str = Field(
        default="reddit-knowledge-graph/0.1",
        description="Reddit API user-agent string",
    )
    reddit_username: str | None = Field(
        default=None, description="Reddit username for authenticated requests (optional)"
    )
    reddit_password: str | None = Field(
        default=None, description="Reddit password for authenticated requests (optional)"
    )

    # ── Anthropic ─────────────────────────────────────────────────────────────
    anthropic_api_key: str = Field(..., description="Anthropic API key")
    anthropic_model: str = Field(
        default="claude-3-5-haiku-20241022",
        description="Anthropic model for entity extraction and sentiment",
    )

    # ── Neo4j ─────────────────────────────────────────────────────────────────
    neo4j_uri: str = Field(default="bolt://localhost:7687", description="Neo4j Bolt URI")
    neo4j_username: str = Field(default="neo4j", description="Neo4j username")
    neo4j_password: str = Field(default="password123", description="Neo4j password")
    neo4j_database: str = Field(default="neo4j", description="Neo4j database name")

    # ── Pipeline ──────────────────────────────────────────────────────────────
    lookback_months: int = Field(
        default=36, ge=1, le=36, description="How many months back to scrape on first run"
    )
    max_posts_per_subreddit: int = Field(
        default=500, ge=1, le=1000, description="Max posts per subreddit per run"
    )
    max_comments_per_post: int = Field(
        default=50, ge=1, le=500, description="Max top-level comments per post"
    )

    # Parsed from comma-separated env vars
    target_subreddits: List[str] = Field(
        default=[
            "snowflake", "databricks", "microsoftfabric", "dataengineering",
            "analytics", "dataanalysis", "datascience", "neo4j",
            "knowledgegraph", "rag",
        ],
        description="Subreddit names to monitor (no r/ prefix)",
    )
    filter_keywords: List[str] = Field(
        default=[
            "Neo4j", "graph database", "graphRAG", "graph AI",
            "graph integrations", "connected components", "path finding", "agentic AI",
        ],
        description="At least one keyword must appear in a post or comment to be ingested",
    )

    # ── Logging ───────────────────────────────────────────────────────────────
    log_level: str = Field(default="INFO", description="Python logging level")

    # ─────────────────────────────────────────────────────────────────────────
    # Validators
    # ─────────────────────────────────────────────────────────────────────────

    @field_validator("target_subreddits", "filter_keywords", mode="before")
    @classmethod
    def _split_csv(cls, v: str | list) -> list:
        """Allow comma-separated strings from env vars to be parsed into lists."""
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        return v

    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, v: str) -> str:
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in valid:
            raise ValueError(f"log_level must be one of {valid}")
        return upper

    # ─────────────────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────────────────

    def configure_logging(self) -> None:
        """Apply the configured log level to the root logger."""
        logging.basicConfig(
            level=getattr(logging, self.log_level),
            format="%(asctime)s | %(levelname)-8s | %(name)s – %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    @property
    def keywords_lower(self) -> List[str]:
        """Return filter keywords lowercased for case-insensitive matching."""
        return [kw.lower() for kw in self.filter_keywords]


# ─────────────────────────────────────────────────────────────────────────────
# Singleton — import this everywhere
# ─────────────────────────────────────────────────────────────────────────────

settings = Settings()
