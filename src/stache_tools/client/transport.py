"""Transport protocol for Stache API communication.

This module defines the interface that all transports must implement.
Both HTTP and Lambda transports conform to this protocol, allowing
StacheAPI to work with either transport interchangeably.
"""

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class StacheTransport(Protocol):
    """Protocol defining the transport interface.

    All transports must implement these methods to be usable
    with StacheAPI. The protocol is runtime-checkable for
    explicit validation.

    Transports are responsible for:
    - Making requests to the Stache backend
    - Handling retries and backoff
    - Converting responses to dictionaries
    - Raising appropriate exceptions for errors
    """

    @property
    def last_request_id(self) -> str | None:
        """Get request_id from last response (for debugging).

        Returns:
            The request_id from the most recent API response, or None
            if no request has been made or the response didn't include one.
        """
        ...

    def get(self, path: str, params: dict | None = None) -> dict[str, Any]:
        """Execute an HTTP GET equivalent request.

        Args:
            path: API path (e.g., "/api/namespaces")
            params: Optional query parameters

        Returns:
            Parsed JSON response as a dictionary

        Raises:
            StacheConnectionError: If unable to connect
            StacheAuthError: If authentication fails (401/403)
            StacheNotFoundError: If resource not found (404)
            StacheAPIError: For other HTTP errors
        """
        ...

    def post(self, path: str, data: dict | None = None) -> dict[str, Any]:
        """Execute an HTTP POST equivalent request.

        Args:
            path: API path (e.g., "/api/capture")
            data: Optional JSON body data

        Returns:
            Parsed JSON response as a dictionary

        Raises:
            StacheConnectionError: If unable to connect
            StacheAuthError: If authentication fails (401/403)
            StacheNotFoundError: If resource not found (404)
            StacheAPIError: For other HTTP errors
        """
        ...

    def put(self, path: str, data: dict | None = None) -> dict[str, Any]:
        """Execute an HTTP PUT equivalent request.

        Args:
            path: API path (e.g., "/api/namespaces/my-ns")
            data: Optional JSON body data

        Returns:
            Parsed JSON response as a dictionary

        Raises:
            StacheConnectionError: If unable to connect
            StacheAuthError: If authentication fails (401/403)
            StacheNotFoundError: If resource not found (404)
            StacheAPIError: For other HTTP errors
        """
        ...

    def delete(self, path: str, params: dict | None = None) -> dict[str, Any]:
        """Execute an HTTP DELETE equivalent request.

        Args:
            path: API path (e.g., "/api/documents/id/doc-123")
            params: Optional query parameters

        Returns:
            Parsed JSON response as a dictionary

        Raises:
            StacheConnectionError: If unable to connect
            StacheAuthError: If authentication fails (401/403)
            StacheNotFoundError: If resource not found (404)
            StacheAPIError: For other HTTP errors
        """
        ...

    def close(self) -> None:
        """Clean up resources (connection pools, clients, etc.).

        Should be called when the transport is no longer needed.
        Safe to call multiple times.
        """
        ...
