"""Pytest configuration and fixtures."""

import json
from io import BytesIO
from unittest.mock import MagicMock

import pytest

from stache_tools.client.config import StacheConfig


@pytest.fixture
def config():
    """Create a test config for HTTP transport."""
    return StacheConfig(
        api_url="http://localhost:8000",
        timeout=30.0,
    )


@pytest.fixture
def lambda_config():
    """Create a test config for Lambda transport."""
    return StacheConfig(
        transport="lambda",
        lambda_function_name="test-stache-api",
        aws_region="us-east-1",
    )


@pytest.fixture
def mock_httpx_client():
    """Create a mock httpx client."""
    client = MagicMock()
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {}
    response.headers = {"x-request-id": "test-123"}
    client.request.return_value = response
    client.get.return_value = response
    client.post.return_value = response
    client.put.return_value = response
    client.delete.return_value = response
    return client


@pytest.fixture
def mock_lambda_client():
    """Create a mock boto3 Lambda client."""
    client = MagicMock()

    def make_response(body: dict, status_code: int = 200, function_error: bool = False):
        """Helper to create Lambda response."""
        response_body = {
            "statusCode": status_code,
            "body": json.dumps(body),
            "headers": {"Content-Type": "application/json"},
        }
        result = {
            "Payload": BytesIO(json.dumps(response_body).encode()),
        }
        if function_error:
            result["FunctionError"] = "Unhandled"
        return result

    # Default success response
    client.invoke.return_value = make_response({"status": "ok"})
    client.make_response = make_response

    return client


@pytest.fixture
def mock_transport():
    """Create a generic mock transport for testing StacheAPI."""
    transport = MagicMock()
    transport.last_request_id = "test-request-id"
    transport.get.return_value = {"status": "ok"}
    transport.post.return_value = {"status": "ok"}
    transport.put.return_value = {"status": "ok"}
    transport.delete.return_value = {"status": "ok"}
    return transport
