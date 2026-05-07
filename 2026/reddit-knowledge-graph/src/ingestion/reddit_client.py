"""
reddit_client.py
────────────────
Thin wrapper around the PRAW (Python Reddit API Wrapper) Reddit instance.

Responsibilities
────────────────
- Build and return a configured praw.Reddit instance from `settings`.
- Support both authenticated (script) and read-only modes.
- Expose a single `get_reddit()` factory used by the rest of the pipeline.

PRAW documentation: https://praw.readthedocs.io
Reddit API rate limits:
  - Unauthenticated: 10 requests / minute
  - Authenticated:   60 requests / minute  (recommended)
"""

from __future__ import annotations

import logging

import praw
from praw import Reddit

from src.config import settings

logger = logging.getLogger(__name__)


def get_reddit() -> Reddit:
    """
    Build and return a configured PRAW Reddit instance.

    If `REDDIT_USERNAME` and `REDDIT_PASSWORD` are set in the environment the
    client runs in authenticated (script) mode, giving a higher rate limit.
    Otherwise it falls back to read-only mode.

    Returns
    -------
    praw.Reddit
        A ready-to-use Reddit client.

    Raises
    ------
    praw.exceptions.PRAWException
        If credentials are missing or invalid.
    """
    # Determine whether we have credentials for authenticated access
    authenticated = bool(settings.reddit_username and settings.reddit_password)

    reddit = praw.Reddit(
        client_id=settings.reddit_client_id,
        client_secret=settings.reddit_client_secret,
        user_agent=settings.reddit_user_agent,
        username=settings.reddit_username if authenticated else None,
        password=settings.reddit_password if authenticated else None,
        # read_only=True makes PRAW skip OAuth flows entirely; set False so
        # authenticated credentials are actually used when present.
        read_only=not authenticated,
    )

    mode = "authenticated" if authenticated else "read-only"
    logger.info("PRAW Reddit client initialised in %s mode (user-agent: %s)", mode, settings.reddit_user_agent)

    return reddit
