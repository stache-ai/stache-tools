"""Job management commands (async ingestion job contract)."""

import json

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ..client import StacheAPI
from ..client.exceptions import StacheNotFoundError

console = Console()


@click.group("jobs")
def jobs():
    """Manage ingestion jobs ("my uploads")."""
    pass


@jobs.command("list")
@click.option("--status", help="Filter by job status")
@click.option("--limit", default=50, help="Maximum jobs to return (default: 50)")
@click.option("--json", "-j", "as_json", is_flag=True, help="Output as JSON")
def list_jobs(status: str | None, limit: int, as_json: bool):
    """List ingestion jobs."""
    with StacheAPI() as api:
        result = api.list_jobs(status=status, limit=limit)

        if as_json:
            console.print_json(json.dumps(result))
            return

        job_list = result.get("jobs", [])

        if not job_list:
            console.print("[yellow]No jobs found.[/yellow]")
            return

        table = Table(title="Jobs")
        table.add_column("Job ID", style="cyan")
        table.add_column("Status")
        table.add_column("Filename")
        table.add_column("Namespace")
        table.add_column("Created")

        for job in job_list:
            table.add_row(
                job.get("job_id", ""),
                job.get("status", ""),
                job.get("filename", "") or "",
                job.get("namespace", "") or "",
                (job.get("created_at", "") or "")[:19],
            )

        console.print(table)


@jobs.command("get")
@click.argument("job_id")
@click.option("--json", "-j", "as_json", is_flag=True, help="Output as JSON")
def get_job(job_id: str, as_json: bool):
    """Get details for a single job."""
    with StacheAPI() as api:
        try:
            result = api.get_job(job_id)
        except StacheNotFoundError:
            console.print(f"[red]Job not found:[/red] {job_id}")
            raise SystemExit(1)

        if as_json:
            console.print_json(json.dumps(result))
            return

        console.print(Panel(
            f"[bold]Status:[/bold] {result.get('status', '')}\n"
            f"[bold]Filename:[/bold] {result.get('filename') or '-'}\n"
            f"[bold]Namespace:[/bold] {result.get('namespace') or '-'}\n"
            f"[bold]Document:[/bold] {result.get('doc_id') or result.get('document_id') or '-'}\n"
            f"[bold]Chunks:[/bold] {result.get('chunks_created', '-')}\n"
            f"[bold]Error:[/bold] {result.get('error_detail') or '-'}\n"
            f"[bold]Created:[/bold] {(result.get('created_at', '') or '')[:19] or '-'}\n"
            f"[bold]Updated:[/bold] {(result.get('updated_at', '') or '')[:19] or '-'}",
            title=f"[cyan]{job_id}[/cyan]",
        ))
