"""Lambda direct invocation transport.

This module implements direct Lambda invocation for communicating with Stache,
bypassing API Gateway for lower latency and simpler authentication (uses AWS
credentials instead of OAuth).

Requires boto3: pip install stache-tools[lambda]
"""

import json
import logging
import time
from typing import Any

from .config import StacheConfig
from .exceptions import (
    StacheAPIError,
    StacheAuthError,
    StacheConnectionError,
    raise_for_status,
)
from .retry import get_retry_decorator, is_retryable_api_error, is_retryable_connection_error

logger = logging.getLogger("stache-tools")

# Lazy import check for boto3
try:
    import boto3
    from botocore.config import Config as BotoConfig
    from botocore.exceptions import ClientError

    BOTO3_AVAILABLE = True
except ImportError:
    BOTO3_AVAILABLE = False
    boto3 = None  # type: ignore
    BotoConfig = None  # type: ignore
    ClientError = Exception  # type: ignore


def _is_retryable_lambda(exception: BaseException) -> bool:
    """Check if Lambda exception is retryable.

    Retryable conditions:
    - StacheConnectionError (function not found, etc.)
    - StacheAPIError with 429 or 5xx status
    - boto3 ClientError for throttling/service issues

    Args:
        exception: The exception to check

    Returns:
        True if the request should be retried
    """
    # Wrapped connection errors
    if is_retryable_connection_error(exception):
        return True
    # Wrapped API errors with retryable status codes
    if is_retryable_api_error(exception):
        return True
    # boto3 ClientError for throttling
    if BOTO3_AVAILABLE and isinstance(exception, ClientError):
        code = exception.response.get("Error", {}).get("Code", "")
        return code in (
            "TooManyRequestsException",
            "ServiceException",
            "ServiceUnavailableException",
        )
    return False


# Create retry decorator with Lambda-specific retry logic
_retry_lambda = get_retry_decorator(_is_retryable_lambda)


class LambdaTransport:
    """Direct Lambda invocation transport.

    Implements StacheTransport protocol for direct Lambda communication,
    bypassing API Gateway for lower latency and simpler auth.

    Requires boto3: pip install stache-tools[lambda]

    Usage:
        transport = LambdaTransport(config)
        result = transport.get("/api/namespaces")
        transport.close()

    Or as context manager:
        with LambdaTransport(config) as transport:
            result = transport.get("/api/namespaces")
    """

    # Cold start threshold for logging (seconds)
    COLD_START_THRESHOLD_SECONDS = 5.0

    def __init__(
        self,
        config: StacheConfig | None = None,
        session: "boto3.Session | None" = None,
    ):
        """Initialize Lambda transport.

        Args:
            config: Stache configuration. If None, loads from environment.
            session: Optional existing boto3 session (for testing or advanced use).

        Raises:
            ImportError: If boto3 is not installed.
        """
        if not BOTO3_AVAILABLE:
            raise ImportError(
                "boto3 is required for Lambda transport. "
                "Install with: pip install stache-tools[lambda]"
            )

        self.config = config or StacheConfig()
        self._last_request_id: str | None = None

        # Create or use provided session
        self._session = session or boto3.Session(
            profile_name=self.config.aws_profile,
            region_name=self.config.aws_region,
        )

        # Configure client with timeout and disable boto3's retry (we handle it)
        boto_config = BotoConfig(
            read_timeout=self.config.lambda_timeout,
            connect_timeout=10,
            retries={"max_attempts": 0},  # We handle retries ourselves
        )

        self._lambda = self._session.client("lambda", config=boto_config)
        self._function_name = self.config.lambda_function_name

    @property
    def last_request_id(self) -> str | None:
        """Get request_id from last response."""
        return self._last_request_id

    def close(self) -> None:
        """Close Lambda client.

        boto3 clients don't require explicit closing, but we implement
        the protocol method for consistency.
        """
        pass

    def __enter__(self) -> "LambdaTransport":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.close()

    def _build_event(
        self,
        method: str,
        path: str,
        body: dict | None = None,
        params: dict | None = None,
    ) -> dict:
        """Build API Gateway REST API format event.

        The Lambda handler expects events in API Gateway v1 (REST API) format.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            path: API path (e.g., "/api/namespaces")
            body: Optional request body (will be JSON serialized)
            params: Optional query string parameters

        Returns:
            Event dictionary in API Gateway v1 format
        """
        return {
            "httpMethod": method,
            "path": path,
            "body": json.dumps(body) if body else None,
            "headers": {"Content-Type": "application/json"},
            "queryStringParameters": params,
            "pathParameters": None,
            "requestContext": {
                "identity": {},
                "requestId": None,  # Lambda will generate if needed
            },
        }

    def _handle_response(self, payload: dict) -> dict[str, Any]:
        """Handle Lambda response payload.

        Expects API Gateway response format: {statusCode, body, headers}
        Maps HTTP status codes to appropriate exceptions.

        Args:
            payload: Parsed Lambda response payload

        Returns:
            Parsed response body as dictionary

        Raises:
            StacheAuthError: For 401/403 status
            StacheNotFoundError: For 404 status
            StacheAPIError: For other 4xx/5xx status
        """
        # Extract request_id from response body if present
        body_str = payload.get("body") or "{}"
        try:
            body = json.loads(body_str) if body_str else {}
            if isinstance(body, dict):
                self._last_request_id = body.get("request_id")
        except (json.JSONDecodeError, TypeError):
            body = {}
            self._last_request_id = None

        status_code = payload.get("statusCode", 200)

        if status_code >= 400:
            # Extract error message
            if isinstance(body, dict):
                message = body.get("error") or body.get("detail") or str(body)
            else:
                message = str(body) or f"HTTP {status_code}"
            raise_for_status(status_code, message, self._last_request_id)

        return body

    def _invoke(
        self,
        method: str,
        path: str,
        body: dict | None = None,
        params: dict | None = None,
    ) -> dict[str, Any]:
        """Invoke Lambda function.

        Args:
            method: HTTP method
            path: API path
            body: Optional request body
            params: Optional query parameters

        Returns:
            Parsed response body

        Raises:
            StacheConnectionError: If Lambda function not found or invocation fails
            StacheAuthError: If access denied to Lambda function
            StacheAPIError: For Lambda execution errors or HTTP errors in response
        """
        event = self._build_event(method, path, body, params)

        start_time = time.monotonic()

        try:
            response = self._lambda.invoke(
                FunctionName=self._function_name,
                InvocationType="RequestResponse",
                Payload=json.dumps(event),
            )
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            error_msg = e.response.get("Error", {}).get("Message", str(e))

            if error_code == "ResourceNotFoundException":
                raise StacheConnectionError(
                    f"Lambda function not found: {self._function_name}"
                )
            elif error_code == "AccessDeniedException":
                raise StacheAuthError(
                    f"Access denied to Lambda function: {self._function_name}. "
                    f"Ensure IAM policy includes lambda:InvokeFunction permission."
                )
            elif error_code in ("TooManyRequestsException", "ServiceException"):
                # Let retry logic handle these by raising retryable error
                raise StacheAPIError(error_msg, 503)
            else:
                raise StacheConnectionError(f"Lambda invocation failed: {error_msg}")

        duration = time.monotonic() - start_time

        # Log potential cold starts
        if duration > self.COLD_START_THRESHOLD_SECONDS:
            logger.info(
                f"Lambda invocation took {duration:.2f}s (possible cold start)"
            )

        # CRITICAL: Read payload bytes ONCE - StreamingBody can only be read once
        payload_bytes = response["Payload"].read()

        # Check for Lambda execution errors (distinct from HTTP errors in response)
        if "FunctionError" in response:
            error_payload = json.loads(payload_bytes)
            error_msg = error_payload.get("errorMessage", "Unknown Lambda error")
            error_type = error_payload.get("errorType", "Error")
            raise StacheAPIError(
                f"Lambda execution error ({error_type}): {error_msg}",
                500,
            )

        # Parse and validate response
        payload = json.loads(payload_bytes)
        return self._handle_response(payload)

    @_retry_lambda
    def get(self, path: str, params: dict | None = None) -> dict[str, Any]:
        """Execute GET request with retry.

        Args:
            path: API path (e.g., "/api/namespaces")
            params: Optional query parameters

        Returns:
            Parsed JSON response
        """
        return self._invoke("GET", path, params=params)

    @_retry_lambda
    def post(self, path: str, data: dict | None = None) -> dict[str, Any]:
        """Execute POST request with retry.

        Args:
            path: API path (e.g., "/api/capture")
            data: Optional JSON body

        Returns:
            Parsed JSON response
        """
        return self._invoke("POST", path, body=data)

    @_retry_lambda
    def put(self, path: str, data: dict | None = None) -> dict[str, Any]:
        """Execute PUT request with retry.

        Args:
            path: API path (e.g., "/api/namespaces/my-ns")
            data: Optional JSON body

        Returns:
            Parsed JSON response
        """
        return self._invoke("PUT", path, body=data)

    @_retry_lambda
    def delete(self, path: str, params: dict | None = None) -> dict[str, Any]:
        """Execute DELETE request with retry.

        Args:
            path: API path (e.g., "/api/documents/id/doc-123")
            params: Optional query parameters

        Returns:
            Parsed JSON response
        """
        return self._invoke("DELETE", path, params=params)
