"""Health check command."""

import json

import click
from rich.console import Console

from ..client import StacheAPI, StacheConfig

console = Console()


@click.command()
@click.option("--check-auth", is_flag=True, help="Validate authentication")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def health(check_auth: bool, as_json: bool):
    """Check API connectivity and health."""
    config = StacheConfig()
    api = StacheAPI(config)

    if not as_json:
        transport = "lambda" if config.lambda_function_name else "http"
        target = config.lambda_function_name or config.api_url
        console.print(f"[bold]Transport:[/bold] {transport}")
        console.print(f"[bold]Target:[/bold] {target}")
        if transport == "http":
            console.print(f"[bold]OAuth:[/bold] {'enabled' if config.oauth_enabled else 'disabled'}")
        console.print()

    try:
        result = api.health(include_auth=check_auth or config.oauth_enabled)

        if as_json:
            console.print_json(json.dumps(result))
            return

        status = result.get("status", "unknown")
        if status == "healthy":
            console.print(f"[green]Status: {status}[/green]")
        else:
            console.print(f"[yellow]Status: {status}[/yellow]")

        if "auth_status" in result:
            auth = result["auth_status"]
            if auth == "valid":
                console.print(f"[green]Auth: {auth}[/green]")
            else:
                console.print(f"[red]Auth: {auth}[/red]")

        # Show providers
        providers = result.get("providers", {})
        if providers:
            console.print()
            console.print("[bold]Providers:[/bold]")
            console.print(f"  VectorDB: {providers.get('vectordb_provider', 'unknown')}")
            console.print(f"  Embedding: {providers.get('embedding_provider', 'unknown')}")
            console.print(f"  LLM: {providers.get('llm_provider', 'unknown')}")

        if api.last_request_id:
            console.print(f"\n[dim]Request ID: {api.last_request_id}[/dim]")

    except Exception as e:
        console.print(f"[red]Health check failed:[/red] {e}")
        raise click.Abort()

    finally:
        api.close()
