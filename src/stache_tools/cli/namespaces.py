"""Namespace management commands."""

import json

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ..client import StacheAPI

console = Console()


@click.group()
def namespace():
    """Manage namespaces."""
    pass


@namespace.command("list")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def list_namespaces(as_json: bool):
    """List all namespaces."""
    with StacheAPI() as api:
        result = api.list_namespaces()

        if as_json:
            console.print_json(json.dumps(result))
            return

        namespaces = result.get("namespaces", [])

        if not namespaces:
            console.print("[yellow]No namespaces found.[/yellow]")
            return

        table = Table(title="Namespaces")
        table.add_column("ID", style="cyan")
        table.add_column("Name")
        table.add_column("Description")
        table.add_column("Docs", justify="right")
        table.add_column("Chunks", justify="right")

        for ns in namespaces:
            table.add_row(
                ns.get("id", ""),
                ns.get("name", ""),
                ns.get("description", "")[:40],
                str(ns.get("doc_count", "-")),
                str(ns.get("chunk_count", "-")),
            )

        console.print(table)


@namespace.command("get")
@click.argument("ns_id")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def get_namespace(ns_id: str, as_json: bool):
    """Get namespace details."""
    with StacheAPI() as api:
        result = api.get_namespace(ns_id)

        if as_json:
            console.print_json(json.dumps(result))
            return

        console.print(Panel(
            f"[bold]Name:[/bold] {result.get('name', '')}\n"
            f"[bold]Description:[/bold] {result.get('description', '')}\n"
            f"[bold]Parent:[/bold] {result.get('parent_id') or 'None'}\n"
            f"[bold]Documents:[/bold] {result.get('doc_count', '-')}\n"
            f"[bold]Chunks:[/bold] {result.get('chunk_count', '-')}\n"
            f"[bold]Created:[/bold] {result.get('created_at', '')[:19] if result.get('created_at') else '-'}\n"
            f"[bold]Updated:[/bold] {result.get('updated_at', '')[:19] if result.get('updated_at') else '-'}",
            title=f"[cyan]{ns_id}[/cyan]",
        ))


@namespace.command("create")
@click.argument("ns_id")
@click.option("--name", "-n", required=True, help="Display name")
@click.option("--description", "-d", default="", help="Description")
@click.option("--parent", "-p", help="Parent namespace ID")
@click.option("--metadata", "-m", help="Metadata as JSON")
def create_namespace(ns_id: str, name: str, description: str, parent: str | None, metadata: str | None):
    """Create a namespace."""
    # Parse metadata if provided
    meta_dict = None
    if metadata:
        try:
            meta_dict = json.loads(metadata)
        except json.JSONDecodeError as e:
            console.print(f"[red]Invalid metadata JSON: {e}[/red]")
            return

    with StacheAPI() as api:
        api.create_namespace(id=ns_id, name=name, description=description, parent_id=parent, metadata=meta_dict)
        console.print(f"[green]Created namespace:[/green] {ns_id}")


@namespace.command("update")
@click.argument("ns_id")
@click.option("--name", "-n", help="New display name")
@click.option("--description", "-d", help="New description")
@click.option("--metadata", "-m", help="New metadata as JSON")
def update_namespace(ns_id: str, name: str | None, description: str | None, metadata: str | None):
    """Update a namespace."""
    # Parse metadata if provided
    meta_dict = None
    if metadata:
        try:
            meta_dict = json.loads(metadata)
        except json.JSONDecodeError as e:
            console.print(f"[red]Invalid metadata JSON: {e}[/red]")
            return

    if not any([name, description, metadata]):
        console.print("[yellow]Nothing to update. Provide --name, --description, or --metadata[/yellow]")
        return

    with StacheAPI() as api:
        api.update_namespace(id=ns_id, name=name, description=description, metadata=meta_dict)
        console.print(f"[green]Updated namespace:[/green] {ns_id}")


@namespace.command("delete")
@click.argument("ns_id")
@click.option("--cascade", is_flag=True, help="Delete all documents in namespace")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def delete_namespace(ns_id: str, cascade: bool, yes: bool):
    """Delete a namespace."""
    if not yes:
        if cascade:
            click.confirm(f"Delete namespace '{ns_id}' and ALL its documents?", abort=True)
        else:
            click.confirm(f"Delete namespace '{ns_id}'?", abort=True)

    with StacheAPI() as api:
        result = api.delete_namespace(id=ns_id, cascade=cascade)
        if cascade:
            chunks = result.get("chunks_deleted", 0)
            docs = result.get("documents_deleted", 0)
            console.print(f"[green]Deleted namespace:[/green] {ns_id} ({docs} docs, {chunks} chunks)")
        else:
            console.print(f"[green]Deleted namespace:[/green] {ns_id}")
