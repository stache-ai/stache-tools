"""Transport factory for creating configured transports.

This module provides a factory function that creates the appropriate transport
based on configuration. It abstracts transport selection from the API layer.
"""

from .config import StacheConfig
from .transport import StacheTransport


def create_transport(config: StacheConfig | None = None) -> StacheTransport:
    """Create appropriate transport based on configuration.

    Examines the configuration to determine which transport to use:
    - If transport="lambda" or auto-detected as Lambda: Creates LambdaTransport
    - Otherwise: Creates HTTPTransport

    Args:
        config: Stache configuration. If None, loads from environment.

    Returns:
        Configured transport implementing StacheTransport protocol.

    Raises:
        ValueError: If configuration is invalid for selected transport
            (e.g., Lambda transport without function name).
        ImportError: If boto3 not installed when Lambda transport is needed.

    Example:
        # Auto-detect based on environment
        transport = create_transport()

        # Explicit configuration
        config = StacheConfig(transport="lambda", lambda_function_name="my-fn")
        transport = create_transport(config)
    """
    config = config or StacheConfig()
    config.validate_config()

    transport_type = config.resolved_transport

    if transport_type == "lambda":
        from .lambda_transport import LambdaTransport

        return LambdaTransport(config)
    else:
        from .http import HTTPTransport

        return HTTPTransport(config)
