"""Search command."""

import json

import click
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from ..client import StacheAPI

console = Console()


@click.command()
@click.argument("query")
@click.option("--namespace", "-n", help="Limit to namespace")
@click.option("--top-k", "-k", default=10, help="Number of results")
@click.option("--synthesize", is_flag=True, help="Enable LLM synthesis (slower, uses LLM)")
@click.option("--no-rerank", is_flag=True, help="Skip reranking (faster, less accurate)")
@click.option("--model", "-m", help="Override LLM model for synthesis")
@click.option("--filter", "-f", "filter_json", help="Metadata filter as JSON (e.g. '{\"source\": \"docs\"}')")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def search(
    query: str,
    namespace: str | None,
    top_k: int,
    synthesize: bool,
    no_rerank: bool,
    model: str | None,
    filter_json: str | None,
    as_json: bool,
):
    """Search the knowledge base."""
    api = StacheAPI()

    # Parse filter JSON if provided
    filter_dict = None
    if filter_json:
        try:
            filter_dict = json.loads(filter_json)
        except json.JSONDecodeError as e:
            console.print(f"[red]Invalid filter JSON: {e}[/red]")
            return

    try:
        result = api.search(
            query,
            namespace=namespace,
            top_k=top_k,
            synthesize=synthesize,
            rerank=not no_rerank,
            model=model,
            filter=filter_dict,
        )

        if as_json:
            console.print_json(json.dumps(result))
            return

        # Display synthesized answer if available
        answer = result.get("answer")
        if answer:
            console.print(Panel(
                Markdown(answer),
                title="[bold green]Answer[/bold green]",
                border_style="green",
            ))
            console.print()

        sources = result.get("sources", [])
        if not sources:
            console.print("[yellow]No results found.[/yellow]")
            return

        console.print(f"[bold]Found {len(sources)} sources:[/bold]\n")

        for i, source in enumerate(sources, 1):
            score = source.get("score", 0)
            text = source.get("content", "")[:300]
            metadata = source.get("metadata", {})
            filename = metadata.get("filename", "Unknown")
            ns = metadata.get("namespace", "default")

            console.print(Panel(
                f"{text}...",
                title=f"[cyan]{i}. {filename}[/cyan] (score: {score:.3f})",
                subtitle=f"namespace: {ns}",
            ))

    finally:
        api.close()
