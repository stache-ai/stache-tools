"""Base classes for stache-tools plugins."""

from abc import ABC, abstractmethod


class StachePlugin(ABC):
    """Base class for all stache-tools plugins.

    Register plugins via entry points in pyproject.toml.
    Available groups: stache_tools.loaders, stache_tools.ocr, stache_tools.enrichment
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Plugin name (unique identifier)."""
        pass

    @property
    def version(self) -> str:
        """Plugin version."""
        return "0.1.0"

    @property
    def priority(self) -> int:
        """Plugin priority (higher = preferred). Default 10."""
        return 10
