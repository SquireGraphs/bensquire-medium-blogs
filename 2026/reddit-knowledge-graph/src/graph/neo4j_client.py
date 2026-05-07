"""
neo4j_client.py
───────────────
Thin wrapper around the official Neo4j Python driver.

Provides:
- A context-manager-friendly `Neo4jClient` class.
- A `get_client()` factory that returns a singleton for the pipeline.
- Helper methods for running Cypher queries and batched writes.

The driver uses connection pooling internally — do not create a new
`Neo4jClient` per query; create one and reuse it throughout the run.

Usage
─────
    with Neo4jClient() as client:
        results = client.query("MATCH (n:Post) RETURN count(n) AS total")
        print(results[0]["total"])
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Dict, Generator, List, Optional

from neo4j import GraphDatabase, ManagedTransaction, Session
from neo4j.exceptions import ServiceUnavailable

from src.config import settings

logger = logging.getLogger(__name__)


class Neo4jClient:
    """
    Thread-safe Neo4j driver wrapper.

    Parameters
    ----------
    uri : str
        Bolt URI (default from settings).
    username : str
        Neo4j username (default from settings).
    password : str
        Neo4j password (default from settings).
    database : str
        Target database (default from settings).
    """

    def __init__(
        self,
        uri: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        database: Optional[str] = None,
    ) -> None:
        self._uri = uri or settings.neo4j_uri
        self._username = username or settings.neo4j_username
        self._password = password or settings.neo4j_password
        self._database = database or settings.neo4j_database
        self._driver = GraphDatabase.driver(
            self._uri,
            auth=(self._username, self._password),
            max_connection_pool_size=50,
        )
        logger.info("Neo4j driver connected to %s (db=%s)", self._uri, self._database)

    # ─────────────────────────────────────────────────────────────────────────
    # Context manager support
    # ─────────────────────────────────────────────────────────────────────────

    def __enter__(self) -> "Neo4jClient":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def close(self) -> None:
        """Close the underlying driver connection pool."""
        self._driver.close()
        logger.info("Neo4j driver closed.")

    # ─────────────────────────────────────────────────────────────────────────
    # Query helpers
    # ─────────────────────────────────────────────────────────────────────────

    def query(
        self,
        cypher: str,
        parameters: Optional[Dict[str, Any]] = None,
        database: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Run a read or write Cypher query and return all records as dicts.

        Parameters
        ----------
        cypher : str
            The Cypher statement to execute.
        parameters : dict, optional
            Named parameters for the Cypher statement.
        database : str, optional
            Override the default database for this query.

        Returns
        -------
        list[dict]
            All result records, each as a plain Python dict.
        """
        db = database or self._database
        with self._driver.session(database=db) as session:
            result = session.run(cypher, parameters or {})
            return [record.data() for record in result]

    def write_transaction(
        self,
        fn: Any,
        *args: Any,
        database: Optional[str] = None,
        **kwargs: Any,
    ) -> Any:
        """
        Execute `fn(tx, *args, **kwargs)` inside a write transaction.

        Automatically retries on transient errors (deadlocks, leader changes).

        Parameters
        ----------
        fn : callable
            Function accepting a `ManagedTransaction` as its first argument.
        """
        db = database or self._database
        with self._driver.session(database=db) as session:
            return session.execute_write(fn, *args, **kwargs)

    def read_transaction(
        self,
        fn: Any,
        *args: Any,
        database: Optional[str] = None,
        **kwargs: Any,
    ) -> Any:
        """Execute `fn(tx, *args, **kwargs)` inside a read transaction."""
        db = database or self._database
        with self._driver.session(database=db) as session:
            return session.execute_read(fn, *args, **kwargs)

    def batch_write(
        self,
        cypher: str,
        rows: List[Dict[str, Any]],
        batch_size: int = 500,
        database: Optional[str] = None,
    ) -> int:
        """
        Write a list of parameter dicts using UNWIND for efficient batch ingestion.

        Parameters
        ----------
        cypher : str
            Cypher statement with `$rows` as the UNWIND parameter, e.g.:
            ``"UNWIND $rows AS row MERGE (n:Post {id: row.id}) SET n += row.props"``
        rows : list[dict]
            List of parameter dicts, one per logical row.
        batch_size : int
            How many rows to send per transaction (default 500).

        Returns
        -------
        int
            Total number of rows processed.
        """
        total = 0
        for i in range(0, len(rows), batch_size):
            chunk = rows[i : i + batch_size]
            self.query(cypher, {"rows": chunk}, database=database)
            total += len(chunk)
            logger.debug("batch_write: committed %d / %d rows", total, len(rows))

        return total

    def verify_connectivity(self) -> bool:
        """
        Check that the database is reachable.

        Returns
        -------
        bool
            True if connectivity check passes.
        """
        try:
            self._driver.verify_connectivity()
            return True
        except ServiceUnavailable as exc:
            logger.error("Neo4j connectivity check failed: %s", exc)
            return False


# ─────────────────────────────────────────────────────────────────────────────
# Module-level singleton — reuse this across the pipeline run
# ─────────────────────────────────────────────────────────────────────────────

_client: Optional[Neo4jClient] = None


def get_client() -> Neo4jClient:
    """
    Return the module-level Neo4jClient singleton.

    Creates one on first call; subsequent calls return the same instance.
    """
    global _client
    if _client is None:
        _client = Neo4jClient()
    return _client
