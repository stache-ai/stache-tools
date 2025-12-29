"""Stache Tools - Client library, CLI, and MCP server for Stache RAG system."""

from stache_tools.client import StacheAPI as StacheClient
from stache_tools.client.config import StacheConfig
from stache_tools.client.exceptions import (
    StacheAPIError,
    StacheAuthError,
    StacheConnectionError,
    StacheError,
    StacheNotFoundError,
)
from stache_tools.loaders import LoaderRegistry
from stache_tools.loaders.base import DocumentLoader, LoadedDocument

try:
    from importlib.metadata import version
    __version__ = version("stache-tools")
except Exception:
    __version__ = "0.1.0"  # Fallback for development

__all__ = [
    "DocumentLoader",
    "LoadedDocument",
    "LoaderRegistry",
    "StacheAPIError",
    "StacheAuthError",
    "StacheClient",
    "StacheConfig",
    "StacheConnectionError",
    "StacheError",
    "StacheNotFoundError",
    "__version__",
]
