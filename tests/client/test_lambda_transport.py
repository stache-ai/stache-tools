"""Tests for Lambda transport.

These tests use moto to mock AWS services, so they don't require
real AWS credentials or Lambda functions.
"""

import json
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

from stache_tools.client.config import StacheConfig
from stache_tools.client.exceptions import (
    StacheAPIError,
    StacheAuthError,
    StacheConnectionError,
    StacheNotFoundError,
)


# Skip all tests if boto3 is not available
pytest.importorskip("boto3")


class TestLambdaTransportInit:
    """Tests for LambdaTransport initialization."""

    def test_init_with_config(self):
        """Test initialization with config."""
        from stache_tools.client.lambda_transport import LambdaTransport

        config = StacheConfig(
            lambda_function_name="test-function",
            aws_region="us-west-2",
        )
        with patch("boto3.Session") as mock_session:
            mock_client = MagicMock()
            mock_session.return_value.client.return_value = mock_client

            transport = LambdaTransport(config)

            assert transport._function_name == "test-function"
            mock_session.assert_called_once_with(
                profile_name=None,
                region_name="us-west-2",
            )

    def test_init_with_custom_session(self):
        """Test initialization with custom boto3 session."""
        from stache_tools.client.lambda_transport import LambdaTransport

        config = StacheConfig(lambda_function_name="test-function")
        mock_session = MagicMock()
        mock_client = MagicMock()
        mock_session.client.return_value = mock_client

        transport = LambdaTransport(config, session=mock_session)

        assert transport._session is mock_session
        mock_session.client.assert_called_once()

    def test_init_without_boto3_raises_import_error(self):
        """Test that missing boto3 raises ImportError."""
        from stache_tools.client import lambda_transport

        original_available = lambda_transport.BOTO3_AVAILABLE
        try:
            lambda_transport.BOTO3_AVAILABLE = False

            with pytest.raises(ImportError, match="boto3 is required"):
                lambda_transport.LambdaTransport()
        finally:
            lambda_transport.BOTO3_AVAILABLE = original_available


class TestLambdaTransportBuildEvent:
    """Tests for event building."""

    @pytest.fixture
    def transport(self):
        """Create transport with mocked client."""
        from stache_tools.client.lambda_transport import LambdaTransport

        config = StacheConfig(lambda_function_name="test-function")
        with patch("boto3.Session"):
            return LambdaTransport(config)

    def test_build_get_event(self, transport):
        """Test building GET event."""
        event = transport._build_event("GET", "/api/namespaces", params={"limit": 10})

        # API Gateway HTTP API v2 format
        assert event["version"] == "2.0"
        assert event["requestContext"]["http"]["method"] == "GET"
        assert event["rawPath"] == "/api/namespaces"
        assert event["body"] is None
        assert event["queryStringParameters"] == {"limit": 10}
        assert event["headers"]["content-type"] == "application/json"

    def test_build_post_event(self, transport):
        """Test building POST event with body."""
        body = {"query": "test", "top_k": 10}
        event = transport._build_event("POST", "/api/query", body=body)

        # API Gateway HTTP API v2 format
        assert event["version"] == "2.0"
        assert event["requestContext"]["http"]["method"] == "POST"
        assert event["rawPath"] == "/api/query"
        assert event["body"] == json.dumps(body)
        assert event["queryStringParameters"] is None


class TestLambdaTransportHandleResponse:
    """Tests for response handling."""

    @pytest.fixture
    def transport(self):
        """Create transport with mocked client."""
        from stache_tools.client.lambda_transport import LambdaTransport

        config = StacheConfig(lambda_function_name="test-function")
        with patch("boto3.Session"):
            return LambdaTransport(config)

    def test_handle_success_response(self, transport):
        """Test handling successful response."""
        payload = {
            "statusCode": 200,
            "body": json.dumps({"results": [], "request_id": "req-123"}),
        }

        result = transport._handle_response(payload)

        assert result == {"results": [], "request_id": "req-123"}
        assert transport.last_request_id == "req-123"

    def test_handle_404_response(self, transport):
        """Test 404 raises StacheNotFoundError."""
        payload = {
            "statusCode": 404,
            "body": json.dumps({"error": "Not found"}),
        }

        with pytest.raises(StacheNotFoundError):
            transport._handle_response(payload)

    def test_handle_401_response(self, transport):
        """Test 401 raises StacheAuthError."""
        payload = {
            "statusCode": 401,
            "body": json.dumps({"error": "Unauthorized"}),
        }

        with pytest.raises(StacheAuthError):
            transport._handle_response(payload)

    def test_handle_500_response(self, transport):
        """Test 500 raises StacheAPIError."""
        payload = {
            "statusCode": 500,
            "body": json.dumps({"error": "Internal error"}),
        }

        with pytest.raises(StacheAPIError) as exc_info:
            transport._handle_response(payload)
        assert exc_info.value.status_code == 500


class TestLambdaTransportInvoke:
    """Tests for Lambda invocation."""

    @pytest.fixture
    def transport(self):
        """Create transport with mocked Lambda client."""
        from stache_tools.client.lambda_transport import LambdaTransport

        config = StacheConfig(lambda_function_name="test-function")
        with patch("boto3.Session") as mock_session:
            mock_lambda = MagicMock()
            mock_session.return_value.client.return_value = mock_lambda

            transport = LambdaTransport(config)
            transport._lambda = mock_lambda
            return transport

    def test_invoke_success(self, transport):
        """Test successful invocation."""
        response_body = {"statusCode": 200, "body": json.dumps({"status": "ok"})}

        transport._lambda.invoke.return_value = {
            "Payload": BytesIO(json.dumps(response_body).encode()),
        }

        result = transport._invoke("GET", "/health")

        assert result == {"status": "ok"}
        transport._lambda.invoke.assert_called_once()

    def test_invoke_function_not_found(self, transport):
        """Test ResourceNotFoundException raises StacheConnectionError."""
        from botocore.exceptions import ClientError

        transport._lambda.invoke.side_effect = ClientError(
            {"Error": {"Code": "ResourceNotFoundException", "Message": "Function not found"}},
            "Invoke",
        )

        with pytest.raises(StacheConnectionError, match="Lambda function not found"):
            transport._invoke("GET", "/health")

    def test_invoke_access_denied(self, transport):
        """Test AccessDeniedException raises StacheAuthError."""
        from botocore.exceptions import ClientError

        transport._lambda.invoke.side_effect = ClientError(
            {"Error": {"Code": "AccessDeniedException", "Message": "Access denied"}},
            "Invoke",
        )

        with pytest.raises(StacheAuthError, match="Access denied"):
            transport._invoke("GET", "/health")

    def test_invoke_function_error(self, transport):
        """Test Lambda function error raises StacheAPIError."""
        error_payload = {"errorMessage": "Runtime error", "errorType": "RuntimeError"}

        transport._lambda.invoke.return_value = {
            "Payload": BytesIO(json.dumps(error_payload).encode()),
            "FunctionError": "Unhandled",
        }

        with pytest.raises(StacheAPIError, match="Lambda execution error"):
            transport._invoke("GET", "/health")

    def test_payload_read_once_on_function_error(self, transport):
        """Test that payload is read only once even on function error.

        This is a regression test for the double-read bug where StreamingBody
        was read twice, causing the second read to return empty bytes.
        """
        error_payload = {"errorMessage": "Test error", "errorType": "TestError"}
        payload_bytes = json.dumps(error_payload).encode()

        # Create a BytesIO that tracks read calls
        mock_payload = BytesIO(payload_bytes)
        original_read = mock_payload.read
        read_count = 0

        def counting_read(*args, **kwargs):
            nonlocal read_count
            read_count += 1
            return original_read(*args, **kwargs)

        mock_payload.read = counting_read

        transport._lambda.invoke.return_value = {
            "Payload": mock_payload,
            "FunctionError": "Unhandled",
        }

        with pytest.raises(StacheAPIError) as exc_info:
            transport._invoke("GET", "/health")

        # Payload should only be read once
        assert read_count == 1
        assert "Test error" in str(exc_info.value)


class TestLambdaTransportMethods:
    """Tests for HTTP method wrappers."""

    @pytest.fixture
    def transport(self):
        """Create transport with mocked _invoke."""
        from stache_tools.client.lambda_transport import LambdaTransport

        config = StacheConfig(lambda_function_name="test-function")
        with patch("boto3.Session"):
            transport = LambdaTransport(config)
            transport._invoke = MagicMock(return_value={"status": "ok"})
            return transport

    def test_get(self, transport):
        """Test GET method."""
        result = transport.get("/api/namespaces", params={"limit": 10})

        assert result == {"status": "ok"}
        transport._invoke.assert_called_once_with("GET", "/api/namespaces", params={"limit": 10})

    def test_post(self, transport):
        """Test POST method."""
        data = {"query": "test"}
        result = transport.post("/api/query", data=data)

        assert result == {"status": "ok"}
        transport._invoke.assert_called_once_with("POST", "/api/query", body=data)

    def test_put(self, transport):
        """Test PUT method."""
        data = {"name": "updated"}
        result = transport.put("/api/namespaces/ns-1", data=data)

        assert result == {"status": "ok"}
        transport._invoke.assert_called_once_with("PUT", "/api/namespaces/ns-1", body=data)

    def test_delete(self, transport):
        """Test DELETE method."""
        result = transport.delete("/api/documents/id/doc-1", params={"namespace": "default"})

        assert result == {"status": "ok"}
        transport._invoke.assert_called_once_with(
            "DELETE", "/api/documents/id/doc-1", params={"namespace": "default"}
        )


class TestTransportFactory:
    """Tests for transport factory."""

    def test_create_http_transport_default(self):
        """Test factory creates HTTP transport by default."""
        from stache_tools.client.factory import create_transport
        from stache_tools.client.http import HTTPTransport

        config = StacheConfig()
        transport = create_transport(config)

        assert isinstance(transport, HTTPTransport)
        transport.close()

    def test_create_lambda_transport_when_configured(self):
        """Test factory creates Lambda transport when configured."""
        from stache_tools.client.factory import create_transport
        from stache_tools.client.lambda_transport import LambdaTransport

        config = StacheConfig(
            transport="lambda",
            lambda_function_name="test-function",
        )

        with patch("boto3.Session"):
            transport = create_transport(config)

        assert isinstance(transport, LambdaTransport)

    def test_create_lambda_transport_auto_detect(self):
        """Test factory auto-detects Lambda when function name is set."""
        from stache_tools.client.factory import create_transport
        from stache_tools.client.lambda_transport import LambdaTransport

        config = StacheConfig(lambda_function_name="test-function")

        with patch("boto3.Session"):
            transport = create_transport(config)

        assert isinstance(transport, LambdaTransport)

    def test_create_transport_validates_config(self):
        """Test factory validates config before creating transport."""
        from stache_tools.client.factory import create_transport

        config = StacheConfig(transport="lambda")  # Missing function name

        with pytest.raises(ValueError, match="STACHE_LAMBDA_FUNCTION"):
            create_transport(config)


class TestConfigTransport:
    """Tests for config transport settings."""

    def test_transport_default_is_auto(self):
        """Test default transport is auto."""
        config = StacheConfig()
        assert config.transport == "auto"

    def test_transport_validation(self):
        """Test invalid transport raises error."""
        with pytest.raises(ValueError, match="Invalid transport"):
            StacheConfig(transport="invalid")

    def test_resolved_transport_auto_without_lambda(self):
        """Test auto resolves to http without Lambda config."""
        config = StacheConfig()
        assert config.resolved_transport == "http"

    def test_resolved_transport_auto_with_lambda(self):
        """Test auto resolves to lambda with Lambda config."""
        config = StacheConfig(lambda_function_name="test-fn")
        assert config.resolved_transport == "lambda"

    def test_resolved_transport_explicit(self):
        """Test explicit transport overrides auto-detection."""
        config = StacheConfig(
            transport="http",
            lambda_function_name="test-fn",
        )
        assert config.resolved_transport == "http"

    def test_validate_config_lambda_without_function(self):
        """Test validate_config catches missing Lambda function."""
        config = StacheConfig(transport="lambda")

        with pytest.raises(ValueError, match="STACHE_LAMBDA_FUNCTION"):
            config.validate_config()

    def test_validate_config_lambda_with_function(self):
        """Test validate_config passes with Lambda function."""
        config = StacheConfig(
            transport="lambda",
            lambda_function_name="test-fn",
        )
        config.validate_config()  # Should not raise
