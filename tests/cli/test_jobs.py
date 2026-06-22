"""Tests for the jobs CLI command group."""

from unittest.mock import Mock, MagicMock, patch

import pytest
from click.testing import CliRunner

from stache_tools.cli.jobs import jobs
from stache_tools.client.exceptions import StacheNotFoundError


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def mock_client():
    client = MagicMock()
    client.__enter__ = Mock(return_value=client)
    client.__exit__ = Mock(return_value=False)
    return client


class TestJobsList:
    @patch("stache_tools.cli.jobs.StacheAPI")
    def test_list_table(self, mock_api_class, runner, mock_client):
        mock_client.list_jobs.return_value = {
            "jobs": [
                {"job_id": "j1", "status": "done", "filename": "a.txt",
                 "namespace": "ns", "created_at": "2026-06-20T10:00:00Z"},
            ]
        }
        mock_api_class.return_value = mock_client

        result = runner.invoke(jobs, ["list"])

        assert result.exit_code == 0
        assert "j1" in result.output
        assert "done" in result.output
        assert "a.txt" in result.output

    @patch("stache_tools.cli.jobs.StacheAPI")
    def test_list_json(self, mock_api_class, runner, mock_client):
        mock_client.list_jobs.return_value = {"jobs": [{"job_id": "j1", "status": "done"}]}
        mock_api_class.return_value = mock_client

        result = runner.invoke(jobs, ["list", "--json"])

        assert result.exit_code == 0
        assert '"job_id"' in result.output
        assert "j1" in result.output

    @patch("stache_tools.cli.jobs.StacheAPI")
    def test_list_empty(self, mock_api_class, runner, mock_client):
        mock_client.list_jobs.return_value = {"jobs": []}
        mock_api_class.return_value = mock_client

        result = runner.invoke(jobs, ["list"])

        assert result.exit_code == 0
        assert "No jobs found" in result.output

    @patch("stache_tools.cli.jobs.StacheAPI")
    def test_list_passes_filters(self, mock_api_class, runner, mock_client):
        mock_client.list_jobs.return_value = {"jobs": []}
        mock_api_class.return_value = mock_client

        runner.invoke(jobs, ["list", "--status", "failed", "--limit", "10"])

        mock_client.list_jobs.assert_called_once_with(status="failed", limit=10)


class TestJobsGet:
    @patch("stache_tools.cli.jobs.StacheAPI")
    def test_get_panel(self, mock_api_class, runner, mock_client):
        mock_client.get_job.return_value = {
            "job_id": "j1", "status": "done", "filename": "a.txt",
            "namespace": "ns", "chunks_created": 5, "doc_id": "d1",
        }
        mock_api_class.return_value = mock_client

        result = runner.invoke(jobs, ["get", "j1"])

        assert result.exit_code == 0
        assert "j1" in result.output
        assert "done" in result.output
        assert "5" in result.output

    @patch("stache_tools.cli.jobs.StacheAPI")
    def test_get_json(self, mock_api_class, runner, mock_client):
        mock_client.get_job.return_value = {"job_id": "j1", "status": "done"}
        mock_api_class.return_value = mock_client

        result = runner.invoke(jobs, ["get", "j1", "-j"])

        assert result.exit_code == 0
        assert '"status"' in result.output

    @patch("stache_tools.cli.jobs.StacheAPI")
    def test_get_not_found(self, mock_api_class, runner, mock_client):
        mock_client.get_job.side_effect = StacheNotFoundError("not found")
        mock_api_class.return_value = mock_client

        result = runner.invoke(jobs, ["get", "nope"])

        assert result.exit_code == 1
        assert "not found" in result.output.lower()
