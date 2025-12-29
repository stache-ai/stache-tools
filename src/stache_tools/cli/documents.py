"""Document management commands."""

import json

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ..client import StacheAPI

console = Console()


@click.group()
def doc():
    """Manage documents."""
    pass


@doc.command("list")
@click.option("--namespace", "-n", help="Filter by namespace")
@click.option("--limit", "-l", default=50, help="Max documents (up to 100)")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def list_documents(namespace: str | None, limit: int, as_json: bool):
    """List documents."""
    api = StacheAPI()

    try:
        result = api.list_documents(namespace=namespace, limit=limit)

        if as_json:
            console.print_json(json.dumps(result))
            return

        documents = result.get("documents", [])

        if not documents:
            console.print("[yellow]No documents found.[/yellow]")
            return

        table = Table(title="Documents")
        table.add_column("ID", style="cyan", max_width=36)
        table.add_column("Filename")
        table.add_column("Namespace")
        table.add_column("Chunks", justify="right")

        for d in documents:
            table.add_row(
                d.get("doc_id", "")[:36],
                d.get("filename", "")[:30],
                d.get("namespace", "default"),
                str(d.get("chunk_count", d.get("total_chunks", "?"))),
            )

        console.print(table)

        # Show pagination info
        next_key = result.get("next_key")
        if next_key:
            console.print(f"\n[dim]More results available. Use --limit to fetch more.[/dim]")
    finally:
        api.close()


@doc.command("get")
@click.argument("doc_id")
@click.option("--namespace", "-n", default="default", help="Namespace containing the document")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def get_document(doc_id: str, namespace: str, as_json: bool):
    """Get document details and content."""
    api = StacheAPI()

    try:
        result = api.get_document(doc_id, namespace)

        if as_json:
            console.print_json(json.dumps(result))
            return

        # Document info panel
        info = (
            f"[bold]ID:[/bold] {result.get('doc_id', '')}\n"
            f"[bold]Namespace:[/bold] {result.get('namespace', 'default')}\n"
            f"[bold]Chunks:[/bold] {result.get('chunk_count', result.get('total_chunks', '?'))}\n"
            f"[bold]Created:[/bold] {result.get('created_at', '')[:19] if result.get('created_at') else '-'}"
        )
        console.print(Panel(info, title=f"[cyan]{result.get('filename', 'Untitled')}[/cyan]"))

        # Document content
        text = result.get("reconstructed_text", result.get("text", ""))
        if text:
            console.print("\n[bold]Content:[/bold]")
            console.print(text[:2000])
            if len(text) > 2000:
                console.print(f"\n[dim]... ({len(text) - 2000} more characters)[/dim]")
    finally:
        api.close()


@doc.command("delete")
@click.argument("doc_id")
@click.option("--namespace", "-n", default="default", help="Namespace containing the document")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def delete_document(doc_id: str, namespace: str, yes: bool):
    """Delete a document."""
    if not yes:
        click.confirm(f"Delete document '{doc_id}'?", abort=True)

    api = StacheAPI()

    try:
        result = api.delete_document(doc_id, namespace)
        if result.get("success"):
            chunks = result.get("chunks_deleted", 0)
            console.print(f"[green]Deleted document ({chunks} chunks)[/green]")
        else:
            console.print(f"[red]Error:[/red] {result.get('error')}")
    finally:
        api.close()
