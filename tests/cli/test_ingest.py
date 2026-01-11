"""Comprehensive tests for the ingest CLI command."""

import pickle
import threading
import time
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch, call

import pytest
from click.testing import CliRunner

from stache_tools.cli.ingest import ingest, ingest_file_worker, collect_files
from stache_tools.client.config import StacheConfig
from stache_tools.client.exceptions import StacheError, StacheAPIError
from stache_tools.loaders import LoaderRegistry
from stache_tools.loaders.base import LoadedDocument


@pytest.fixture
def runner():
    """Create Click CLI runner."""
    return CliRunner()


@pytest.fixture
def temp_files(tmp_path):
    """Create temporary test files with content."""
    files = []
    for i in range(5):
        f = tmp_path / f"test_{i}.txt"
        f.write_text(f"Content for test file {i}")
        files.append(f)
    return files


@pytest.fixture
def mock_client():
    """Create mock StacheAPI client."""
    client = MagicMock()
    client.ingest_text.return_value = {
        "chunks_created": 3,
        "doc_id": "test-doc-id-123",
    }
    client.__enter__ = Mock(return_value=client)
    client.__exit__ = Mock(return_value=False)
    return client


@pytest.fixture
def mock_loader():
    """Create mock document loader."""
    loader = MagicMock()
    loader.load.return_value = LoadedDocument(
        text="Sample document content",
        metadata={"type": "text"},
    )
    return loader


@pytest.fixture
def mock_registry(mock_loader):
    """Create mock LoaderRegistry."""
    registry = MagicMock()
    registry.get_loader.return_value = mock_loader
    return registry


class TestIngestDryRun:
    """Tests for dry-run mode."""

    def test_dry_run_no_api_calls(self, runner, temp_files, tmp_path):
        """Verify dry-run makes no API calls."""
        with patch("stache_tools.cli.ingest.StacheAPI") as mock_api:
            result = runner.invoke(
                ingest,
                [str(tmp_path), "-n", "test-ns", "--dry-run"],
            )

            assert result.exit_code == 0
            assert "Dry Run" in result.output
            assert "Would ingest 5 files" in result.output
            mock_api.assert_not_called()

    def test_dry_run_shows_file_list(self, runner, temp_files, tmp_path):
        """Verify dry-run shows list of files to process."""
        result = runner.invoke(
            ingest,
            [str(tmp_path), "-n", "test-ns", "--dry-run"],
        )

        assert result.exit_code == 0
        # Should show filenames
        for f in temp_files:
            assert f.name in result.output
        assert "Target namespace: test-ns" in result.output

    def test_dry_run_with_empty_files(self, runner, tmp_path):
        """Dry-run shows status for empty files."""
        # Create mix of empty and non-empty files
        (tmp_path / "empty.txt").write_text("")
        (tmp_path / "content.txt").write_text("has content")

        result = runner.invoke(
            ingest,
            [str(tmp_path), "-n", "test-ns", "--dry-run"],
        )

        assert result.exit_code == 0
        assert "Would ingest 2 files" in result.output
        # Both files should be listed regardless of content
        assert "empty.txt" in result.output
        assert "content.txt" in result.output

    def test_dry_run_with_pattern(self, runner, tmp_path):
        """Dry-run respects glob pattern."""
        (tmp_path / "doc.md").write_text("# Markdown")
        (tmp_path / "note.txt").write_text("Text")
        (tmp_path / "data.json").write_text("{}")

        result = runner.invoke(
            ingest,
            [str(tmp_path), "-n", "test-ns", "--dry-run", "--pattern", "*.md"],
        )

        assert result.exit_code == 0
        assert "doc.md" in result.output
        assert "note.txt" not in result.output


class TestIngestParallel:
    """Tests for parallel processing mode."""

    @patch("stache_tools.cli.ingest.StacheAPI")
    def test_parallel_processing(self, mock_api_class, runner, temp_files, tmp_path, mock_client):
        """Verify parallel mode processes files concurrently."""
        mock_api_class.return_value = mock_client

        result = runner.invoke(
            ingest,
            [str(tmp_path), "-n", "test-ns", "-P", "4", "-y"],
        )

        assert result.exit_code == 0
        assert "Successful: 5 files" in result.output
        # Should have called ingest_text for each file
        assert mock_client.ingest_text.call_count == 5

    @patch("stache_tools.cli.ingest.StacheAPI")
    def test_parallel_error_cancellation(self, mock_api_class, runner, temp_files, tmp_path):
        """Verify error stops processing without --skip-errors."""
        mock_client = MagicMock()
        mock_client.__enter__ = Mock(return_value=mock_client)
        mock_client.__exit__ = Mock(return_value=False)

        # First call fails immediately
        mock_client.ingest_text.side_effect = StacheAPIError("API Error", status_code=500)
        mock_api_class.return_value = mock_client

        result = runner.invoke(
            ingest,
            [str(tmp_path), "-n", "test-ns", "-P", "2", "-y"],
        )

        # Should exit with error code 1
        assert result.exit_code == 1
        assert "Stopping due to error" in result.output
        # Should show error indicator
        assert "✗" in result.output

    @patch("stache_tools.cli.ingest.StacheAPI")
    def test_parallel_with_skip_errors(self, mock_api_class, runner, temp_files, tmp_path):
        """Verify --skip-errors continues after failures."""
        mock_client = MagicMock()
        mock_client.__enter__ = Mock(return_value=mock_client)
        mock_client.__exit__ = Mock(return_value=False)

        # Mix of success and failure
        mock_client.ingest_text.side_effect = [
            {"chunks_created": 3, "doc_id": "doc-1"},
            StacheAPIError("API Error", status_code=500),
            {"chunks_created": 3, "doc_id": "doc-3"},
            StacheAPIError("Another error", status_code=500),
            {"chunks_created": 3, "doc_id": "doc-5"},
        ]
        mock_api_class.return_value = mock_client

        result = runner.invoke(
            ingest,
            [str(tmp_path), "-n", "test-ns", "-P", "2", "--skip-errors", "-y"],
        )

        # Exit code 1 because there were failures (even with --skip-errors)
        assert result.exit_code == 1
        assert "Successful: 3 files" in result.output
        assert "Failed: 2 files" in result.output
        # Should process all files
        assert mock_client.ingest_text.call_count == 5

    @patch("stache_tools.cli.ingest.StacheAPI")
    def test_parallel_all_fail(self, mock_api_class, runner, temp_files, tmp_path):
        """Clean exit when all files fail."""
        mock_client = MagicMock()
        mock_client.__enter__ = Mock(return_value=mock_client)
        mock_client.__exit__ = Mock(return_value=False)
        mock_client.ingest_text.side_effect = StacheAPIError("Error", status_code=500)
        mock_api_class.return_value = mock_client

        result = runner.invoke(
            ingest,
            [str(tmp_path), "-n", "test-ns", "-P", "2", "--skip-errors", "-y"],
        )

        # Exit code 1 because all files failed
        assert result.exit_code == 1
        assert "Successful: 0 files" in result.output
        assert "Failed: 5 files" in result.output


class TestIngestConfiguration:
    """Tests for configuration and setup."""

    def test_config_picklable(self):
        """Verify StacheConfig can be pickled for ThreadPoolExecutor."""
        config = StacheConfig(
            api_url="http://localhost:8000",
            timeout=30.0,
        )

        # Should be able to pickle and unpickle
        pickled = pickle.dumps(config)
        restored = pickle.loads(pickled)

        assert restored.api_url == config.api_url
        assert restored.timeout == config.timeout

    def test_namespace_required_multi_file(self, runner, temp_files, tmp_path):
        """Error on missing namespace for multi-file ingest."""
        result = runner.invoke(
            ingest,
            [str(tmp_path)],
        )

        # Exit code 1 because namespace is required
        assert result.exit_code == 1
        assert "namespace required for multi-file ingests" in result.output
        assert "Example:" in result.output


class TestIngestConfirmation:
    """Tests for confirmation prompts."""

    @patch("stache_tools.cli.ingest.StacheAPI")
    def test_confirmation_prompt(self, mock_api_class, runner, temp_files, tmp_path, mock_client):
        """Prompts for multi-file ingest without -y flag."""
        mock_api_class.return_value = mock_client

        # Confirm with 'y'
        result = runner.invoke(
            ingest,
            [str(tmp_path), "-n", "test-ns"],
            input="y\n",
        )

        assert result.exit_code == 0
        assert "Ingest 5 files" in result.output
        assert "Successful: 5 files" in result.output

    @patch("stache_tools.cli.ingest.StacheAPI")
    def test_confirmation_abort(self, mock_api_class, runner, temp_files, tmp_path, mock_client):
        """Aborting confirmation exits cleanly."""
        mock_api_class.return_value = mock_client

        result = runner.invoke(
            ingest,
            [str(tmp_path), "-n", "test-ns"],
            input="n\n",
        )

        assert result.exit_code == 0
        assert "Aborted" in result.output
        # Should not call API
        mock_client.ingest_text.assert_not_called()

    @patch("stache_tools.cli.ingest.StacheAPI")
    def test_yes_flag_skips_prompt(self, mock_api_class, runner, temp_files, tmp_path, mock_client):
        """--yes flag skips confirmation prompt."""
        mock_api_class.return_value = mock_client

        result = runner.invoke(
            ingest,
            [str(tmp_path), "-n", "test-ns", "-y"],
        )

        assert result.exit_code == 0
        # Should not show confirmation prompt
        assert "Ingest 5 files" not in result.output or "?" not in result.output
        assert "Successful: 5 files" in result.output


class TestIngestFileHandling:
    """Tests for file processing and error handling."""

    @patch("stache_tools.cli.ingest.StacheAPI")
    def test_empty_file_skip(self, mock_api_class, runner, tmp_path, mock_client):
        """Skips empty files."""
        empty_file = tmp_path / "empty.txt"
        empty_file.write_text("")

        mock_api_class.return_value = mock_client

        result = runner.invoke(
            ingest,
            [str(empty_file), "-n", "test-ns"],
        )

        assert result.exit_code == 0
        assert "(empty)" in result.output
        # Should not call ingest_text
        mock_client.ingest_text.assert_not_called()

    @patch("stache_tools.cli.ingest.StacheAPI")
    def test_skip_errors(self, mock_api_class, runner, temp_files, tmp_path):
        """Continues after failure with --skip-errors."""
        mock_client = MagicMock()
        mock_client.__enter__ = Mock(return_value=mock_client)
        mock_client.__exit__ = Mock(return_value=False)

        # First call fails, rest succeed
        mock_client.ingest_text.side_effect = [
            StacheAPIError("API Error", status_code=500),
            {"chunks_created": 3, "doc_id": "doc-2"},
            {"chunks_created": 3, "doc_id": "doc-3"},
            {"chunks_created": 3, "doc_id": "doc-4"},
            {"chunks_created": 3, "doc_id": "doc-5"},
        ]
        mock_api_class.return_value = mock_client

        result = runner.invoke(
            ingest,
            [str(tmp_path), "-n", "test-ns", "--skip-errors", "-y"],
        )

        # Exit code 1 because there was a failure
        assert result.exit_code == 1
        assert "Successful: 4 files" in result.output
        assert "Failed: 1 files" in result.output

    def test_glob_pattern(self, runner, tmp_path):
        """Filters files correctly with glob pattern."""
        (tmp_path / "doc1.md").write_text("# Doc 1")
        (tmp_path / "doc2.md").write_text("# Doc 2")
        (tmp_path / "note.txt").write_text("Note")
        (tmp_path / "data.json").write_text("{}")

        result = runner.invoke(
            ingest,
            [str(tmp_path), "-n", "test-ns", "--pattern", "*.md", "--dry-run"],
        )

        assert result.exit_code == 0
        assert "Would ingest 2 files" in result.output
        assert "doc1.md" in result.output
        assert "doc2.md" in result.output
        assert "note.txt" not in result.output


class TestIngestTextMode:
    """Tests for direct text ingestion."""

    @patch("stache_tools.cli.ingest.StacheAPI")
    def test_text_flag(self, mock_api_class, runner, mock_client):
        """Ingest text directly with --text flag."""
        mock_api_class.return_value = mock_client

        result = runner.invoke(
            ingest,
            ["-t", "Quick note to remember", "-n", "notes"],
        )

        assert result.exit_code == 0
        assert "Ingested text" in result.output
        mock_client.ingest_text.assert_called_once()
        call_args = mock_client.ingest_text.call_args
        assert call_args[1]["text"] == "Quick note to remember"
        assert call_args[1]["namespace"] == "notes"

    @patch("stache_tools.cli.ingest.StacheAPI")
    def test_stdin_mode(self, mock_api_class, runner, mock_client):
        """Ingest text from stdin."""
        mock_api_class.return_value = mock_client

        result = runner.invoke(
            ingest,
            ["--stdin", "-n", "notes"],
            input="Text from stdin",
        )

        assert result.exit_code == 0
        mock_client.ingest_text.assert_called_once()
        call_args = mock_client.ingest_text.call_args
        assert call_args[1]["text"] == "Text from stdin"


class TestIngestMetadata:
    """Tests for metadata handling."""

    @patch("stache_tools.cli.ingest.StacheAPI")
    def test_metadata_json(self, mock_api_class, runner, tmp_path, mock_client):
        """Parse and apply JSON metadata."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Content")

        mock_api_class.return_value = mock_client

        result = runner.invoke(
            ingest,
            [str(test_file), "-n", "test-ns", "-m", '{"author": "John", "topic": "testing"}'],
        )

        assert result.exit_code == 0
        mock_client.ingest_text.assert_called_once()
        call_args = mock_client.ingest_text.call_args
        assert call_args[1]["metadata"]["author"] == "John"
        assert call_args[1]["metadata"]["topic"] == "testing"

    @patch("stache_tools.cli.ingest.StacheAPI")
    def test_prepend_metadata(self, mock_api_class, runner, tmp_path, mock_client):
        """Parse and apply prepend_metadata keys."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Content")

        mock_api_class.return_value = mock_client

        result = runner.invoke(
            ingest,
            [str(test_file), "-n", "test-ns", "-p", "author,topic"],
        )

        assert result.exit_code == 0
        mock_client.ingest_text.assert_called_once()
        call_args = mock_client.ingest_text.call_args
        assert call_args[1]["prepend_metadata"] == ["author", "topic"]

    def test_invalid_metadata_json(self, runner, tmp_path):
        """Handle invalid JSON metadata gracefully."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Content")

        result = runner.invoke(
            ingest,
            [str(test_file), "-n", "test-ns", "-m", "not-valid-json"],
        )

        # Exit code 1 because metadata is invalid
        assert result.exit_code == 1
        assert "Invalid metadata JSON" in result.output


class TestIngestWorker:
    """Tests for worker function."""

    def test_worker_creates_fresh_client(self):
        """Worker creates fresh client per call."""
        config = StacheConfig(api_url="http://localhost:8000")
        test_file = Path("/tmp/test.txt")

        with patch("stache_tools.cli.ingest.StacheAPI") as mock_api_class:
            mock_client = MagicMock()
            mock_client.__enter__ = Mock(return_value=mock_client)
            mock_client.__exit__ = Mock(return_value=False)
            mock_client.ingest_text.return_value = {"chunks_created": 3, "doc_id": "test"}
            mock_api_class.return_value = mock_client

            with patch("stache_tools.cli.ingest.LoaderRegistry") as mock_registry_class:
                mock_registry = MagicMock()
                mock_loader = MagicMock()
                mock_loader.load.return_value = LoadedDocument(
                    text="Content",
                    metadata={"type": "text"},
                )
                mock_registry.get_loader.return_value = mock_loader
                mock_registry_class.return_value = mock_registry

                with patch("builtins.open", create=True) as mock_open:
                    mock_open.return_value.__enter__.return_value.read.return_value = b"Content"

                    args = (test_file, config, "test-ns", "recursive", None, None)
                    result = ingest_file_worker(args)

                    # Should create fresh client
                    mock_api_class.assert_called_once_with(config)
                    assert result["status"] in ["success", "error", "skipped"]


class TestLoaderRegistry:
    """Tests for LoaderRegistry thread safety."""

    def test_loader_registry_thread_safety(self):
        """Verify singleton in threads."""
        results = []

        def get_registry():
            registry = LoaderRegistry()
            results.append(id(registry))

        threads = [threading.Thread(target=get_registry) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All threads should get same singleton instance
        assert len(set(results)) == 1


class TestCollectFiles:
    """Tests for file collection utility."""

    def test_collect_single_file(self, tmp_path):
        """Collect single file path."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Content")

        files = collect_files(test_file, "*", recursive=False)

        assert len(files) == 1
        assert files[0] == test_file

    def test_collect_directory_non_recursive(self, tmp_path):
        """Collect files from directory non-recursively."""
        (tmp_path / "file1.txt").write_text("Content 1")
        (tmp_path / "file2.txt").write_text("Content 2")
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (subdir / "file3.txt").write_text("Content 3")

        files = collect_files(tmp_path, "*", recursive=False)

        assert len(files) == 2
        assert all(f.parent == tmp_path for f in files)

    def test_collect_directory_recursive(self, tmp_path):
        """Collect files from directory recursively."""
        (tmp_path / "file1.txt").write_text("Content 1")
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (subdir / "file2.txt").write_text("Content 2")

        files = collect_files(tmp_path, "*", recursive=True)

        assert len(files) == 2

    def test_collect_with_pattern(self, tmp_path):
        """Collect files matching pattern."""
        (tmp_path / "doc.md").write_text("# Doc")
        (tmp_path / "note.txt").write_text("Note")

        files = collect_files(tmp_path, "*.md", recursive=False)

        assert len(files) == 1
        assert files[0].suffix == ".md"


# ==================== INTEGRATION TESTS ====================


class TestIngestIntegration:
    """Integration tests with real file I/O."""

    @patch("stache_tools.cli.ingest.StacheAPI")
    def test_integration_mixed_file_types(self, mock_api_class, runner, tmp_path):
        """Directory with multiple file types."""
        # Create mix of supported and unsupported files
        (tmp_path / "doc.txt").write_text("Text document")
        (tmp_path / "note.md").write_text("# Markdown note")
        (tmp_path / "data.json").write_text('{"key": "value"}')
        (tmp_path / "unsupported.xyz").write_text("Unknown type")

        mock_client = MagicMock()
        mock_client.__enter__ = Mock(return_value=mock_client)
        mock_client.__exit__ = Mock(return_value=False)
        mock_client.ingest_text.return_value = {"chunks_created": 3, "doc_id": "test"}
        mock_api_class.return_value = mock_client

        result = runner.invoke(
            ingest,
            [str(tmp_path), "-n", "test-ns", "-y"],
        )

        assert result.exit_code == 0
        # Should process supported files
        assert mock_client.ingest_text.call_count >= 2

    @patch("stache_tools.cli.ingest.StacheAPI")
    def test_integration_parallel_real_files(self, mock_api_class, runner, tmp_path):
        """10+ files with parallel=4."""
        # Create 12 files
        for i in range(12):
            (tmp_path / f"doc_{i:02d}.txt").write_text(f"Document {i} content")

        mock_client = MagicMock()
        mock_client.__enter__ = Mock(return_value=mock_client)
        mock_client.__exit__ = Mock(return_value=False)
        mock_client.ingest_text.return_value = {"chunks_created": 3, "doc_id": "test"}
        mock_api_class.return_value = mock_client

        result = runner.invoke(
            ingest,
            [str(tmp_path), "-n", "test-ns", "-P", "4", "-y"],
        )

        assert result.exit_code == 0
        assert "Successful: 12 files" in result.output
        assert mock_client.ingest_text.call_count == 12

    @patch("stache_tools.cli.ingest.StacheAPI")
    def test_integration_dry_run_accuracy(self, mock_api_class, runner, tmp_path):
        """Dry run matches actual file count."""
        # Create various files
        (tmp_path / "doc1.txt").write_text("Content 1")
        (tmp_path / "doc2.md").write_text("# Content 2")
        (tmp_path / "empty.txt").write_text("")

        # Dry run
        dry_result = runner.invoke(
            ingest,
            [str(tmp_path), "-n", "test-ns", "--dry-run"],
        )

        # Extract count from dry run
        assert "Would ingest 3 files" in dry_result.output

        # Actual run
        mock_client = MagicMock()
        mock_client.__enter__ = Mock(return_value=mock_client)
        mock_client.__exit__ = Mock(return_value=False)
        mock_client.ingest_text.return_value = {"chunks_created": 3, "doc_id": "test"}
        mock_api_class.return_value = mock_client

        actual_result = runner.invoke(
            ingest,
            [str(tmp_path), "-n", "test-ns", "-y"],
        )

        # Should process 2 files (empty skipped)
        assert "Successful: 2 files" in actual_result.output
        assert "Skipped: 1 files" in actual_result.output


class TestIngestParallelIntegration:
    """Integration tests for parallel processing edge cases."""

    @patch("stache_tools.cli.ingest.StacheAPI")
    def test_parallel_oauth_token_refresh(self, mock_api_class, runner, tmp_path):
        """Long-running parallel ingest with simulated token refresh."""
        # Create many files
        for i in range(10):
            (tmp_path / f"doc_{i:02d}.txt").write_text(f"Document {i} content")

        mock_client = MagicMock()
        mock_client.__enter__ = Mock(return_value=mock_client)
        mock_client.__exit__ = Mock(return_value=False)

        # Simulate slow API calls
        def slow_ingest(*args, **kwargs):
            time.sleep(0.01)  # Small delay to simulate network
            return {"chunks_created": 3, "doc_id": "test"}

        mock_client.ingest_text.side_effect = slow_ingest
        mock_api_class.return_value = mock_client

        result = runner.invoke(
            ingest,
            [str(tmp_path), "-n", "test-ns", "-P", "3", "-y"],
        )

        assert result.exit_code == 0
        assert "Successful: 10 files" in result.output

    @patch("stache_tools.cli.ingest.StacheAPI")
    def test_parallel_with_rate_limiting(self, mock_api_class, runner, tmp_path):
        """Mock 429 responses (rate limiting)."""
        # Create test files
        for i in range(5):
            (tmp_path / f"doc_{i}.txt").write_text(f"Document {i}")

        mock_client = MagicMock()
        mock_client.__enter__ = Mock(return_value=mock_client)
        mock_client.__exit__ = Mock(return_value=False)

        # First call gets rate limited, rest succeed
        mock_client.ingest_text.side_effect = [
            StacheAPIError("Rate limit exceeded", status_code=429),
            {"chunks_created": 3, "doc_id": "doc-2"},
            {"chunks_created": 3, "doc_id": "doc-3"},
            {"chunks_created": 3, "doc_id": "doc-4"},
            {"chunks_created": 3, "doc_id": "doc-5"},
        ]
        mock_api_class.return_value = mock_client

        result = runner.invoke(
            ingest,
            [str(tmp_path), "-n", "test-ns", "-P", "2", "--skip-errors", "-y"],
        )

        # Exit code 1 because there was a failure
        assert result.exit_code == 1
        assert "Successful: 4 files" in result.output
        assert "Failed: 1 files" in result.output


class TestIngestChunkingStrategy:
    """Tests for chunking strategy options."""

    @patch("stache_tools.cli.ingest.StacheAPI")
    def test_auto_strategy_default(self, mock_api_class, runner, tmp_path, mock_client):
        """Default to 'auto' strategy (converted to 'recursive')."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Content")

        mock_api_class.return_value = mock_client

        result = runner.invoke(
            ingest,
            [str(test_file), "-n", "test-ns"],
        )

        assert result.exit_code == 0
        call_args = mock_client.ingest_text.call_args
        # 'auto' should be converted to 'recursive'
        assert call_args[1]["chunking_strategy"] == "recursive"

    @patch("stache_tools.cli.ingest.StacheAPI")
    def test_explicit_strategy(self, mock_api_class, runner, tmp_path, mock_client):
        """Explicit chunking strategy is passed through."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Content")

        mock_api_class.return_value = mock_client

        result = runner.invoke(
            ingest,
            [str(test_file), "-n", "test-ns", "-c", "semantic"],
        )

        assert result.exit_code == 0
        call_args = mock_client.ingest_text.call_args
        assert call_args[1]["chunking_strategy"] == "semantic"


class TestIngestRecursive:
    """Tests for recursive directory processing."""

    @patch("stache_tools.cli.ingest.StacheAPI")
    def test_recursive_flag(self, mock_api_class, runner, tmp_path, mock_client):
        """Recursive flag processes subdirectories."""
        # Create nested structure
        (tmp_path / "root.txt").write_text("Root file")
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (subdir / "nested.txt").write_text("Nested file")

        mock_api_class.return_value = mock_client

        result = runner.invoke(
            ingest,
            [str(tmp_path), "-n", "test-ns", "-r", "-y"],
        )

        assert result.exit_code == 0
        assert "Successful: 2 files" in result.output
        assert mock_client.ingest_text.call_count == 2

    @patch("stache_tools.cli.ingest.StacheAPI")
    def test_non_recursive_ignores_subdirs(self, mock_api_class, runner, tmp_path, mock_client):
        """Without -r flag, ignores subdirectories."""
        (tmp_path / "root.txt").write_text("Root file")
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (subdir / "nested.txt").write_text("Nested file")

        mock_api_class.return_value = mock_client

        result = runner.invoke(
            ingest,
            [str(tmp_path), "-n", "test-ns", "-y"],
        )

        assert result.exit_code == 0
        assert "Successful: 1 files" in result.output
        assert mock_client.ingest_text.call_count == 1
