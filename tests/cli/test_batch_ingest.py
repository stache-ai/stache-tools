"""Comprehensive tests for the batch-ingest CLI command."""

import json
import uuid
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch, call

import pytest
from click.testing import CliRunner

from stache_tools.cli.batch_ingest import (
    read_jsonl,
    build_vectors,
    sanitize_for_dynamodb,
    insert_vectors,
    write_dynamo_docs,
    batch_ingest,
)


@pytest.fixture
def runner():
    """Create Click CLI runner."""
    return CliRunner()


@pytest.fixture
def sample_records():
    """Sample JSONL records for testing."""
    return [
        {"text": "First chunk of text", "doc_id": "doc1", "namespace": "test-ns", "filename": "doc1.txt", "chunk_index": 0},
        {"text": "Second chunk of text", "doc_id": "doc1", "namespace": "test-ns", "filename": "doc1.txt", "chunk_index": 1},
        {"text": "Another document", "doc_id": "doc2", "namespace": "test-ns", "filename": "doc2.txt", "chunk_index": 0},
    ]


@pytest.fixture
def sample_embeddings():
    """Sample embeddings matching sample_records (dimension=4 for brevity)."""
    return [
        [0.1, 0.2, 0.3, 0.4],
        [0.5, 0.6, 0.7, 0.8],
        [0.9, 1.0, 1.1, 1.2],
    ]


@pytest.fixture
def jsonl_file(tmp_path, sample_records):
    """Write sample records to a JSONL file."""
    filepath = tmp_path / "test.jsonl"
    with open(filepath, "w") as f:
        for record in sample_records:
            json.dump(record, f)
            f.write("\n")
    return filepath


# ==================== read_jsonl ====================


class TestReadJsonl:
    """Tests for read_jsonl function."""

    def test_valid_file(self, jsonl_file, sample_records):
        """Parses valid JSONL file correctly."""
        records = read_jsonl(jsonl_file)
        assert len(records) == 3
        assert records[0]["text"] == "First chunk of text"
        assert records[2]["doc_id"] == "doc2"

    def test_skips_empty_text(self, tmp_path):
        """Records with empty/whitespace text are skipped."""
        filepath = tmp_path / "test.jsonl"
        with open(filepath, "w") as f:
            f.write('{"text": "valid text", "doc_id": "d1"}\n')
            f.write('{"text": "", "doc_id": "d2"}\n')
            f.write('{"text": "   ", "doc_id": "d3"}\n')
            f.write('{"text": "also valid", "doc_id": "d4"}\n')
        records = read_jsonl(filepath)
        assert len(records) == 2
        assert records[0]["doc_id"] == "d1"
        assert records[1]["doc_id"] == "d4"

    def test_skips_blank_lines(self, tmp_path):
        """Blank lines in JSONL are ignored."""
        filepath = tmp_path / "test.jsonl"
        with open(filepath, "w") as f:
            f.write('{"text": "hello"}\n')
            f.write("\n")
            f.write('{"text": "world"}\n')
        records = read_jsonl(filepath)
        assert len(records) == 2

    def test_invalid_json_raises(self, tmp_path):
        """Invalid JSON raises ClickException with line number."""
        filepath = tmp_path / "test.jsonl"
        with open(filepath, "w") as f:
            f.write('{"text": "valid"}\n')
            f.write("not json at all\n")

        from click import ClickException
        with pytest.raises(ClickException, match="Invalid JSON on line 2"):
            read_jsonl(filepath)

    def test_empty_file_raises(self, tmp_path):
        """File with no valid records raises ClickException."""
        filepath = tmp_path / "empty.jsonl"
        filepath.write_text("")

        from click import ClickException
        with pytest.raises(ClickException, match="No valid records"):
            read_jsonl(filepath)

    def test_all_empty_text_raises(self, tmp_path):
        """File where all records have empty text raises ClickException."""
        filepath = tmp_path / "test.jsonl"
        with open(filepath, "w") as f:
            f.write('{"text": ""}\n')
            f.write('{"text": "  "}\n')

        from click import ClickException
        with pytest.raises(ClickException, match="No valid records"):
            read_jsonl(filepath)

    def test_missing_text_field_skipped(self, tmp_path):
        """Records without text field are skipped (empty text default)."""
        filepath = tmp_path / "test.jsonl"
        with open(filepath, "w") as f:
            f.write('{"doc_id": "no-text"}\n')
            f.write('{"text": "has text"}\n')
        records = read_jsonl(filepath)
        assert len(records) == 1
        assert records[0]["text"] == "has text"


# ==================== build_vectors ====================


class TestBuildVectors:
    """Tests for build_vectors function."""

    def test_uuid5_determinism(self, sample_records, sample_embeddings):
        """UUIDs are deterministic based on namespace:doc_id and doc_id:chunk_index."""
        vectors1, docs1 = build_vectors(sample_records, sample_embeddings, 4, None)
        vectors2, docs2 = build_vectors(sample_records, sample_embeddings, 4, None)

        # Same input produces same UUIDs
        assert [v["key"] for v in vectors1] == [v["key"] for v in vectors2]
        assert [d["doc_id"] for d in docs1] == [d["doc_id"] for d in docs2]

    def test_doc_uuid_formula(self, sample_records, sample_embeddings):
        """Doc UUID = uuid5(NAMESPACE_URL, f"{namespace}:{jsonl_doc_id}")."""
        vectors, docs = build_vectors(sample_records, sample_embeddings, 4, None)

        expected_doc1_uuid = str(uuid.uuid5(uuid.NAMESPACE_URL, "test-ns:doc1"))
        expected_doc2_uuid = str(uuid.uuid5(uuid.NAMESPACE_URL, "test-ns:doc2"))

        # Check vectors have correct doc_id
        assert vectors[0]["metadata"]["doc_id"] == expected_doc1_uuid
        assert vectors[1]["metadata"]["doc_id"] == expected_doc1_uuid
        assert vectors[2]["metadata"]["doc_id"] == expected_doc2_uuid

    def test_vector_uuid_formula(self, sample_records, sample_embeddings):
        """Vector UUID = uuid5(NAMESPACE_URL, f"{doc_id}:{chunk_index}")."""
        vectors, _ = build_vectors(sample_records, sample_embeddings, 4, None)

        doc1_uuid = str(uuid.uuid5(uuid.NAMESPACE_URL, "test-ns:doc1"))
        expected_vec0 = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{doc1_uuid}:0"))
        expected_vec1 = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{doc1_uuid}:1"))

        assert vectors[0]["key"] == expected_vec0
        assert vectors[1]["key"] == expected_vec1

    def test_namespace_override(self, sample_records, sample_embeddings):
        """Namespace override replaces per-record namespace."""
        vectors, docs = build_vectors(sample_records, sample_embeddings, 4, "override-ns")

        # All vectors should have overridden namespace
        for v in vectors:
            assert v["metadata"]["namespace"] == "override-ns"

        # Doc UUID should use override namespace
        expected_doc1_uuid = str(uuid.uuid5(uuid.NAMESPACE_URL, "override-ns:doc1"))
        assert vectors[0]["metadata"]["doc_id"] == expected_doc1_uuid

        # DynamoDB items should use override namespace
        for doc in docs:
            assert doc["namespace"] == "override-ns"
            assert doc["PK"].startswith("DOC#override-ns#")
            assert doc["GSI1PK"] == "NAMESPACE#override-ns"

    def test_default_namespace(self, sample_embeddings):
        """Records without namespace use 'default'."""
        records = [{"text": "hello", "doc_id": "d1"}]
        embeddings = [sample_embeddings[0]]
        vectors, docs = build_vectors(records, embeddings, 4, None)

        assert vectors[0]["metadata"]["namespace"] == "default"
        expected_uuid = str(uuid.uuid5(uuid.NAMESPACE_URL, "default:d1"))
        assert vectors[0]["metadata"]["doc_id"] == expected_uuid

    def test_dimension_mismatch_raises(self, sample_records):
        """Raises ClickException when embedding dimension doesn't match."""
        bad_embeddings = [[0.1, 0.2]] * 3  # dimension 2, not 4

        from click import ClickException
        with pytest.raises(ClickException, match="Embedding dimension 2 != expected 4"):
            build_vectors(sample_records, bad_embeddings, 4, None)

    def test_count_mismatch_raises(self, sample_records, sample_embeddings):
        """Raises ClickException when embedding count != record count."""
        from click import ClickException
        with pytest.raises(ClickException, match="Embedding count.*!= record count"):
            build_vectors(sample_records, sample_embeddings[:2], 4, None)

    def test_metadata_passthrough(self, sample_embeddings):
        """Custom metadata fields pass through to vector metadata."""
        records = [
            {"text": "hello", "doc_id": "d1", "namespace": "ns", "filename": "f.txt",
             "author": "Jane", "topic": "testing", "priority": 5},
        ]
        vectors, docs = build_vectors(records, [sample_embeddings[0]], 4, None)

        meta = vectors[0]["metadata"]
        assert meta["author"] == "Jane"
        assert meta["topic"] == "testing"
        assert meta["priority"] == 5

    def test_reserved_keys_excluded_from_custom_metadata(self, sample_embeddings):
        """Reserved keys (text, namespace, doc_id, etc.) not duplicated in custom metadata."""
        records = [
            {"text": "hello", "doc_id": "d1", "namespace": "ns",
             "filename": "f.txt", "chunk_index": 0, "total_chunks": 1,
             "custom_field": "keep_me"},
        ]
        vectors, _ = build_vectors(records, [sample_embeddings[0]], 4, None)

        meta = vectors[0]["metadata"]
        # These should be set by build_vectors, not from custom passthrough
        assert meta["text"] == "hello"
        assert meta["custom_field"] == "keep_me"

    def test_total_chunks_computed(self, sample_records, sample_embeddings):
        """total_chunks is computed per doc_id."""
        vectors, _ = build_vectors(sample_records, sample_embeddings, 4, None)

        # doc1 has 2 chunks
        assert vectors[0]["metadata"]["total_chunks"] == 2
        assert vectors[1]["metadata"]["total_chunks"] == 2
        # doc2 has 1 chunk
        assert vectors[2]["metadata"]["total_chunks"] == 1

    def test_dynamo_doc_items_structure(self, sample_records, sample_embeddings):
        """DynamoDB document items have correct structure."""
        _, docs = build_vectors(sample_records, sample_embeddings, 4, None)

        assert len(docs) == 2  # Two unique doc_ids

        doc1 = next(d for d in docs if d["filename"] == "doc1.txt")
        assert doc1["chunk_count"] == 2
        assert len(doc1["chunk_ids"]) == 2
        assert doc1["status"] == "active"
        assert doc1["SK"] == "METADATA"
        assert "created_at" in doc1

    def test_embedding_data_format(self, sample_records, sample_embeddings):
        """Vectors contain embedding in float32 format."""
        vectors, _ = build_vectors(sample_records, sample_embeddings, 4, None)

        for v, emb in zip(vectors, sample_embeddings):
            assert v["data"] == {"float32": emb}

    def test_default_doc_id_and_filename(self, sample_embeddings):
        """Records without doc_id/filename default to 'unknown'."""
        records = [{"text": "bare minimum"}]
        vectors, docs = build_vectors(records, [sample_embeddings[0]], 4, None)

        assert vectors[0]["metadata"]["filename"] == "unknown"
        expected_uuid = str(uuid.uuid5(uuid.NAMESPACE_URL, "default:unknown"))
        assert vectors[0]["metadata"]["doc_id"] == expected_uuid


# ==================== sanitize_for_dynamodb ====================


class TestSanitizeForDynamodb:
    """Tests for sanitize_for_dynamodb function."""

    def test_float_to_decimal(self):
        """Floats are converted to Decimal."""
        result = sanitize_for_dynamodb({"score": 0.95})
        assert result["score"] == Decimal("0.95")
        assert isinstance(result["score"], Decimal)

    def test_none_removal(self):
        """None values are removed from dicts."""
        result = sanitize_for_dynamodb({"keep": "yes", "remove": None})
        assert "keep" in result
        assert "remove" not in result

    def test_nested_dict(self):
        """Handles nested dictionaries."""
        result = sanitize_for_dynamodb({
            "outer": {
                "float_val": 1.5,
                "none_val": None,
                "string_val": "hello",
            }
        })
        assert result["outer"]["float_val"] == Decimal("1.5")
        assert "none_val" not in result["outer"]
        assert result["outer"]["string_val"] == "hello"

    def test_nested_list(self):
        """Handles lists containing dicts and floats."""
        result = sanitize_for_dynamodb([
            {"val": 0.5, "empty": None},
            1.23,
            "string",
            42,
        ])
        assert result[0]["val"] == Decimal("0.5")
        assert "empty" not in result[0]
        assert result[1] == Decimal("1.23")
        assert result[2] == "string"
        assert result[3] == 42

    def test_passthrough_types(self):
        """Strings, ints, bools pass through unchanged."""
        result = sanitize_for_dynamodb({
            "str": "hello",
            "int": 42,
            "bool": True,
        })
        assert result == {"str": "hello", "int": 42, "bool": True}

    def test_deeply_nested(self):
        """Handles deeply nested structures."""
        result = sanitize_for_dynamodb({
            "a": {"b": {"c": {"val": 3.14, "nope": None}}}
        })
        assert result["a"]["b"]["c"]["val"] == Decimal("3.14")
        assert "nope" not in result["a"]["b"]["c"]


# ==================== insert_vectors ====================


class TestInsertVectors:
    """Tests for insert_vectors function."""

    def _make_vectors(self, count, dim=4):
        """Helper to create vector records."""
        return [
            {
                "key": f"vec-{i}",
                "data": {"float32": [0.1] * dim},
                "metadata": {"text": f"chunk {i}"},
            }
            for i in range(count)
        ]

    @patch("stache_tools.cli.batch_ingest.time.sleep")
    def test_batching(self, mock_sleep):
        """Vectors are inserted in batches of specified size."""
        s3v = MagicMock()
        vectors = self._make_vectors(7)

        inserted = insert_vectors(s3v, "bucket", "index", vectors, batch_size=3, skip_errors=False)

        assert inserted == 7
        assert s3v.put_vectors.call_count == 3  # 3 + 3 + 1

        # Verify batch sizes
        calls = s3v.put_vectors.call_args_list
        assert len(calls[0][1]["vectors"]) == 3
        assert len(calls[1][1]["vectors"]) == 3
        assert len(calls[2][1]["vectors"]) == 1

    @patch("stache_tools.cli.batch_ingest.time.sleep")
    def test_retry_on_throttling(self, mock_sleep):
        """Retries with exponential backoff on ThrottlingException."""
        from botocore.exceptions import ClientError

        s3v = MagicMock()
        throttle_error = ClientError(
            {"Error": {"Code": "ThrottlingException", "Message": "slow down"}},
            "PutVectors",
        )
        # Fail twice, then succeed
        s3v.put_vectors.side_effect = [throttle_error, throttle_error, None]
        vectors = self._make_vectors(2)

        inserted = insert_vectors(s3v, "bucket", "index", vectors, batch_size=10, skip_errors=False)

        assert inserted == 2
        assert s3v.put_vectors.call_count == 3
        # Check backoff sleep calls
        assert mock_sleep.call_count == 2
        mock_sleep.assert_any_call(0.5)   # 0.5 * 2^0
        mock_sleep.assert_any_call(1.0)   # 0.5 * 2^1

    @patch("stache_tools.cli.batch_ingest.time.sleep")
    def test_skip_errors_continues(self, mock_sleep):
        """With skip_errors=True, continues past non-throttle errors."""
        from botocore.exceptions import ClientError

        s3v = MagicMock()
        error = ClientError(
            {"Error": {"Code": "ValidationException", "Message": "bad data"}},
            "PutVectors",
        )
        # First batch fails, second succeeds
        s3v.put_vectors.side_effect = [error, None]
        vectors = self._make_vectors(4)

        inserted = insert_vectors(s3v, "bucket", "index", vectors, batch_size=2, skip_errors=True)

        # Only second batch counted as inserted
        assert inserted == 2
        assert s3v.put_vectors.call_count == 2

    @patch("stache_tools.cli.batch_ingest.time.sleep")
    def test_non_throttle_error_raises_without_skip(self, mock_sleep):
        """Non-throttle errors raise when skip_errors=False."""
        from botocore.exceptions import ClientError

        s3v = MagicMock()
        error = ClientError(
            {"Error": {"Code": "ValidationException", "Message": "bad"}},
            "PutVectors",
        )
        s3v.put_vectors.side_effect = error
        vectors = self._make_vectors(2)

        with pytest.raises(ClientError):
            insert_vectors(s3v, "bucket", "index", vectors, batch_size=10, skip_errors=False)

    @patch("stache_tools.cli.batch_ingest.time.sleep")
    def test_throttle_exhausts_retries_raises(self, mock_sleep):
        """Raises after exhausting all retries on throttling without skip_errors."""
        from botocore.exceptions import ClientError

        s3v = MagicMock()
        throttle_error = ClientError(
            {"Error": {"Code": "ThrottlingException", "Message": "slow down"}},
            "PutVectors",
        )
        s3v.put_vectors.side_effect = throttle_error
        vectors = self._make_vectors(2)

        with pytest.raises(ClientError):
            insert_vectors(s3v, "bucket", "index", vectors, batch_size=10, skip_errors=False)

        assert s3v.put_vectors.call_count == 5  # max_retries = 5

    @patch("stache_tools.cli.batch_ingest.time.sleep")
    def test_throttle_exhausts_retries_skip_errors(self, mock_sleep):
        """With skip_errors, logs and continues after exhausting retries."""
        from botocore.exceptions import ClientError

        s3v = MagicMock()
        throttle_error = ClientError(
            {"Error": {"Code": "ThrottlingException", "Message": "slow down"}},
            "PutVectors",
        )
        s3v.put_vectors.side_effect = throttle_error
        vectors = self._make_vectors(2)

        inserted = insert_vectors(s3v, "bucket", "index", vectors, batch_size=10, skip_errors=True)

        assert inserted == 0
        assert s3v.put_vectors.call_count == 5

    @patch("stache_tools.cli.batch_ingest.time.sleep")
    def test_empty_vectors(self, mock_sleep):
        """No-op for empty vector list."""
        s3v = MagicMock()
        inserted = insert_vectors(s3v, "bucket", "index", [], batch_size=10, skip_errors=False)

        assert inserted == 0
        s3v.put_vectors.assert_not_called()


# ==================== write_dynamo_docs ====================


class TestWriteDynamoDocs:
    """Tests for write_dynamo_docs function."""

    def test_batch_writer_usage(self):
        """Uses batch_writer context manager and put_item for each doc."""
        mock_table = MagicMock()
        mock_batch = MagicMock()
        mock_table.batch_writer.return_value.__enter__ = Mock(return_value=mock_batch)
        mock_table.batch_writer.return_value.__exit__ = Mock(return_value=False)

        doc_items = [
            {"PK": "DOC#ns#id1", "SK": "METADATA", "score": 0.95, "empty": None},
            {"PK": "DOC#ns#id2", "SK": "METADATA", "count": 3},
        ]

        written = write_dynamo_docs(mock_table, doc_items)

        assert written == 2
        assert mock_batch.put_item.call_count == 2
        mock_table.batch_writer.assert_called_once()

    def test_sanitizes_items(self):
        """Items are sanitized (floats to Decimal, None removed) before writing."""
        mock_table = MagicMock()
        mock_batch = MagicMock()
        mock_table.batch_writer.return_value.__enter__ = Mock(return_value=mock_batch)
        mock_table.batch_writer.return_value.__exit__ = Mock(return_value=False)

        doc_items = [{"PK": "DOC#ns#id", "score": 0.5, "nothing": None}]
        write_dynamo_docs(mock_table, doc_items)

        written_item = mock_batch.put_item.call_args[1]["Item"]
        assert written_item["score"] == Decimal("0.5")
        assert "nothing" not in written_item

    def test_empty_list(self):
        """Returns 0 for empty doc list."""
        mock_table = MagicMock()
        mock_batch = MagicMock()
        mock_table.batch_writer.return_value.__enter__ = Mock(return_value=mock_batch)
        mock_table.batch_writer.return_value.__exit__ = Mock(return_value=False)

        written = write_dynamo_docs(mock_table, [])
        assert written == 0
        mock_batch.put_item.assert_not_called()


# ==================== CLI batch_ingest command ====================


class TestBatchIngestCLI:
    """Tests for the batch_ingest Click command."""

    def test_help_without_dependencies(self, runner):
        """--help works without cohere or boto3 installed."""
        result = runner.invoke(batch_ingest, ["--help"])
        assert result.exit_code == 0
        assert "Batch embed a JSONL file" in result.output
        assert "--dry-run" in result.output
        assert "--cohere-api-key" in result.output

    def test_dry_run_shows_stats(self, runner, jsonl_file):
        """--dry-run shows record/doc/namespace stats without executing."""
        # dry-run exits before needing cohere/boto3 or credentials
        result = runner.invoke(batch_ingest, [
            str(jsonl_file),
            "--dry-run",
        ])

        assert result.exit_code == 0
        assert "Records: 3" in result.output
        assert "Documents: 2" in result.output
        assert "Dry Run" in result.output

    def test_dry_run_with_namespace_override(self, runner, jsonl_file):
        """--dry-run with namespace override shows correct namespace."""
        result = runner.invoke(batch_ingest, [
            str(jsonl_file),
            "--dry-run",
            "-n", "my-ns",
        ])

        assert result.exit_code == 0
        assert "my-ns" in result.output

    def test_missing_cohere_api_key(self, runner, jsonl_file):
        """Shows error when COHERE_API_KEY is missing."""
        result = runner.invoke(batch_ingest, [
            str(jsonl_file),
            "--s3vectors-bucket", "b",
            "--s3vectors-index", "i",
            "--documents-table", "t",
        ])

        assert result.exit_code != 0
        assert "Cohere API key required" in result.output

    def test_missing_s3vectors_bucket(self, runner, jsonl_file):
        """Shows error when S3VECTORS_BUCKET is missing."""
        result = runner.invoke(batch_ingest, [
            str(jsonl_file),
            "--cohere-api-key", "key",
            "--s3vectors-index", "i",
            "--documents-table", "t",
        ])

        assert result.exit_code != 0
        assert "S3 Vectors bucket required" in result.output

    def test_missing_s3vectors_index(self, runner, jsonl_file):
        """Shows error when S3VECTORS_INDEX is missing."""
        result = runner.invoke(batch_ingest, [
            str(jsonl_file),
            "--cohere-api-key", "key",
            "--s3vectors-bucket", "b",
            "--documents-table", "t",
        ])

        assert result.exit_code != 0
        assert "S3 Vectors index required" in result.output

    def test_missing_documents_table(self, runner, jsonl_file):
        """Shows error when DOCUMENTS_TABLE is missing."""
        result = runner.invoke(batch_ingest, [
            str(jsonl_file),
            "--cohere-api-key", "key",
            "--s3vectors-bucket", "b",
            "--s3vectors-index", "i",
        ])

        assert result.exit_code != 0
        assert "DynamoDB table required" in result.output

    def test_nonexistent_file(self, runner):
        """Click rejects nonexistent JSONL file."""
        result = runner.invoke(batch_ingest, [
            "/nonexistent/file.jsonl",
            "--cohere-api-key", "key",
            "--s3vectors-bucket", "b",
            "--s3vectors-index", "i",
            "--documents-table", "t",
        ])

        assert result.exit_code != 0

    def test_invalid_jsonl_file(self, runner, tmp_path):
        """Invalid JSONL content shows error."""
        bad_file = tmp_path / "bad.jsonl"
        bad_file.write_text("this is not json\n")

        result = runner.invoke(batch_ingest, [str(bad_file)])

        assert result.exit_code != 0
        assert "Invalid JSON" in result.output

    def test_empty_jsonl_file(self, runner, tmp_path):
        """Empty JSONL file shows error."""
        empty_file = tmp_path / "empty.jsonl"
        empty_file.write_text("")

        result = runner.invoke(batch_ingest, [str(empty_file)])

        assert result.exit_code != 0
        assert "No valid records" in result.output

    def test_default_options(self, runner):
        """Default option values are set correctly."""
        result = runner.invoke(batch_ingest, ["--help"])
        assert "default: embed-english-v3.0" in result.output
        assert "default: 1024" in result.output
        assert "default: 500" in result.output
        assert "default: 30" in result.output
        assert "default: us-east-1" in result.output


# ==================== Integration-style tests ====================


class TestBuildVectorsEdgeCases:
    """Edge case tests for build_vectors."""

    def test_single_record(self):
        """Works with a single record."""
        records = [{"text": "solo", "doc_id": "d1", "namespace": "ns"}]
        embeddings = [[0.1, 0.2, 0.3]]
        vectors, docs = build_vectors(records, embeddings, 3, None)

        assert len(vectors) == 1
        assert len(docs) == 1
        assert docs[0]["chunk_count"] == 1

    def test_multiple_docs_same_namespace(self):
        """Multiple documents in the same namespace."""
        records = [
            {"text": f"text {i}", "doc_id": f"doc{i}", "namespace": "shared"}
            for i in range(5)
        ]
        embeddings = [[0.1, 0.2]] * 5
        vectors, docs = build_vectors(records, embeddings, 2, None)

        assert len(vectors) == 5
        assert len(docs) == 5
        # All in same namespace
        for d in docs:
            assert d["namespace"] == "shared"

    def test_chunk_ids_sorted_in_doc_items(self):
        """chunk_ids in doc items are sorted by chunk_index."""
        records = [
            {"text": "c2", "doc_id": "d1", "namespace": "ns", "chunk_index": 2},
            {"text": "c0", "doc_id": "d1", "namespace": "ns", "chunk_index": 0},
            {"text": "c1", "doc_id": "d1", "namespace": "ns", "chunk_index": 1},
        ]
        embeddings = [[0.1, 0.2]] * 3
        _, docs = build_vectors(records, embeddings, 2, None)

        assert len(docs) == 1
        doc = docs[0]
        assert doc["chunk_count"] == 3
        # Verify chunk_ids are in chunk_index order
        doc1_uuid = str(uuid.uuid5(uuid.NAMESPACE_URL, "ns:d1"))
        expected_order = [
            str(uuid.uuid5(uuid.NAMESPACE_URL, f"{doc1_uuid}:0")),
            str(uuid.uuid5(uuid.NAMESPACE_URL, f"{doc1_uuid}:1")),
            str(uuid.uuid5(uuid.NAMESPACE_URL, f"{doc1_uuid}:2")),
        ]
        assert doc["chunk_ids"] == expected_order
