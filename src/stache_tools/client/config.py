"""Configuration for Stache API client."""

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class StacheConfig(BaseSettings):
    """Configuration for Stache API client.

    All settings can be configured via environment variables with STACHE_ prefix.

    Transport Selection:
        - transport="auto" (default): Uses Lambda if STACHE_LAMBDA_FUNCTION is set,
          otherwise uses HTTP
        - transport="http": Forces HTTP transport via API Gateway
        - transport="lambda": Forces Lambda direct invocation

    HTTP Transport (via API Gateway):
        - STACHE_API_URL: API Gateway endpoint
        - STACHE_COGNITO_*: OAuth credentials for authentication

    Lambda Transport (direct invocation):
        - STACHE_LAMBDA_FUNCTION: Lambda function name or ARN
        - AWS_PROFILE/AWS_REGION: AWS credentials configuration
    """

    model_config = SettingsConfigDict(
        env_prefix="STACHE_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Transport selection
    transport: str = Field(
        default="auto",
        description="Transport mode: 'http', 'lambda', or 'auto'",
    )

    # HTTP transport settings
    api_url: str = Field(
        default="http://localhost:8000",
        validation_alias=AliasChoices("api_url", "STACHE_API_URL", "STACHE_URL"),
    )
    timeout: float = Field(default=60.0, ge=1.0, le=300.0)

    # OAuth settings (for HTTP transport)
    cognito_client_id: str | None = Field(default=None)
    cognito_client_secret: str | None = Field(default=None)
    cognito_token_url: str | None = Field(default=None)
    cognito_scope: str | None = Field(default=None)

    # Lambda transport settings
    lambda_function_name: str | None = Field(
        default=None,
        validation_alias=AliasChoices("lambda_function_name", "STACHE_LAMBDA_FUNCTION"),
        description="Lambda function name or ARN for direct invocation",
    )
    aws_profile: str | None = Field(
        default=None,
        description="AWS profile name (uses default credential chain if not set)",
    )
    aws_region: str = Field(
        default="us-east-1",
        description="AWS region for Lambda invocation",
    )
    lambda_timeout: float = Field(
        default=60.0,
        ge=1.0,
        le=900.0,  # Lambda max is 15 minutes
        description="Read timeout for Lambda invocations (seconds)",
    )

    log_level: str = Field(default="INFO")

    @field_validator("transport")
    @classmethod
    def validate_transport(cls, v: str) -> str:
        """Validate transport mode is one of the allowed values."""
        valid = {"http", "lambda", "auto"}
        if v.lower() not in valid:
            raise ValueError(f"Invalid transport: {v}. Must be one of {valid}")
        return v.lower()

    @field_validator("api_url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        """Validate URL format and strip trailing slash."""
        if not v.startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")
        return v.rstrip("/")

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level is a valid Python logging level."""
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v.upper() not in valid:
            raise ValueError(f"Invalid log level: {v}")
        return v.upper()

    @property
    def resolved_transport(self) -> str:
        """Determine actual transport to use.

        Returns:
            "http" or "lambda" based on configuration.

        When transport is "auto":
            - Returns "lambda" if lambda_function_name is set
            - Returns "http" otherwise
        """
        if self.transport != "auto":
            return self.transport
        # Auto-detect: prefer Lambda if configured, otherwise HTTP
        if self.lambda_function_name:
            return "lambda"
        return "http"

    @property
    def oauth_enabled(self) -> bool:
        """Check if OAuth is configured for HTTP transport."""
        return all([
            self.cognito_client_id,
            self.cognito_client_secret,
            self.cognito_token_url,
        ])

    def validate_config(self) -> None:
        """Validate that required config is present for selected transport.

        Call this after construction to get helpful error messages about
        missing configuration.

        Raises:
            ValueError: If configuration is incomplete for the selected transport.
        """
        transport = self.resolved_transport

        if transport == "lambda":
            if not self.lambda_function_name:
                raise ValueError(
                    "Lambda transport requires STACHE_LAMBDA_FUNCTION to be set. "
                    "Example: STACHE_LAMBDA_FUNCTION=stache-api"
                )
        # HTTP transport: api_url has a default, so it's always valid
