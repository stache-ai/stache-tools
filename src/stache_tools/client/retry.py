"""Shared retry configuration and utilities.

This module centralizes retry configuration used by both HTTP and Lambda
transports, ensuring consistent behavior across transports.
"""

import logging
from typing import Callable

from tenacity import (
    before_sleep_log,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)

from .exceptions import StacheAPIError, StacheConnectionError

logger = logging.getLogger("stache-tools")


# Shared retry configuration - used by all transports
RETRY_CONFIG = {
    "stop": stop_after_attempt(3),
    "wait": wait_exponential_jitter(initial=1, max=10, jitter=2),
    "reraise": True,
}


def get_retry_decorator(is_retryable: Callable[[BaseException], bool]):
    """Create a retry decorator with the shared config.

    Args:
        is_retryable: Function that takes an exception and returns True
            if the operation should be retried.

    Returns:
        A tenacity retry decorator configured with standard settings.

    Example:
        @get_retry_decorator(_is_retryable_http)
        def my_method(self):
            ...
    """
    from tenacity import retry

    return retry(
        stop=RETRY_CONFIG["stop"],
        wait=RETRY_CONFIG["wait"],
        retry=retry_if_exception(is_retryable),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=RETRY_CONFIG["reraise"],
    )


def is_retryable_status_code(status_code: int) -> bool:
    """Check if an HTTP status code indicates a retryable error.

    Args:
        status_code: HTTP status code

    Returns:
        True if the status code is 429 (rate limit) or 5xx (server error)
    """
    return status_code == 429 or (500 <= status_code < 600)


def is_retryable_api_error(exception: BaseException) -> bool:
    """Check if a StacheAPIError is retryable based on status code.

    Args:
        exception: The exception to check

    Returns:
        True if the exception is a StacheAPIError with a retryable status code
    """
    if isinstance(exception, StacheAPIError):
        return is_retryable_status_code(exception.status_code)
    return False


def is_retryable_connection_error(exception: BaseException) -> bool:
    """Check if the exception is a connection error.

    Args:
        exception: The exception to check

    Returns:
        True if the exception is a StacheConnectionError
    """
    return isinstance(exception, StacheConnectionError)
