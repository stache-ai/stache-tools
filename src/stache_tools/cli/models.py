"""Model listing command."""

import json

import click
from rich.console import Console
from rich.table import Table

from ..client import StacheAPI

console = Console()


@click.command("models")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def models(as_json: bool):
    """List available LLM models."""
    api = StacheAPI()

    try:
        result = api.list_models()

        if as_json:
            console.print_json(json.dumps(result))
            return

        provider = result.get("provider", "unknown")
        default = result.get("default", "")
        model_list = result.get("models", [])

        console.print(f"[bold]Provider:[/bold] {provider}")
        console.print(f"[bold]Default:[/bold] {default}")
        console.print()

        if not model_list:
            console.print("[yellow]No models available.[/yellow]")
            return

        table = Table(title="Available Models")
        table.add_column("ID", style="cyan")
        table.add_column("Name")
        table.add_column("Tier")
        table.add_column("Context", justify="right")

        for model in model_list:
            model_id = model.get("id", "")
            is_default = " *" if model_id == default else ""
            table.add_row(
                model_id + is_default,
                model.get("name", ""),
                model.get("tier", ""),
                str(model.get("context_window", "-")),
            )

        console.print(table)
        console.print("\n[dim]* = default model[/dim]")
    finally:
        api.close()
