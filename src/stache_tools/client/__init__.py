"""Stache API client.

This package provides the client library for communicating with Stache.
It supports two transport modes:

HTTP Transport (default):
    Uses API Gateway with OAuth authentication. Requires Cognito credentials.

Lambda Transport:
    Direct Lambda invocation using AWS credentials. Lower latency, simpler auth.
    Requires: pip install stache-tools[lambda]

Usage:
    from stache_tools.client import StacheAPI, StacheConfig

    # Auto-detect transport from environment
    api = StacheAPI()
    results = api.search("my query")

    # Explicit Lambda transport
    config = StacheConfig(
        transport="lambda",
        lambda_function_name="stache-api",
    )
    api = StacheAPI(config)
"""

from .api import StacheAPI
from .config import StacheConfig
from .exceptions import (
    StacheAPIError,
    StacheAuthError,
    StacheConnectionError,
    StacheError,
    StacheNotFoundError,
)
from .factory import create_transport
from .http import HTTPTransport, StacheHTTPClient
from .transport import StacheTransport

# Conditional export of LambdaTransport
try:
    from .lambda_transport import LambdaTransport

    _LAMBDA_AVAILABLE = True
except ImportError:
    LambdaTransport = None  # type: ignore
    _LAMBDA_AVAILABLE = False

__all__ = [
    # Main API
    "StacheAPI",
    "StacheConfig",
    # Transport protocol and factory
    "StacheTransport",
    "create_transport",
    # Transport implementations
    "HTTPTransport",
    "StacheHTTPClient",  # Backwards compatibility
    "LambdaTransport",
    # Exceptions
    "StacheAPIError",
    "StacheAuthError",
    "StacheConnectionError",
    "StacheError",
    "StacheNotFoundError",
]
