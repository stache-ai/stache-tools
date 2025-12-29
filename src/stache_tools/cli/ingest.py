"""Ingest command for uploading files to Stache."""

import json
import os
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from stache_tools.client import StacheAPI
from stache_tools.client.config import StacheConfig
from stache_tools.client.exceptions import StacheError
from stache_tools.loaders import LoaderRegistry

console = Console()

CHUNKING_STRATEGIES = ["auto", "recursive", "markdown", "semantic", "character", "hierarchical", "transcript"]


def ingest_file(
    client: StacheAPI,
    registry: LoaderRegistry,
    filepath: Path,
    namespace: str | None,
    chunking_strategy: str,
    metadata: dict | None,
    prepend_metadata: list[str] | None,
) -> bool:
    """Ingest a single file. Returns True on success."""
    loader = registry.get_loader(filepath.name)
    if loader is None:
        console.print(f"[yellow]Skipping {filepath} - no loader available[/yellow]")
        return False

    try:
        with open(filepath, "rb") as f:
            doc = loader.load(f, filepath.name)

        # Merge metadata
        file_metadata = doc.metadata.copy()
        file_metadata["source_file"] = str(filepath)
        if metadata:
            file_metadata.update(metadata)

        result = client.ingest_text(
            text=doc.text,
            namespace=namespace,
            metadata=file_metadata,
            chunking_strategy=chunking_strategy,
            prepend_metadata=prepend_metadata,
        )
        chunks = result.get("chunks_created", "?")
        console.print(f"[green]✓[/green] {filepath.name} → {chunks} chunks")
        return True
    except StacheError as e:
        console.print(f"[red]✗[/red] {filepath.name}: {e}")
        return False
    except Exception as e:
        console.print(f"[red]✗[/red] {filepath.name}: {e}")
        return False


def collect_files(path: Path, recursive: bool) -> list[Path]:
    """Collect files to ingest."""
    if path.is_file():
        return [path]

    if not path.is_dir():
        return []

    files = []
    if recursive:
        for root, _, filenames in os.walk(path):
            for name in filenames:
                files.append(Path(root) / name)
    else:
        files = [p for p in path.iterdir() if p.is_file()]

    return sorted(files)


@click.command("ingest")
@click.argument("path", type=click.Path(exists=True), required=False)
@click.option("-n", "--namespace", help="Target namespace")
@click.option("-r", "--recursive", is_flag=True, help="Recursively process directories")
@click.option(
    "-c", "--chunking-strategy",
    type=click.Choice(CHUNKING_STRATEGIES, case_sensitive=False),
    default="auto",
    help="Chunking strategy (default: auto)"
)
@click.option("-m", "--metadata", "metadata_json", help="Metadata as JSON (e.g. '{\"author\": \"John\"}')")
@click.option(
    "-p", "--prepend-metadata",
    help="Metadata keys to prepend to chunks (comma-separated, e.g. 'author,topic')"
)
@click.option("-t", "--text", "text_input", help="Ingest text directly instead of a file")
@click.option("--stdin", is_flag=True, help="Read text from stdin")
def ingest(
    path: str | None,
    namespace: str | None,
    recursive: bool,
    chunking_strategy: str,
    metadata_json: str | None,
    prepend_metadata: str | None,
    text_input: str | None,
    stdin: bool,
) -> None:
    """Ingest files or text into Stache.

    PATH can be a file or directory. Use -r for recursive directory processing.

    Alternatively, use --text or --stdin to ingest text directly.

    \b
    Examples:
      stache ingest document.pdf -n docs
      stache ingest ./files/ -r -c markdown
      stache ingest -t "Quick note to remember" -n notes
      echo "Text from pipe" | stache ingest --stdin -n notes
      stache ingest sermon.txt -m '{"speaker":"Pastor John"}' -p speaker
    """
    config = StacheConfig()

    # Parse metadata
    metadata = None
    if metadata_json:
        try:
            metadata = json.loads(metadata_json)
        except json.JSONDecodeError as e:
            console.print(f"[red]Invalid metadata JSON: {e}[/red]")
            return

    # Parse prepend_metadata
    prepend_keys = None
    if prepend_metadata:
        prepend_keys = [k.strip() for k in prepend_metadata.split(",") if k.strip()]

    # Handle text input modes
    if stdin:
        if not sys.stdin.isatty():
            text_input = sys.stdin.read()
        else:
            console.print("[red]No input on stdin[/red]")
            return

    if text_input:
        # Direct text ingestion
        with StacheAPI(config) as client:
            try:
                result = client.ingest_text(
                    text=text_input,
                    namespace=namespace,
                    metadata=metadata,
                    chunking_strategy=chunking_strategy if chunking_strategy != "auto" else "recursive",
                    prepend_metadata=prepend_keys,
                )
                chunks = result.get("chunks_created", "?")
                doc_id = result.get("doc_id", result.get("document_id", ""))
                console.print(f"[green]✓[/green] Ingested text → {chunks} chunks (doc: {doc_id[:8]}...)")
            except StacheError as e:
                console.print(f"[red]✗[/red] Failed: {e}")
        return

    # File/directory ingestion
    if not path:
        console.print("[red]Provide a PATH or use --text/--stdin[/red]")
        return

    registry = LoaderRegistry()
    target = Path(path)
    files = collect_files(target, recursive)

    if not files:
        console.print("[yellow]No files to ingest[/yellow]")
        return

    console.print(f"Found {len(files)} file(s) to process")
    if chunking_strategy != "auto":
        console.print(f"[dim]Chunking strategy: {chunking_strategy}[/dim]")

    success = 0
    failed = 0
    skipped = 0

    with StacheAPI(config) as client:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Ingesting...", total=len(files))

            for filepath in files:
                progress.update(task, description=f"Processing {filepath.name}")

                loader = registry.get_loader(filepath.name)
                if loader is None:
                    skipped += 1
                elif ingest_file(
                    client, registry, filepath, namespace,
                    chunking_strategy if chunking_strategy != "auto" else "recursive",
                    metadata, prepend_keys
                ):
                    success += 1
                else:
                    failed += 1

                progress.advance(task)

    # Summary
    console.print()
    console.print(f"[bold]Results:[/bold] {success} ingested, {failed} failed, {skipped} skipped")
