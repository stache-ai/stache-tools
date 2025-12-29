"""Tests for Stache client."""

import pytest
from stache_tools.client.config import StacheConfig
from stache_tools.client.exceptions import (
    StacheError,
    StacheAuthError,
    StacheNotFoundError,
    StacheAPIError,
    raise_for_status,
)


class TestStacheConfig:
    """Tests for StacheConfig."""

    def test_default_values(self):
        """Test default configuration values."""
        config = StacheConfig()
        assert config.api_url == "http://localhost:8000"
        assert config.timeout == 60.0
        assert config.log_level == "INFO"

    def test_url_validation(self):
        """Test URL must start with http."""
        with pytest.raises(ValueError, match="URL must start with http"):
            StacheConfig(api_url="invalid-url")

    def test_url_strips_trailing_slash(self):
        """Test trailing slash is stripped from URL."""
        config = StacheConfig(api_url="http://localhost:8000/")
        assert config.api_url == "http://localhost:8000"

    def test_oauth_not_enabled_by_default(self):
        """Test OAuth is disabled when credentials not set."""
        config = StacheConfig()
        assert config.oauth_enabled is False

    def test_oauth_enabled_when_configured(self):
        """Test OAuth is enabled when all credentials set."""
        config = StacheConfig(
            cognito_client_id="test-id",
            cognito_client_secret="test-secret",
            cognito_token_url="https://auth.example.com/token",
        )
        assert config.oauth_enabled is True


class TestExceptions:
    """Tests for exception hierarchy."""

    def test_stache_error_base(self):
        """Test base StacheError."""
        error = StacheError("Test error")
        assert str(error) == "Test error"
        assert error.request_id is None

    def test_stache_error_with_request_id(self):
        """Test StacheError with request ID."""
        error = StacheError("Test error", request_id="req-123")
        assert "req-123" in str(error)

    def test_raise_for_status_auth(self):
        """Test 401/403 raises StacheAuthError."""
        with pytest.raises(StacheAuthError):
            raise_for_status(401, "Unauthorized")
        with pytest.raises(StacheAuthError):
            raise_for_status(403, "Forbidden")

    def test_raise_for_status_not_found(self):
        """Test 404 raises StacheNotFoundError."""
        with pytest.raises(StacheNotFoundError):
            raise_for_status(404, "Not found")

    def test_raise_for_status_server_error(self):
        """Test 5xx raises StacheAPIError."""
        with pytest.raises(StacheAPIError) as exc_info:
            raise_for_status(500, "Server error")
        assert exc_info.value.status_code == 500

    def test_raise_for_status_success(self):
        """Test success codes don't raise."""
        raise_for_status(200, "OK")  # Should not raise
        raise_for_status(201, "Created")  # Should not raise
