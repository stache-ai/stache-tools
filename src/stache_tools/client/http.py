"""HTTP transport with OAuth and retry/backoff.

This module implements the HTTP transport for communicating with Stache
via API Gateway. It handles OAuth authentication and implements retry
logic for transient failures.
"""

import logging
from typing import Any

import httpx
from httpx_auth import OAuth2ClientCredentials

from .config import StacheConfig
from .exceptions import StacheAPIError, StacheConnectionError, raise_for_status
from .retry import get_retry_decorator, is_retryable_api_error, is_retryable_connection_error

logger = logging.getLogger("stache-tools")


def _is_retryable_http(exception: BaseException) -> bool:
    """Check if exception is retryable for HTTP transport.

    Retryable conditions:
    - Raw httpx connection/timeout errors
    - Wrapped StacheConnectionError
    - StacheAPIError with 429 or 5xx status

    Args:
        exception: The exception to check

    Returns:
        True if the request should be retried
    """
    # Raw httpx exceptions (connection/timeout)
    if isinstance(exception, (httpx.ConnectError, httpx.TimeoutException)):
        return True
    # Wrapped connection errors
    if is_retryable_connection_error(exception):
        return True
    # Wrapped API errors with retryable status codes
    if is_retryable_api_error(exception):
        return True
    return False


# Create retry decorator with HTTP-specific retry logic
_retry_http = get_retry_decorator(_is_retryable_http)


class HTTPTransport:
    """HTTP transport with OAuth and retry/backoff.

    Implements StacheTransport protocol for API Gateway communication.
    Handles OAuth2 client credentials flow and automatic retry with
    exponential backoff for transient failures.

    Usage:
        transport = HTTPTransport(config)
        result = transport.get("/api/namespaces")
        transport.close()

    Or as context manager:
        with HTTPTransport(config) as transport:
            result = transport.get("/api/namespaces")
    """

    def __init__(self, config: StacheConfig | None = None):
        """Initialize HTTP transport.

        Args:
            config: Stache configuration. If None, loads from environment.
        """
        self.config = config or StacheConfig()
        self._client: httpx.Client | None = None
        self._last_request_id: str | None = None

    @property
    def client(self) -> httpx.Client:
        """Lazy-initialize HTTP client with optional OAuth."""
        if self._client is None:
            auth = None
            if self.config.oauth_enabled:
                auth = OAuth2ClientCredentials(
                    token_url=self.config.cognito_token_url,
                    client_id=self.config.cognito_client_id,
                    client_secret=self.config.cognito_client_secret,
                    scope=self.config.cognito_scope,
                )
            self._client = httpx.Client(
                base_url=self.config.api_url,
                timeout=self.config.timeout,
                auth=auth,
            )
        return self._client

    @property
    def last_request_id(self) -> str | None:
        """Get request_id from last response."""
        return self._last_request_id

    def __enter__(self) -> "HTTPTransport":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit - close client."""
        self.close()

    def close(self) -> None:
        """Close HTTP client and release resources."""
        if self._client:
            self._client.close()
            self._client = None

    def _extract_request_id(self, response: httpx.Response) -> str | None:
        """Extract request_id from response body.

        Args:
            response: HTTP response object

        Returns:
            The request_id if present in JSON body, otherwise None
        """
        try:
            data = response.json()
            if isinstance(data, dict):
                return data.get("request_id")
        except Exception:
            pass
        return None

    def _handle_response(self, response: httpx.Response) -> dict[str, Any]:
        """Handle response and raise exceptions for errors.

        Args:
            response: HTTP response object

        Returns:
            Parsed JSON response as dictionary

        Raises:
            StacheAuthError: For 401/403 responses
            StacheNotFoundError: For 404 responses
            StacheAPIError: For other 4xx/5xx responses
        """
        self._last_request_id = self._extract_request_id(response)

        if response.status_code >= 400:
            try:
                error_data = response.json()
                message = error_data.get("error") or error_data.get("detail") or str(error_data)
            except Exception:
                message = response.text or f"HTTP {response.status_code}"
            raise_for_status(response.status_code, message, self._last_request_id)

        return response.json()

    @_retry_http
    def get(self, path: str, params: dict | None = None) -> dict[str, Any]:
        """Execute GET request with retry.

        Args:
            path: API path (e.g., "/api/namespaces")
            params: Optional query parameters

        Returns:
            Parsed JSON response
        """
        try:
            response = self.client.get(path, params=params)
            return self._handle_response(response)
        except httpx.ConnectError as e:
            raise StacheConnectionError(f"Cannot connect to {self.config.api_url}: {e}")
        except httpx.TimeoutException as e:
            raise StacheConnectionError(f"Request timeout to {self.config.api_url}: {e}")

    @_retry_http
    def post(self, path: str, data: dict | None = None) -> dict[str, Any]:
        """Execute POST request with retry.

        Args:
            path: API path (e.g., "/api/capture")
            data: Optional JSON body

        Returns:
            Parsed JSON response
        """
        try:
            response = self.client.post(path, json=data)
            return self._handle_response(response)
        except httpx.ConnectError as e:
            raise StacheConnectionError(f"Cannot connect to {self.config.api_url}: {e}")
        except httpx.TimeoutException as e:
            raise StacheConnectionError(f"Request timeout to {self.config.api_url}: {e}")

    @_retry_http
    def put(self, path: str, data: dict | None = None) -> dict[str, Any]:
        """Execute PUT request with retry.

        Args:
            path: API path (e.g., "/api/namespaces/my-ns")
            data: Optional JSON body

        Returns:
            Parsed JSON response
        """
        try:
            response = self.client.put(path, json=data)
            return self._handle_response(response)
        except httpx.ConnectError as e:
            raise StacheConnectionError(f"Cannot connect to {self.config.api_url}: {e}")
        except httpx.TimeoutException as e:
            raise StacheConnectionError(f"Request timeout to {self.config.api_url}: {e}")

    @_retry_http
    def delete(self, path: str, params: dict | None = None) -> dict[str, Any]:
        """Execute DELETE request with retry.

        Args:
            path: API path (e.g., "/api/documents/id/doc-123")
            params: Optional query parameters

        Returns:
            Parsed JSON response
        """
        try:
            response = self.client.delete(path, params=params)
            return self._handle_response(response)
        except httpx.ConnectError as e:
            raise StacheConnectionError(f"Cannot connect to {self.config.api_url}: {e}")
        except httpx.TimeoutException as e:
            raise StacheConnectionError(f"Request timeout to {self.config.api_url}: {e}")


# Backwards compatibility alias
StacheHTTPClient = HTTPTransport
