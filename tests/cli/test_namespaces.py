"""Tests for the namespace CLI commands."""

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from stache_tools.cli.namespaces import delete_namespace


@pytest.fixture
def runner():
    """Create Click CLI runner."""
    return CliRunner()


@pytest.fixture
def mock_api():
    """Mock StacheAPI context manager."""
    with patch("stache_tools.cli.namespaces.StacheAPI") as mock_cls:
        api = MagicMock()
        api.delete_namespace.return_value = {
            "success": True,
            "namespace_id": "docs",
            "chunks_deleted": 0,
        }
        mock_cls.return_value.__enter__.return_value = api
        yield api


class TestDeleteNamespace:
    """Deleting a namespace must never delete documents unless asked to."""

    def test_default_keeps_documents(self, runner, mock_api):
        result = runner.invoke(delete_namespace, ["docs", "--yes"])

        assert result.exit_code == 0
        # The server defaults delete_documents to True, so the client must
        # always send an explicit False
        mock_api.delete_namespace.assert_called_once_with(
            id="docs", cascade=False, delete_documents=False
        )
        assert "documents kept" in result.output

    def test_delete_documents_flag_passes_through(self, runner, mock_api):
        mock_api.delete_namespace.return_value = {
            "success": True,
            "namespace_id": "docs",
            "chunks_deleted": 42,
        }

        result = runner.invoke(delete_namespace, ["docs", "--delete-documents", "--yes"])

        assert result.exit_code == 0
        mock_api.delete_namespace.assert_called_once_with(
            id="docs", cascade=False, delete_documents=True
        )
        assert "42 chunks" in result.output

    def test_confirmation_discloses_document_deletion(self, runner, mock_api):
        result = runner.invoke(
            delete_namespace, ["docs", "--delete-documents"], input="n\n"
        )

        assert result.exit_code != 0
        assert "PERMANENTLY delete all documents" in result.output
        mock_api.delete_namespace.assert_not_called()

    def test_default_confirmation_does_not_mention_documents(self, runner, mock_api):
        result = runner.invoke(delete_namespace, ["docs"], input="y\n")

        assert result.exit_code == 0
        assert "documents" not in result.output.split("?")[0].lower()

    def test_cascade_discloses_children(self, runner, mock_api):
        result = runner.invoke(delete_namespace, ["docs", "--cascade"], input="n\n")

        assert result.exit_code != 0
        assert "child namespaces" in result.output
