"""Ingest command for uploading files to Stache."""

import json
import logging
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

# Terminal job statuses (mirrors the server's job contract)
TERMINAL_STATUSES = {"done", "skipped", "failed", "cancelled"}


def _finalize_job(job: dict, filepath: Path) -> dict:
    """Convert a terminal job dict into the legacy result dict shape.

    Returns a dict with status/chunks/message used by the summary logic.
    """
    status = job.get("status")
    if status in ("done", "skipped"):
        chunks = job.get("chunks_created", 0) or 0
        if status == "skipped":
            return {
                'status': 'skipped',
                'reason': job.get("error_detail") or "skipped",
                'filepath': filepath,
                'chunks': 0,
                'message': f"[yellow]○[/yellow] {filepath.name} (skipped)"
            }
        return {
            'status': 'success',
            'filepath': filepath,
            'chunks': chunks,
            'message': f"[green]✓[/green] {filepath.name} → {chunks} chunks"
        }
    # failed / cancelled
    reason = job.get("error_detail") or status or "failed"
    return {
        'status': 'error',
        'reason': reason,
        'filepath': filepath,
        'chunks': 0,
        'message': f"[red]✗[/red] {filepath.name}: {reason}"
    }


def ingest_file(
    client: StacheAPI,
    registry: LoaderRegistry,
    filepath: Path,
    namespace: str | None,
    chunking_strategy: str,
    metadata: dict | None,
    prepend_metadata: list[str] | None,
    base_path: Path | None = None,
    *,
    inline_max: int = 5_000_000,
    force_mode: str | None = None,
    wait: bool = True,
    async_mode: bool = False,
    poll_interval: float = 1.0,
    timeout: float = 600.0,
) -> dict:
    """Ingest a single file via the async job contract.

    Args:
        base_path: Optional base path to strip from source_path for portable identifiers
        inline_max: Size threshold (bytes); files above use presigned upload
        force_mode: "inline", "upload", or None (auto by size)
        wait: Poll the job until terminal
        async_mode: Submit only, return job_id without polling
        poll_interval: Initial poll interval
        timeout: Polling timeout

    Returns:
        dict with keys:
        - status: "success" | "skipped" | "error" | "submitted"
        - reason: str (for skipped/error)
        - chunks: int (for success)
        - filepath: Path
        - job_id: str (when submitted/async)
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
        import io

        with open(filepath, "rb") as f:
            raw_bytes = f.read()
        doc = loader.load(io.BytesIO(raw_bytes), filepath.name)

        # A loader that failed extraction (e.g. OCR with no tesseract) returns
        # empty text plus this marker; surface it as an error, not a silent skip
        if doc.metadata.get("extraction_failed"):
            reason = doc.metadata.get("ocr_error", "extraction failed")
            return {
                'status': 'error',
                'reason': reason,
                'filepath': filepath,
                'chunks': 0,
                'message': f"[red]✗[/red] {filepath.name}: {reason}"
            }

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
                abs_filepath = filepath.resolve()
                abs_basepath = base_path.resolve()
                source_path = str(abs_filepath.relative_to(abs_basepath))
            except ValueError:
                source_path = str(filepath)
        else:
            source_path = filepath.name

        # Merge metadata
        file_metadata = doc.metadata.copy()
        file_metadata["source_path"] = source_path
        file_metadata["filename"] = filepath.name
        if metadata:
            file_metadata.update(metadata)

        # Decide inline (submit text) vs presigned upload (raw bytes)
        if force_mode == "inline":
            use_upload = False
        elif force_mode == "upload":
            use_upload = True
        else:
            use_upload = len(raw_bytes) > inline_max

        if use_upload:
            presign = client.request_upload(
                filename=filepath.name,
                namespace=namespace,
                metadata=file_metadata,
            )
            client.upload_to_presigned(
                presign["upload_url"], raw_bytes, presign.get("required_headers")
            )
            job_id = presign["job_id"]
            job = presign
        else:
            job = client.submit_ingest(
                text=doc.text,
                namespace=namespace,
                filename=filepath.name,
                metadata=file_metadata,
                chunking_strategy=chunking_strategy,
                wait=wait and not async_mode,
            )
            job_id = job.get("job_id")

        # Async: submit only
        if async_mode:
            return {
                'status': 'submitted',
                'filepath': filepath,
                'chunks': 0,
                'job_id': job_id,
                'message': f"[cyan]→[/cyan] {filepath.name} submitted (job: {job_id})"
            }

        # If the submit response is already terminal (sync backend), use it.
        if job.get("status") in TERMINAL_STATUSES:
            return _finalize_job(job, filepath)

        # Otherwise poll until terminal.
        if not wait:
            return {
                'status': 'submitted',
                'filepath': filepath,
                'chunks': 0,
                'job_id': job_id,
                'message': f"[cyan]→[/cyan] {filepath.name} submitted (job: {job_id})"
            }

        final = client.wait_for_job(job_id, timeout=timeout, interval=poll_interval)
        return _finalize_job(final, filepath)

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
    (filepath, config, namespace, chunking_strategy, metadata, prepend_keys,
     base_path, inline_max, force_mode, wait, async_mode, poll_interval,
     timeout) = args

    with StacheAPI(config) as client:
        registry = LoaderRegistry()
        return ingest_file(
            client, registry, filepath, namespace,
            chunking_strategy, metadata, prepend_keys, base_path,
            inline_max=inline_max, force_mode=force_mode, wait=wait,
            async_mode=async_mode, poll_interval=poll_interval, timeout=timeout,
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
@click.option('--wait/--no-wait', default=True, help='Wait for jobs to finish (default: wait)')
@click.option('--poll-interval', default=1.0, type=float, help='Initial poll interval in seconds (default: 1.0)')
@click.option('--timeout', default=600.0, type=float, help='Polling timeout in seconds (default: 600)')
@click.option('--async', 'async_mode', is_flag=True, help='Submit jobs and print job IDs without polling')
@click.option('--inline-max', default=5_000_000, type=int,
              help='Size threshold in bytes; files above use presigned upload (default: 5000000)')
@click.option('--upload/--inline', 'force_upload', default=None,
              help='Force presigned upload (--upload) or inline submit (--inline); default: auto by size')
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
    wait: bool,
    poll_interval: float,
    timeout: float,
    async_mode: bool,
    inline_max: int,
    force_upload: bool | None,
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
      stache ingest big.pdf -n docs --async
    """
    if verbose:
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

    config = StacheConfig()

    # Translate tri-state --upload/--inline into a force_mode string
    if force_upload is True:
        force_mode = "upload"
    elif force_upload is False:
        force_mode = "inline"
    else:
        force_mode = None

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
        # Direct text ingestion via the job contract
        with StacheAPI(config) as client:
            try:
                job = client.submit_ingest(
                    text=text_input,
                    namespace=namespace,
                    metadata=metadata,
                    chunking_strategy=chunking_strategy if chunking_strategy != "auto" else "recursive",
                    wait=wait and not async_mode,
                )
                job_id = job.get("job_id")

                if async_mode:
                    console.print(f"[cyan]→[/cyan] Submitted text (job: {job_id})")
                    ctx.exit(0)

                if job.get("status") not in TERMINAL_STATUSES and wait:
                    job = client.wait_for_job(job_id, timeout=timeout, interval=poll_interval)
                elif job.get("status") not in TERMINAL_STATUSES:
                    console.print(f"[cyan]→[/cyan] Submitted text (job: {job_id})")
                    ctx.exit(0)

                if job.get("status") == "failed":
                    console.print(f"[red]✗[/red] Failed: {job.get('error_detail') or 'job failed'}")
                    ctx.exit(1)

                chunks = job.get("chunks_created", "?")
                doc_id = job.get("doc_id", job.get("document_id", "")) or ""
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

    effective_strategy = chunking_strategy if chunking_strategy != "auto" else "recursive"

    success = 0
    failed = 0
    skipped = 0
    submitted = 0
    total_chunks = 0

    def _account(result: dict) -> None:
        nonlocal success, failed, skipped, submitted, total_chunks
        if result['status'] == 'success':
            success += 1
            total_chunks += result.get('chunks', 0)
        elif result['status'] == 'skipped':
            skipped += 1
        elif result['status'] == 'submitted':
            submitted += 1
        elif result['status'] == 'error':
            failed += 1

    if parallel > 1:
        # Parallel processing - each worker creates its own client
        file_args = [
            (fp, config, namespace, effective_strategy, metadata, prepend_keys,
             base_path, inline_max, force_mode, wait, async_mode, poll_interval,
             timeout)
            for fp in files
        ]

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Ingesting...", total=len(files))

            with ThreadPoolExecutor(max_workers=parallel) as executor:
                future_to_file = {
                    executor.submit(ingest_file_worker, args): args[0]
                    for args in file_args
                }

                for future in as_completed(future_to_file):
                    filepath = future_to_file[future]

                    try:
                        result = future.result()

                        if 'message' in result:
                            console.print(result['message'])

                        _account(result)

                        if result['status'] == 'error' and not skip_errors:
                            for f in future_to_file:
                                if not f.done():
                                    f.cancel()
                            console.print(f"[red]Error:[/red] Stopping due to error. Use --skip-errors to continue.")
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

                    def _on_update(job, _fp=filepath):
                        progress.update(task, description=f"Processing {_fp.name} ({job.get('status', '')})")

                    result = ingest_file(
                        client, registry, filepath, namespace,
                        effective_strategy, metadata, prepend_keys, base_path,
                        inline_max=inline_max, force_mode=force_mode, wait=wait,
                        async_mode=async_mode, poll_interval=poll_interval,
                        timeout=timeout,
                    )

                    if 'message' in result:
                        console.print(result['message'])

                    _account(result)

                    if result['status'] == 'error' and not skip_errors:
                        console.print(f"[red]Error:[/red] Stopping due to error. Use --skip-errors to continue.")
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
