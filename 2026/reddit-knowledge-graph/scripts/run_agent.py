"""
run_agent.py
────────────
Interactive CLI for the Reddit Knowledge Graph AI agent.

Starts an interactive REPL where you can ask natural-language questions
about the Reddit knowledge graph. The agent uses LangGraph + Claude to
query Neo4j and synthesise answers.

Usage
─────
    # Interactive mode (REPL)
    python scripts/run_agent.py

    # Single question (non-interactive)
    python scripts/run_agent.py --question "Where are people talking about Neo4j the most?"

    # Streaming mode (shows tool calls as they happen)
    python scripts/run_agent.py --stream

Example questions
─────────────────
    Where are people talking about Neo4j integrations the most?
    What problems are people facing with Agentic AI knowledge graphs?
    How is sentiment surrounding Neo4j in the broader tech ecosystem?
    Who is posting in multiple communities we follow?
    What topics are trending in r/dataengineering this month?
    Show me the most upvoted posts about graphRAG.
"""

from __future__ import annotations

import sys
from typing import Optional

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt

from src.agent.graph_agent import ask, build_agent, stream_ask
from src.agent.prompts import EXAMPLE_QUESTIONS
from src.config import settings

app = typer.Typer(help="Interact with the Reddit Knowledge Graph AI agent.")
console = Console()


@app.command()
def main(
    question: Optional[str] = typer.Option(
        None, "--question", "-q", help="Ask a single question and exit."
    ),
    stream: bool = typer.Option(
        False, "--stream", help="Stream tool calls and intermediate steps."
    ),
) -> None:
    """Launch the Reddit Knowledge Graph AI agent."""
    settings.configure_logging()

    console.print(Panel.fit(
        "[bold cyan]Reddit Knowledge Graph — AI Agent[/bold cyan]\n"
        "[dim]Powered by Claude + LangGraph + Neo4j[/dim]",
        border_style="cyan",
    ))

    if question:
        # Single-shot mode
        _ask_and_print(question, stream=stream)
        return

    # Interactive REPL
    console.print("\n[bold]Example questions you can ask:[/bold]")
    for i, q in enumerate(EXAMPLE_QUESTIONS[:5], 1):
        console.print(f"  [dim]{i}.[/dim] {q}")

    console.print("\n[dim]Type 'exit' or 'quit' to stop. Type 'help' for examples.[/dim]\n")

    while True:
        try:
            user_input = Prompt.ask("[bold cyan]You[/bold cyan]").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Goodbye![/dim]")
            break

        if not user_input:
            continue

        if user_input.lower() in ("exit", "quit", "q"):
            console.print("[dim]Goodbye![/dim]")
            break

        if user_input.lower() in ("help", "?"):
            console.print("\n[bold]Example questions:[/bold]")
            for q in EXAMPLE_QUESTIONS:
                console.print(f"  • {q}")
            console.print()
            continue

        _ask_and_print(user_input, stream=stream)
        console.print()


def _ask_and_print(question: str, stream: bool = False) -> None:
    """Ask the agent a question and print the response."""
    console.print()

    if stream:
        _stream_response(question)
    else:
        _simple_response(question)


def _simple_response(question: str) -> None:
    """Non-streaming response — waits for full answer then prints."""
    with console.status("[dim]Thinking...[/dim]", spinner="dots"):
        answer = ask(question)

    console.print(Panel(
        Markdown(answer),
        title="[bold green]Agent[/bold green]",
        border_style="green",
        padding=(1, 2),
    ))


def _stream_response(question: str) -> None:
    """Streaming response — shows tool calls as they happen."""
    console.print("[dim]Streaming (tool calls shown as they happen)...[/dim]\n")

    final_answer = None
    for event in stream_ask(question):
        # Show tool calls
        if "tools" in event:
            messages = event["tools"].get("messages", [])
            for msg in messages:
                tool_name = getattr(msg, "name", "unknown_tool")
                console.print(f"  [dim]→ Tool: [cyan]{tool_name}[/cyan][/dim]")

        # Capture the final LLM message
        if "llm" in event:
            messages = event["llm"].get("messages", [])
            for msg in messages:
                content = getattr(msg, "content", "")
                if content and not getattr(msg, "tool_calls", None):
                    final_answer = content

    if final_answer:
        console.print()
        console.print(Panel(
            Markdown(final_answer),
            title="[bold green]Agent[/bold green]",
            border_style="green",
            padding=(1, 2),
        ))


if __name__ == "__main__":
    app()
