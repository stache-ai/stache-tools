"""Custom exceptions for Stache API client."""



class StacheError(Exception):
    """Base exception for all Stache errors."""

    def __init__(self, message: str, request_id: str | None = None):
        self.message = message
        self.request_id = request_id
        super().__init__(message)

    def __str__(self) -> str:
        if self.request_id:
            return f"{self.message} (request_id: {self.request_id})"
        return self.message


class StacheConnectionError(StacheError):
    """Cannot reach the API server."""
    pass


class StacheAuthError(StacheError):
    """Authentication failed (401/403)."""
    pass


class StacheNotFoundError(StacheError):
    """Resource not found (404)."""
    pass


class StacheAPIError(StacheError):
    """Server error (5xx) or other API error."""

    def __init__(self, message: str, status_code: int, request_id: str | None = None):
        super().__init__(message, request_id)
        self.status_code = status_code

    def __str__(self) -> str:
        base = f"HTTP {self.status_code}: {self.message}"
        if self.request_id:
            return f"{base} (request_id: {self.request_id})"
        return base


def raise_for_status(status_code: int, message: str, request_id: str | None = None) -> None:
    """Raise appropriate exception based on HTTP status code."""
    if status_code == 401 or status_code == 403:
        raise StacheAuthError(message, request_id)
    elif status_code == 404:
        raise StacheNotFoundError(message, request_id)
    elif status_code >= 400:
        raise StacheAPIError(message, status_code, request_id)
