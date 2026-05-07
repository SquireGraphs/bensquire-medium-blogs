"""
ingester.py
───────────
Writes enriched Reddit data into the Neo4j knowledge graph.

Design
──────
- All writes use MERGE (upsert) — running the pipeline twice for the same
  post does NOT create duplicate nodes.
- Properties are SET with `+=` to preserve existing fields while adding new ones.
- Heavy writes (posts, comments) are batched with UNWIND for efficiency.
- Cross-community user tracking is handled automatically: a single User node
  is shared across all subreddits; edges record which communities they post in.

Node labels created
───────────────────
  Post, Comment, User, Subreddit, Entity, Topic

Relationship types created
──────────────────────────
  POSTED, COMMENTED, IN_SUBREDDIT, ON_POST, REPLY_TO,
  MENTIONS, COVERS, RELATED_TO, ACTIVE_IN
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional

from src.graph.neo4j_client import Neo4jClient
from src.ingestion.models import RedditComment, RedditPost, SubredditMeta
from src.processing.models import EnrichedContent, ExtractedEntity, TopicTag

logger = logging.getLogger(__name__)


class GraphIngester:
    """
    Writes Reddit posts, comments, and NLP enrichments into Neo4j.

    Parameters
    ----------
    client : Neo4jClient
        An open Neo4j client instance.
    """

    def __init__(self, client: Neo4jClient) -> None:
        self.client = client

    # ─────────────────────────────────────────────────────────────────────────
    # Subreddit
    # ─────────────────────────────────────────────────────────────────────────

    def upsert_subreddit(self, meta: SubredditMeta) -> None:
        """Create or update a Subreddit node."""
        self.client.query(
            """
            MERGE (s:Subreddit {name: $name})
            SET s.display_name   = $display_name,
                s.subscribers    = $subscribers,
                s.description    = $description,
                s.created_utc    = $created_utc,
                s.last_updated   = $now
            """,
            {
                "name": meta.name.lower(),
                "display_name": meta.display_name,
                "subscribers": meta.subscribers,
                "description": meta.description,
                "created_utc": meta.created_utc.isoformat() if meta.created_utc else None,
                "now": datetime.utcnow().isoformat(),
            },
        )

    # ─────────────────────────────────────────────────────────────────────────
    # User
    # ─────────────────────────────────────────────────────────────────────────

    def upsert_user(self, username: str) -> None:
        """
        Create or update a User node.

        User nodes are shared across all subreddits — this is what enables
        cross-community tracking. We deliberately use MERGE on username only.
        """
        self.client.query(
            """
            MERGE (u:User {username: $username})
            ON CREATE SET u.first_seen = $now
            SET u.last_seen = $now
            """,
            {"username": username, "now": datetime.utcnow().isoformat()},
        )

    def link_user_to_subreddit(self, username: str, subreddit: str) -> None:
        """
        Create or update an ACTIVE_IN relationship between a User and Subreddit.

        The `activity_count` property is incremented on each call so we can
        rank users by their cross-community engagement.
        """
        self.client.query(
            """
            MATCH (u:User {username: $username})
            MATCH (s:Subreddit {name: $subreddit})
            MERGE (u)-[r:ACTIVE_IN]->(s)
            ON CREATE SET r.activity_count = 1
            ON MATCH  SET r.activity_count = r.activity_count + 1
            """,
            {"username": username, "subreddit": subreddit.lower()},
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Posts
    # ─────────────────────────────────────────────────────────────────────────

    def upsert_post(self, post: RedditPost) -> None:
        """Create or update a Post node and its POSTED / IN_SUBREDDIT edges."""
        self.client.query(
            """
            MERGE (p:Post {id: $id})
            SET p.title         = $title,
                p.body          = $body,
                p.url           = $url,
                p.permalink     = $permalink,
                p.score         = $score,
                p.upvote_ratio  = $upvote_ratio,
                p.num_comments  = $num_comments,
                p.flair         = $flair,
                p.subreddit     = $subreddit,
                p.created_utc   = $created_utc,
                p.is_self       = $is_self,
                p.last_updated  = $now

            WITH p

            // Link to subreddit
            MATCH (s:Subreddit {name: $subreddit})
            MERGE (p)-[:IN_SUBREDDIT]->(s)
            """,
            {
                "id": post.id,
                "title": post.title,
                "body": post.body[:5_000],  # cap to avoid very large node properties
                "url": post.url,
                "permalink": post.permalink,
                "score": post.score,
                "upvote_ratio": post.upvote_ratio,
                "num_comments": post.num_comments,
                "flair": post.flair,
                "subreddit": post.subreddit.lower(),
                "created_utc": post.created_utc.isoformat(),
                "is_self": post.is_self,
                "now": datetime.utcnow().isoformat(),
            },
        )

        # Link author
        if post.author:
            self.upsert_user(post.author)
            self.client.query(
                """
                MATCH (u:User {username: $username})
                MATCH (p:Post  {id: $post_id})
                MERGE (u)-[:POSTED]->(p)
                """,
                {"username": post.author, "post_id": post.id},
            )
            self.link_user_to_subreddit(post.author, post.subreddit)

    # ─────────────────────────────────────────────────────────────────────────
    # Comments
    # ─────────────────────────────────────────────────────────────────────────

    def upsert_comment(self, comment: RedditComment) -> None:
        """Create or update a Comment node and its ON_POST / REPLY_TO / COMMENTED edges."""
        self.client.query(
            """
            MERGE (c:Comment {id: $id})
            SET c.body          = $body,
                c.score         = $score,
                c.created_utc   = $created_utc,
                c.depth         = $depth,
                c.permalink     = $permalink,
                c.is_top_level  = $is_top_level,
                c.last_updated  = $now

            WITH c

            // Always link to the parent post
            MATCH (p:Post {id: $post_id})
            MERGE (c)-[:ON_POST]->(p)
            """,
            {
                "id": comment.id,
                "body": comment.body[:2_000],
                "score": comment.score,
                "created_utc": comment.created_utc.isoformat(),
                "depth": comment.depth,
                "permalink": comment.permalink,
                "is_top_level": comment.is_top_level,
                "post_id": comment.post_id,
                "now": datetime.utcnow().isoformat(),
            },
        )

        # REPLY_TO edge for threaded comments
        if comment.parent_id and comment.parent_id != comment.post_id:
            self.client.query(
                """
                MATCH (child:Comment  {id: $child_id})
                MATCH (parent:Comment {id: $parent_id})
                MERGE (child)-[:REPLY_TO]->(parent)
                """,
                {"child_id": comment.id, "parent_id": comment.parent_id},
            )

        # Link author
        if comment.author:
            self.upsert_user(comment.author)
            self.client.query(
                """
                MATCH (u:User    {username: $username})
                MATCH (c:Comment {id: $comment_id})
                MERGE (u)-[:COMMENTED]->(c)
                """,
                {"username": comment.author, "comment_id": comment.id},
            )

    # ─────────────────────────────────────────────────────────────────────────
    # Enrichment (entities, topics, sentiment)
    # ─────────────────────────────────────────────────────────────────────────

    def apply_enrichment(self, enrichment: EnrichedContent) -> None:
        """
        Write NLP enrichment data for a post or comment into Neo4j.

        - Adds sentiment properties directly to the Post/Comment node.
        - Creates/merges Entity nodes and MENTIONS relationships.
        - Creates/merges Topic nodes and COVERS relationships.
        - Creates RELATED_TO relationships between co-occurring entities.
        """
        node_label = "Post" if enrichment.content_type == "post" else "Comment"

        # ── Sentiment (stored as properties on the content node) ──────────
        if enrichment.sentiment:
            self.client.query(
                f"""
                MATCH (n:{node_label} {{id: $id}})
                SET n.sentiment_label     = $label,
                    n.sentiment_score     = $score,
                    n.sentiment_reasoning = $reasoning
                """,
                {
                    "id": enrichment.content_id,
                    "label": enrichment.sentiment.label.value,
                    "score": enrichment.sentiment.score,
                    "reasoning": enrichment.sentiment.reasoning,
                },
            )

        # ── Summary (posts only) ──────────────────────────────────────────
        if enrichment.summary and enrichment.content_type == "post":
            self.client.query(
                "MATCH (p:Post {id: $id}) SET p.summary = $summary",
                {"id": enrichment.content_id, "summary": enrichment.summary},
            )

        # ── Entities ──────────────────────────────────────────────────────
        for entity in enrichment.entities:
            self._upsert_entity_mention(
                entity, enrichment.content_id, node_label
            )

        # ── Co-occurrence: RELATED_TO between entity pairs ─────────────
        self._upsert_entity_cooccurrence(enrichment.entities)

        # ── Topics ───────────────────────────────────────────────────────
        for topic in enrichment.topics:
            self._upsert_topic_coverage(
                topic, enrichment.content_id, node_label
            )

    def _upsert_entity_mention(
        self,
        entity: ExtractedEntity,
        content_id: str,
        node_label: str,
    ) -> None:
        """Create/update an Entity node and a MENTIONS relationship."""
        self.client.query(
            f"""
            MERGE (e:Entity {{name: $name, type: $type}})
            ON CREATE SET e.first_seen = $now
            SET e.last_seen = $now

            WITH e
            MATCH (n:{node_label} {{id: $content_id}})
            MERGE (n)-[r:MENTIONS]->(e)
            ON CREATE SET r.mentions   = $mentions,
                          r.context    = $context
            ON MATCH  SET r.mentions   = r.mentions + $mentions
            """,
            {
                "name": entity.name,
                "type": entity.type.value,
                "mentions": entity.mentions,
                "context": entity.context,
                "content_id": content_id,
                "now": datetime.utcnow().isoformat(),
            },
        )

    def _upsert_entity_cooccurrence(self, entities: List[ExtractedEntity]) -> None:
        """
        Create/update RELATED_TO edges between all entity pairs in the same content.

        A higher `co_occurrence_count` indicates entities that frequently
        appear together across posts — useful for graph clustering.
        """
        if len(entities) < 2:
            return

        for i, e1 in enumerate(entities):
            for e2 in entities[i + 1 :]:
                self.client.query(
                    """
                    MATCH (a:Entity {name: $name1, type: $type1})
                    MATCH (b:Entity {name: $name2, type: $type2})
                    WHERE id(a) <> id(b)
                    MERGE (a)-[r:RELATED_TO]-(b)
                    ON CREATE SET r.co_occurrence_count = 1
                    ON MATCH  SET r.co_occurrence_count = r.co_occurrence_count + 1
                    """,
                    {
                        "name1": e1.name, "type1": e1.type.value,
                        "name2": e2.name, "type2": e2.type.value,
                    },
                )

    def _upsert_topic_coverage(
        self,
        topic: TopicTag,
        content_id: str,
        node_label: str,
    ) -> None:
        """Create/update a Topic node and a COVERS relationship."""
        self.client.query(
            f"""
            MERGE (t:Topic {{name: $name}})
            ON CREATE SET t.first_seen = $now
            SET t.last_seen = $now

            WITH t
            MATCH (n:{node_label} {{id: $content_id}})
            MERGE (n)-[r:COVERS]->(t)
            ON CREATE SET r.relevance = $relevance
            ON MATCH  SET r.relevance = (r.relevance + $relevance) / 2.0
            """,
            {
                "name": topic.name,
                "relevance": topic.relevance,
                "content_id": content_id,
                "now": datetime.utcnow().isoformat(),
            },
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Convenience: ingest a full post + all comments + enrichments
    # ─────────────────────────────────────────────────────────────────────────

    def ingest_full_post(
        self,
        post: RedditPost,
        post_enrichment: EnrichedContent,
        comment_enrichments: List[EnrichedContent],
    ) -> None:
        """
        Write a post, its comments, and all NLP enrichments into Neo4j.

        This is the main entry-point called by the pipeline orchestrator.
        """
        # Upsert subreddit (must exist before linking post)
        # (Subreddit nodes are seeded by the orchestrator before posts are written;
        #  this MATCH will succeed because schema.py's constraint + orchestrator
        #  pre-seeds them. We include a guard MERGE here for safety.)
        self.client.query(
            "MERGE (:Subreddit {name: $name})",
            {"name": post.subreddit.lower()},
        )

        # Post
        self.upsert_post(post)
        self.apply_enrichment(post_enrichment)

        # Comments
        for comment, enrichment in zip(post.comments, comment_enrichments):
            self.upsert_comment(comment)
            self.apply_enrichment(enrichment)

        logger.debug(
            "Ingested post %s with %d comments and %d enrichments",
            post.id, len(post.comments), len(comment_enrichments),
        )
