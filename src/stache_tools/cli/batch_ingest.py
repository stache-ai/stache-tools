"""Batch ingest command: embed JSONL via Cohere API, load into S3 Vectors + DynamoDB."""

import json
import logging
import os
import sys
import tempfile
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import click
from rich.console import Console

logger = logging.getLogger(__name__)
console = Console()


def read_jsonl(filepath: Path) -> list[dict]:
    """Parse and validate JSONL file, skip empty text."""
    records = []
    with open(filepath) as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as e:
                raise click.ClickException(f"Invalid JSON on line {line_num}: {e}")

            text = record.get("text", "").strip()
            if not text:
                logger.debug(f"Skipping line {line_num}: empty text")
                continue

            records.append(record)

    if not records:
        raise click.ClickException("No valid records with text found in JSONL file")

    return records


def prep_and_submit(co, records: list[dict], model: str) -> str:
    """Write temp JSONL, create Cohere dataset, submit embed job, return job_id."""
    # Write Cohere-format JSONL (just {"text": ...} per line)
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".jsonl", delete=False, prefix="stache_batch_"
    ) as f:
        for record in records:
            json.dump({"text": record["text"]}, f)
            f.write("\n")
        tmp_path = f.name

    try:
        console.print(f"Uploading {len(records)} records as Cohere dataset...")

        # Create dataset from JSONL file
        with open(tmp_path, "rb") as data_file:
            dataset = co.datasets.create(
                name=f"stache-batch-{int(time.time())}",
                type="embed-input",
                data=data_file,
            )
        dataset_id = dataset.id

        console.print(f"Dataset created: {dataset_id}")

        # Wait for dataset validation
        ds = co.wait(dataset)
        if ds.validation_status != "validated":
            raise click.ClickException(
                f"Dataset validation failed: {ds.validation_status}"
            )

        # Submit embed job
        job = co.embed_jobs.create(
            dataset_id=dataset_id,
            input_type="search_document",
            model=model,
            embedding_types=["float"],
        )

        console.print(f"Embed job submitted: {job.id}")
        return job.id
    finally:
        os.unlink(tmp_path)


def poll_job(co, job_id: str, interval: int) -> None:
    """Poll embed job until complete or failed."""
    from rich.progress import SpinnerColumn, TextColumn, Progress

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Waiting for embeddings...", total=None)

        while True:
            job = co.embed_jobs.get(id=job_id)
            status = job.status

            if status == "complete":
                progress.update(task, description="[green]Embeddings complete!")
                return
            elif status == "failed":
                raise click.ClickException(f"Embed job failed: {job}")
            elif status == "cancelling" or status == "cancelled":
                raise click.ClickException(f"Embed job cancelled")

            progress.update(task, description=f"Embedding... (status: {status})")
            time.sleep(interval)


def download_embeddings(co, job_id: str) -> list[list[float]]:
    """Fetch embeddings from completed job."""
    import cohere as cohere_module

    job = co.embed_jobs.get(id=job_id)
    if not job.output_dataset_id:
        raise click.ClickException(f"Embed job {job_id} has no output dataset")

    output_response = co.datasets.get(id=job.output_dataset_id)
    dataset = output_response.dataset

    embeddings = []
    for record in cohere_module.utils.dataset_generator(dataset):
        record_embeddings = record.get("embeddings")
        if record_embeddings and isinstance(record_embeddings, dict):
            floats = record_embeddings.get("float")
            if floats is not None:
                embeddings.append(floats)
                continue
        # Fallback for older SDK versions
        embedding = record.get("embedding")
        if embedding is not None:
            embeddings.append(embedding)
        else:
            raise click.ClickException(
                f"Could not extract embedding from record: {list(record.keys())}"
            )

    console.print(f"Downloaded {len(embeddings)} embeddings")
    return embeddings


def build_vectors(
    records: list[dict],
    embeddings: list[list[float]],
    dimension: int,
    namespace_override: str | None,
) -> tuple[list[dict], list[dict]]:
    """Build S3 Vectors records and DynamoDB document items.

    UUID generation matches Lambda batch logic exactly:
    - doc UUID: uuid5(NAMESPACE_URL, f"{namespace}:{jsonl_doc_id}")
    - vector UUID: uuid5(NAMESPACE_URL, f"{doc_id}:{chunk_index}")

    Returns:
        (vectors, doc_items) - S3 Vectors records and DynamoDB items
    """
    if len(embeddings) != len(records):
        raise click.ClickException(
            f"Embedding count ({len(embeddings)}) != record count ({len(records)})"
        )

    now = datetime.now(timezone.utc).isoformat()
    vectors = []
    doc_chunks = defaultdict(list)

    # Pre-compute doc UUIDs and chunk counts
    doc_chunk_counts = defaultdict(int)
    doc_uuid_map = {}
    for record in records:
        jsonl_doc_id = record.get("doc_id", "unknown")
        ns = namespace_override or record.get("namespace", "default")
        doc_chunk_counts[jsonl_doc_id] += 1

        if jsonl_doc_id not in doc_uuid_map:
            doc_uuid_map[jsonl_doc_id] = str(
                uuid.uuid5(uuid.NAMESPACE_URL, f"{ns}:{jsonl_doc_id}")
            )

    reserved_keys = {"text", "namespace", "doc_id", "chunk_index", "filename", "total_chunks"}

    for i, (embedding, record) in enumerate(zip(embeddings, records)):
        if len(embedding) != dimension:
            raise click.ClickException(
                f"Embedding dimension {len(embedding)} != expected {dimension}"
            )

        ns = namespace_override or record.get("namespace", "default")
        jsonl_doc_id = record.get("doc_id", "unknown")
        doc_id = doc_uuid_map[jsonl_doc_id]
        chunk_index = record.get("chunk_index", i)
        doc_filename = record.get("filename", "unknown")

        vector_uuid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{doc_id}:{chunk_index}"))

        chunk_metadata = {k: v for k, v in record.items() if k not in reserved_keys}

        metadata = {
            "text": record["text"],
            "namespace": ns,
            "doc_id": doc_id,
            "chunk_index": chunk_index,
            "total_chunks": doc_chunk_counts[jsonl_doc_id],
            "created_at": now,
            "filename": doc_filename,
            "status": "active",
            **chunk_metadata,
        }

        vectors.append({
            "key": vector_uuid,
            "data": {"float32": embedding},
            "metadata": metadata,
        })

        doc_chunks[doc_id].append((vector_uuid, chunk_index))

    # Build DynamoDB document items
    jsonl_doc_metadata_map = {}
    for record in records:
        jsonl_doc_id = record.get("doc_id", "unknown")
        if jsonl_doc_id not in jsonl_doc_metadata_map:
            jsonl_doc_metadata_map[jsonl_doc_id] = record

    doc_items = []
    for doc_id, chunk_list in doc_chunks.items():
        chunk_list.sort(key=lambda x: x[1])
        chunk_ids = [c[0] for c in chunk_list]

        # Reverse-map doc_id to jsonl_doc_id
        jsonl_doc_id = None
        for jdid, uuid_val in doc_uuid_map.items():
            if uuid_val == doc_id:
                jsonl_doc_id = jdid
                break

        orig = jsonl_doc_metadata_map.get(jsonl_doc_id, {})
        ns = namespace_override or orig.get("namespace", "default")
        doc_filename = orig.get("filename", "unknown")

        doc_extra_metadata = {k: v for k, v in orig.items() if k not in reserved_keys}

        doc_items.append({
            "PK": f"DOC#{ns}#{doc_id}",
            "SK": "METADATA",
            "GSI1PK": f"NAMESPACE#{ns}",
            "GSI1SK": f"CREATED#{now}",
            "GSI2PK": f"FILENAME#{ns}#{doc_filename}",
            "GSI2SK": f"CREATED#{now}",
            "doc_id": doc_id,
            "filename": doc_filename,
            "namespace": ns,
            "chunk_ids": chunk_ids,
            "chunk_count": len(chunk_ids),
            "status": "active",
            "created_at": now,
            "metadata": doc_extra_metadata,
        })

    return vectors, doc_items


def sanitize_for_dynamodb(obj):
    """Recursively convert floats to Decimal and remove None values for DynamoDB."""
    if isinstance(obj, dict):
        return {k: sanitize_for_dynamodb(v) for k, v in obj.items() if v is not None}
    elif isinstance(obj, list):
        return [sanitize_for_dynamodb(item) for item in obj]
    elif isinstance(obj, float):
        return Decimal(str(obj))
    else:
        return obj


def insert_vectors(s3v, bucket: str, index: str, vectors: list[dict], batch_size: int,
                   skip_errors: bool) -> int:
    """Batch insert vectors into S3 Vectors with retry + exponential backoff."""
    from botocore.exceptions import ClientError
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, MofNCompleteColumn

    total_inserted = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Inserting vectors...", total=len(vectors))

        for batch_start in range(0, len(vectors), batch_size):
            batch = vectors[batch_start:batch_start + batch_size]
            max_retries = 5

            for attempt in range(max_retries):
                try:
                    s3v.put_vectors(
                        vectorBucketName=bucket,
                        indexName=index,
                        vectors=batch,
                    )
                    total_inserted += len(batch)
                    progress.advance(task, len(batch))
                    break
                except ClientError as e:
                    error_code = e.response.get("Error", {}).get("Code", "")
                    if error_code in ("ThrottlingException", "TooManyRequestsException"):
                        if attempt < max_retries - 1:
                            sleep_time = 0.5 * (2 ** attempt)
                            logger.warning(
                                f"Throttled, retrying in {sleep_time}s "
                                f"(attempt {attempt + 1}/{max_retries})"
                            )
                            time.sleep(sleep_time)
                        else:
                            if skip_errors:
                                logger.error(f"Failed batch at offset {batch_start}: {e}")
                                progress.advance(task, len(batch))
                                break
                            raise
                    else:
                        if skip_errors:
                            logger.error(f"Failed batch at offset {batch_start}: {e}")
                            progress.advance(task, len(batch))
                            break
                        raise

    return total_inserted


def write_dynamo_docs(table, doc_items: list[dict]) -> int:
    """Write document index entries to DynamoDB via batch_writer."""
    written = 0
    with table.batch_writer() as batch:
        for item in doc_items:
            sanitized = sanitize_for_dynamodb(item)
            batch.put_item(Item=sanitized)
            written += 1
    return written


@click.command("batch-ingest")
@click.argument("jsonl_file", type=click.Path(exists=True, path_type=Path))
@click.option("-n", "--namespace", help="Override namespace for all records")
@click.option("--cohere-api-key", envvar="COHERE_API_KEY", help="Cohere API key")
@click.option("--s3vectors-bucket", envvar="S3VECTORS_BUCKET", help="S3 Vectors bucket")
@click.option("--s3vectors-index", envvar="S3VECTORS_INDEX", help="S3 Vectors index")
@click.option("--documents-table", envvar="DOCUMENTS_TABLE", help="DynamoDB documents table")
@click.option("--model", default="embed-english-v3.0", help="Cohere model (default: embed-english-v3.0)")
@click.option("--dimension", default=1024, type=int, help="Embedding dimension (default: 1024)")
@click.option("--batch-size", default=500, type=int, help="S3 Vectors batch size (default: 500)")
@click.option("--poll-interval", default=30, type=int, help="Seconds between polls (default: 30)")
@click.option("--dry-run", is_flag=True, help="Show stats without running")
@click.option("--skip-errors", is_flag=True, help="Continue on vector insertion errors")
@click.option("--region", default="us-east-1", help="AWS region (default: us-east-1)")
@click.option("-v", "--verbose", is_flag=True, help="Debug logging")
@click.pass_context
def batch_ingest(
    ctx: click.Context,
    jsonl_file: Path,
    namespace: str | None,
    cohere_api_key: str | None,
    s3vectors_bucket: str | None,
    s3vectors_index: str | None,
    documents_table: str | None,
    model: str,
    dimension: int,
    batch_size: int,
    poll_interval: int,
    dry_run: bool,
    skip_errors: bool,
    region: str,
    verbose: bool,
) -> None:
    """Batch embed a JSONL file via Cohere and load into S3 Vectors + DynamoDB.

    Reads a local JSONL file where each line has at minimum a "text" field.
    Submits all texts to Cohere's batch embed API, polls for completion,
    then bulk-inserts vectors into S3 Vectors and document entries into DynamoDB.

    \b
    JSONL record format:
      {"text": "...", "doc_id": "ch1", "namespace": "bible", "filename": "genesis.txt", ...}

    Required fields: text
    Optional fields: doc_id, namespace, filename, chunk_index, plus any custom metadata.

    \b
    Examples:
      stache batch-ingest bible.jsonl --namespace bible
      stache batch-ingest data.jsonl --dry-run
      stache batch-ingest chunks.jsonl -n docs --batch-size 250 --poll-interval 15
    """
    if verbose:
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )

    # Step 1: Read and validate JSONL (before lazy imports so dry-run works without cohere)
    console.print(f"Reading {jsonl_file}...")
    records = read_jsonl(jsonl_file)

    # Compute stats
    namespaces = set()
    doc_ids = set()
    for r in records:
        ns = namespace or r.get("namespace", "default")
        namespaces.add(ns)
        doc_ids.add(r.get("doc_id", "unknown"))

    console.print(f"  Records: {len(records)}")
    console.print(f"  Documents: {len(doc_ids)}")
    console.print(f"  Namespaces: {', '.join(sorted(namespaces))}")

    if dry_run:
        console.print("\n[bold]Dry Run[/bold] — no changes made.")
        ctx.exit(0)

    # Validate required config (after dry-run so dry-run doesn't need credentials)
    if not cohere_api_key:
        console.print("[red]Cohere API key required (--cohere-api-key or COHERE_API_KEY env)[/red]")
        ctx.exit(1)
    if not s3vectors_bucket:
        console.print("[red]S3 Vectors bucket required (--s3vectors-bucket or S3VECTORS_BUCKET env)[/red]")
        ctx.exit(1)
    if not s3vectors_index:
        console.print("[red]S3 Vectors index required (--s3vectors-index or S3VECTORS_INDEX env)[/red]")
        ctx.exit(1)
    if not documents_table:
        console.print("[red]DynamoDB table required (--documents-table or DOCUMENTS_TABLE env)[/red]")
        ctx.exit(1)

    # Lazy import cohere and boto3
    try:
        import cohere  # noqa: F811
    except ImportError:
        console.print(
            "[red]cohere package required for batch-ingest.[/red]\n"
            "Install with: pip install 'stache-tools[batch]'"
        )
        ctx.exit(1)

    try:
        import boto3
    except ImportError:
        console.print(
            "[red]boto3 package required for batch-ingest.[/red]\n"
            "Install with: pip install 'stache-tools[batch]'"
        )
        ctx.exit(1)

    # Step 2: Submit to Cohere
    co = cohere.ClientV2(api_key=cohere_api_key)
    job_id = prep_and_submit(co, records, model)

    # Step 3: Poll until complete
    poll_job(co, job_id, poll_interval)

    # Step 4: Download embeddings
    embeddings = download_embeddings(co, job_id)

    # Step 5: Build vectors and doc items
    console.print("Building vectors and document index entries...")
    vectors, doc_items = build_vectors(records, embeddings, dimension, namespace)

    # Step 6: Insert vectors into S3 Vectors
    s3v = boto3.client("s3vectors", region_name=region)
    inserted = insert_vectors(s3v, s3vectors_bucket, s3vectors_index, vectors, batch_size, skip_errors)

    # Step 7: Write DynamoDB document index
    dynamodb = boto3.resource("dynamodb", region_name=region)
    table = dynamodb.Table(documents_table)
    docs_written = write_dynamo_docs(table, doc_items)

    # Step 8: Summary
    failed = len(vectors) - inserted
    console.print()
    console.print(f"[bold]{'='*50}[/bold]")
    console.print("[bold]Batch Ingest Complete[/bold]")
    console.print(f"  Vectors inserted: {inserted}")
    if failed > 0:
        console.print(f"  [red]Vectors FAILED: {failed}[/red] (see log for batch offsets)")
    console.print(f"  Documents created: {docs_written}")
    console.print(f"  Namespaces: {', '.join(sorted(namespaces))}")
    console.print(f"  Cohere job: {job_id}")
    console.print(f"[bold]{'='*50}[/bold]")

    # Exit non-zero when any batch failed so scripts/CI see the failure,
    # matching the ingest command's --skip-errors behavior
    ctx.exit(1 if failed > 0 else 0)
