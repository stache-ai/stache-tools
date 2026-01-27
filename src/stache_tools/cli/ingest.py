"""Ingest command for uploading files to Stache."""

import json
import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
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
    base_path: Path | None = None,
) -> dict:
    """Ingest a single file.

    Args:
        base_path: Optional base path to strip from source_path for portable identifiers

    Returns:
        dict with keys:
        - status: "success" | "skipped" | "error"
        - reason: str (for skipped/error)
        - chunks: int (for success)
        - filepath: Path
        - message: str (formatted message for display)
    """
    loader = registry.get_loader(filepath.name)
    if loader is None:
        return {
            'status': 'skipped',
            'reason': 'no_loader',
            'filepath': filepath,
            'chunks': 0,
            'message': f"[yellow]○[/yellow] {filepath.name} (no loader)"
        }

    try:
        with open(filepath, "rb") as f:
            doc = loader.load(f, filepath.name)

        # Check for empty content
        if not doc.text.strip():
            return {
                'status': 'skipped',
                'reason': 'empty',
                'filepath': filepath,
                'chunks': 0,
                'message': f"[yellow]○[/yellow] {filepath.name} (empty)"
            }

        # Compute source_path (relative to base_path if provided)
        if base_path:
            try:
                # Get absolute paths and compute relative
                abs_filepath = filepath.resolve()
                abs_basepath = base_path.resolve()
                source_path = str(abs_filepath.relative_to(abs_basepath))
            except ValueError:
                # filepath not under base_path, use full path
                source_path = str(filepath)
        else:
            source_path = filepath.name

        # Merge metadata
        file_metadata = doc.metadata.copy()
        file_metadata["source_path"] = source_path
        file_metadata["filename"] = filepath.name
        if metadata:
            file_metadata.update(metadata)

        result = client.ingest_text(
            text=doc.text,
            namespace=namespace,
            metadata=file_metadata,
            chunking_strategy=chunking_strategy,
            prepend_metadata=prepend_metadata,
        )
        chunks = result.get("chunks_created", 0)
        return {
            'status': 'success',
            'filepath': filepath,
            'chunks': chunks,
            'message': f"[green]✓[/green] {filepath.name} → {chunks} chunks"
        }
    except StacheError as e:
        return {
            'status': 'error',
            'reason': str(e),
            'filepath': filepath,
            'chunks': 0,
            'message': f"[red]✗[/red] {filepath.name}: {e}"
        }
    except Exception as e:
        return {
            'status': 'error',
            'reason': str(e),
            'filepath': filepath,
            'chunks': 0,
            'message': f"[red]✗[/red] {filepath.name}: {e}"
        }


def ingest_file_worker(args: tuple) -> dict:
    """Worker function for parallel file processing.

    Creates a fresh StacheAPI client per call to avoid sharing mutable state.
    OAuth token cache is shared at module level (thread-safe).
    LoaderRegistry is singleton (thread-safe).
    """
    filepath, config, namespace, chunking_strategy, metadata, prepend_keys, base_path = args

    # Create fresh client per file (HTTPTransport has mutable state)
    with StacheAPI(config) as client:
        registry = LoaderRegistry()
        return ingest_file(
            client, registry, filepath, namespace,
            chunking_strategy, metadata, prepend_keys, base_path
        )


def _print_summary(success: int, failed: int, skipped: int, total_chunks: int, namespace: str | None) -> None:
    """Print ingestion summary."""
    console.print()
    console.print(f"[bold]{'='*50}[/bold]")
    console.print("[bold]Import Complete[/bold]")
    console.print(f"  Successful: {success} files")
    console.print(f"  Failed: {failed} files")
    console.print(f"  Skipped: {skipped} files")
    console.print(f"  Total chunks: {total_chunks}")
    console.print(f"  Namespace: {namespace or 'default'}")
    console.print(f"[bold]{'='*50}[/bold]")


def collect_files(path: Path, pattern: str, recursive: bool) -> list[Path]:
    """Collect files matching pattern.

    Args:
        path: Base path (file or directory)
        pattern: Glob pattern (e.g., "*.md", "data_*.json")
        recursive: Whether to search subdirectories

    Returns:
        Sorted list of file paths
    """
    if path.is_file():
        return [path]

    if not path.is_dir():
        return []

    if recursive:
        files = list(path.glob(f"**/{pattern}"))
    else:
        files = list(path.glob(pattern))

    return sorted(f for f in files if f.is_file())


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
@click.option("--base-path", type=click.Path(exists=True, path_type=Path),
              help="Base path to strip from source_path for portable identifiers (e.g., /home/user/projects)")
@click.option("--dry-run", is_flag=True, help="Show what would be ingested without actually doing it")
@click.option('-y', '--yes', is_flag=True, help='Skip confirmation prompt')
@click.option('--skip-errors', is_flag=True, help='Continue on errors instead of stopping')
@click.option('-v', '--verbose', is_flag=True, help='Verbose output with debug logging')
@click.option('--pattern', default='*', help='Glob pattern for files (default: *)')
@click.option('-P', '--parallel', default=1, type=click.IntRange(1, 32),
              help='Number of parallel uploads (1-32, default: 1)')
@click.pass_context
def ingest(
    ctx: click.Context,
    path: str | None,
    namespace: str | None,
    recursive: bool,
    chunking_strategy: str,
    metadata_json: str | None,
    prepend_metadata: str | None,
    text_input: str | None,
    stdin: bool,
    base_path: Path | None,
    dry_run: bool,
    yes: bool,
    skip_errors: bool,
    verbose: bool,
    pattern: str,
    parallel: int,
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
    if verbose:
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

    config = StacheConfig()

    # Parse metadata
    metadata = None
    if metadata_json:
        try:
            metadata = json.loads(metadata_json)
        except json.JSONDecodeError as e:
            console.print(f"[red]Invalid metadata JSON: {e}[/red]")
            ctx.exit(1)

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
            ctx.exit(1)

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
                ctx.exit(0)
            except StacheError as e:
                console.print(f"[red]✗[/red] Failed: {e}")
                ctx.exit(1)

    # File/directory ingestion
    if not path:
        console.print("[red]Provide a PATH or use --text/--stdin[/red]")
        ctx.exit(1)

    registry = LoaderRegistry()
    target = Path(path)
    files = collect_files(target, pattern, recursive)

    if not files:
        console.print("[yellow]No files to ingest[/yellow]")
        return

    # Require namespace for multi-file ingests
    if len(files) > 1 and not namespace:
        console.print("[red]Error: --namespace required for multi-file ingests[/red]")
        console.print("Specify namespace with -n/--namespace")
        console.print(f"\nExample: stache ingest {path} -n my-namespace -r")
        ctx.exit(1)

    console.print(f"Found {len(files)} file(s) to process")
    if chunking_strategy != "auto":
        console.print(f"[dim]Chunking strategy: {chunking_strategy}[/dim]")

    if dry_run:
        console.print(f"\n[bold]Dry Run[/bold] - Would ingest {len(files)} files:")
        for f in files[:20]:
            loader = registry.get_loader(f.name)
            status = "[green]✓[/green]" if loader else "[yellow]skip[/yellow]"
            console.print(f"  {status} {f}")
        if len(files) > 20:
            console.print(f"  ... and {len(files) - 20} more")
        console.print(f"\nTarget namespace: {namespace or 'default'}")
        return

    # Confirmation prompt for multi-file ingests
    if not yes and len(files) > 1:
        if not click.confirm(f"Ingest {len(files)} files to namespace '{namespace or 'default'}'?"):
            console.print("Aborted.")
            return

    success = 0
    failed = 0
    skipped = 0
    total_chunks = 0

    if parallel > 1:
        # Parallel processing - each worker creates its own client
        file_args = [
            (fp, config, namespace,
             chunking_strategy if chunking_strategy != "auto" else "recursive",
             metadata, prepend_keys, base_path)
            for fp in files
        ]

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Ingesting...", total=len(files))

            with ThreadPoolExecutor(max_workers=parallel) as executor:
                # Submit all files
                future_to_file = {
                    executor.submit(ingest_file_worker, args): args[0]
                    for args in file_args
                }

                # Process results as they complete
                for future in as_completed(future_to_file):
                    filepath = future_to_file[future]

                    try:
                        result = future.result()

                        # Defer console output to main thread (thread-safe)
                        if 'message' in result:
                            console.print(result['message'])

                        if result['status'] == 'success':
                            success += 1
                            total_chunks += result.get('chunks', 0)
                        elif result['status'] == 'skipped':
                            skipped += 1
                        elif result['status'] == 'error':
                            failed += 1
                            if not skip_errors:
                                # Cancel remaining futures
                                for f in future_to_file:
                                    if not f.done():
                                        f.cancel()
                                console.print(f"[red]Error:[/red] Stopping due to error. Use --skip-errors to continue.")
                                # Print summary before exiting
                                _print_summary(success, failed, skipped, total_chunks, namespace)
                                ctx.exit(1)
                    except Exception as e:
                        failed += 1
                        console.print(f"[red]✗[/red] {filepath.name}: {e}")
                        if not skip_errors:
                            for f in future_to_file:
                                if not f.done():
                                    f.cancel()
                            console.print(f"[red]Error:[/red] Stopping due to error. Use --skip-errors to continue.")
                            # Print summary before exiting
                            _print_summary(success, failed, skipped, total_chunks, namespace)
                            ctx.exit(1)

                    progress.advance(task)
    else:
        # Sequential processing
        with StacheAPI(config) as client:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                task = progress.add_task("Ingesting...", total=len(files))

                for filepath in files:
                    progress.update(task, description=f"Processing {filepath.name}")

                    result = ingest_file(
                        client, registry, filepath, namespace,
                        chunking_strategy if chunking_strategy != "auto" else "recursive",
                        metadata, prepend_keys, base_path
                    )

                    # Print message from result
                    if 'message' in result:
                        console.print(result['message'])

                    if result['status'] == 'success':
                        success += 1
                        total_chunks += result.get('chunks', 0)
                    elif result['status'] == 'skipped':
                        skipped += 1
                    elif result['status'] == 'error':
                        failed += 1
                        if not skip_errors:
                            console.print(f"[red]Error:[/red] Stopping due to error. Use --skip-errors to continue.")
                            # Print summary before exiting
                            _print_summary(success, failed, skipped, total_chunks, namespace)
                            ctx.exit(1)

                    progress.advance(task)

    # Summary - always print
    _print_summary(success, failed, skipped, total_chunks, namespace)

    # Exit with appropriate code
    if failed > 0:
        ctx.exit(1)
    else:
        ctx.exit(0)
