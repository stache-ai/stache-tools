"""Enrichment plugin interface for metadata enhancement."""

import logging
from abc import abstractmethod
from dataclasses import dataclass, field
from importlib.metadata import entry_points

from .base import StachePlugin

logger = logging.getLogger("stache-tools")


@dataclass
class EnrichmentResult:
    """Result of document enrichment."""
    text: str
    metadata: dict = field(default_factory=dict)


class EnrichmentPlugin(StachePlugin):
    """Base class for enrichment plugins."""

    @abstractmethod
    def enrich(self, text: str, metadata: dict) -> EnrichmentResult:
        """Enrich the document."""
        pass


def get_enrichment_plugins() -> list[EnrichmentPlugin]:
    """Get all available enrichment plugins sorted by priority."""
    plugins = []

    try:
        eps = entry_points(group="stache_tools.enrichment")
        for ep in eps:
            try:
                plugin_class = ep.load()
                plugins.append(plugin_class())
                logger.debug(f"Loaded enrichment plugin: {ep.name}")
            except Exception as e:
                logger.warning(f"Failed to load enrichment plugin {ep.name}: {e}")
    except Exception as e:
        logger.debug(f"No enrichment plugins found: {e}")

    plugins.sort(key=lambda p: p.priority, reverse=True)
    return plugins


def apply_enrichments(text: str, metadata: dict) -> tuple[str, dict]:
    """Apply all enrichment plugins to document."""
    plugins = get_enrichment_plugins()

    current_text = text
    merged_metadata = metadata.copy()

    for plugin in plugins:
        try:
            result = plugin.enrich(current_text, merged_metadata)
            current_text = result.text
            merged_metadata.update(result.metadata)
        except Exception as e:
            logger.warning(f"Enrichment plugin {plugin.name} failed: {e}")

    return current_text, merged_metadata
