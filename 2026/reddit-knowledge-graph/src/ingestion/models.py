"""
models.py
─────────
Pydantic models representing the raw Reddit data extracted by the scraper.

These models sit between PRAW objects and the Neo4j ingestion layer.
They are serialisation-friendly (JSON / dict) so they can be cached, logged,
or written to a queue without any PRAW dependency downstream.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class RedditUser(BaseModel):
    """Represents a Reddit account."""

    username: str
    # PRAW only exposes these for the authenticated user; for others they may
    # be None if the account is suspended or shadowbanned.
    created_utc: Optional[datetime] = None
    link_karma: Optional[int] = None
    comment_karma: Optional[int] = None
    is_mod: bool = False


class RedditComment(BaseModel):
    """A single Reddit comment."""

    id: str
    post_id: str                     # Parent submission ID
    parent_id: str                   # Could be post_id or another comment ID
    author: Optional[str] = None     # None if [deleted]
    body: str
    score: int = 0
    created_utc: datetime
    depth: int = 0
    permalink: str = ""
    is_top_level: bool = True        # True if direct reply to post


class RedditPost(BaseModel):
    """A Reddit submission (post)."""

    id: str
    subreddit: str
    title: str
    body: str = ""                   # selftext; empty for link posts
    url: str
    permalink: str
    author: Optional[str] = None     # None if [deleted]
    score: int = 0
    upvote_ratio: float = 0.0
    num_comments: int = 0
    flair: Optional[str] = None
    created_utc: datetime
    is_self: bool = True             # True = text post; False = link post
    comments: List[RedditComment] = Field(default_factory=list)


class SubredditMeta(BaseModel):
    """Lightweight subreddit metadata."""

    name: str                        # e.g. "neo4j"
    display_name: str                # e.g. "r/neo4j"
    subscribers: int = 0
    description: str = ""
    created_utc: Optional[datetime] = None
