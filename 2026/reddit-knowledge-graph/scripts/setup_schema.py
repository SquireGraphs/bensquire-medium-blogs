"""
setup_schema.py
───────────────
CLI script to initialise the Neo4j schema (constraints + indexes).

Run this ONCE before the first pipeline run, and whenever you rebuild
the database from scratch.

Usage
─────
    python scripts/setup_schema.py

    # Wipe and rebuild (destructive — removes all schema metadata):
    python scripts/setup_schema.py --drop

Options
───────
    --drop    Drop all existing constraints/indexes before re-applying.
              WARNING: Data nodes are preserved, but all schema objects
              are destroyed first. Use for clean rebuilds only.
"""

from __future__ import annotations

import sys

import typer
from rich.console import Console
from rich.table import Table

from src.config import settings
from src.graph.neo4j_client import Neo4jClient
from src.graph.schema import apply_schema, drop_schema

app = typer.Typer(help="Initialise the Neo4j schema for the Reddit Knowledge Graph.")
console = Console()


@app.command()
def main(
    drop: bool = typer.Option(
        False,
        "--drop",
        help="Drop all existing constraints/indexes before applying (destructive).",
    )
) -> None:
    """Apply Neo4j schema: constraints, indexes, and full-text indexes."""
    settings.configure_logging()

    console.print("\n[bold cyan]Reddit Knowledge Graph — Schema Setup[/bold cyan]\n")
    console.print(f"  Neo4j URI  : {settings.neo4j_uri}")
    console.print(f"  Database   : {settings.neo4j_database}\n")

    with Neo4jClient() as client:
        # Verify connectivity first
        if not client.verify_connectivity():
            console.print(
                "[bold red]ERROR:[/bold red] Cannot connect to Neo4j. "
                "Is Docker running? Check your .env settings.",
                style="red",
            )
            raise typer.Exit(code=1)

        console.print("[green]✓[/green] Connected to Neo4j\n")

        if drop:
            console.print("[yellow]⚠ Dropping existing schema...[/yellow]")
            drop_schema(client)
            console.print("[green]✓[/green] Schema dropped\n")

        console.print("Applying schema...")
        apply_schema(client)
        console.print("[green]✓[/green] Schema applied successfully\n")

        # Show a summary of what was created
        _print_schema_summary(client)


def _print_schema_summary(client: Neo4jClient) -> None:
    """Print a summary of constraints and indexes in the database."""
    try:
        constraints = client.query("SHOW CONSTRAINTS YIELD name, type, labelsOrTypes, properties")
        indexes = client.query("SHOW INDEXES YIELD name, type, labelsOrTypes, properties WHERE type <> 'LOOKUP'")

        table = Table(title="Active Constraints", show_header=True)
        table.add_column("Name", style="cyan")
        table.add_column("Label")
        table.add_column("Properties")
        for row in constraints:
            table.add_row(
                row.get("name", ""),
                str(row.get("labelsOrTypes", "")),
                str(row.get("properties", "")),
            )
        console.print(table)

        idx_table = Table(title=f"Active Indexes ({len(indexes)})", show_header=True)
        idx_table.add_column("Name", style="cyan")
        idx_table.add_column("Type")
        idx_table.add_column("Labels")
        for row in indexes[:15]:  # Show first 15 to avoid clutter
            idx_table.add_row(
                row.get("name", ""),
                row.get("type", ""),
                str(row.get("labelsOrTypes", "")),
            )
        console.print(idx_table)

    except Exception as exc:
        console.print(f"[yellow]Could not fetch schema summary: {exc}[/yellow]")


if __name__ == "__main__":
    app()
