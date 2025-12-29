"""Plugin interfaces for stache-tools extensions."""

from .base import StachePlugin
from .enrichment import (
    EnrichmentPlugin,
    EnrichmentResult,
    apply_enrichments,
    get_enrichment_plugins,
)
from .ocr import OCRProvider, get_ocr_provider

__all__ = [
    "EnrichmentPlugin",
    "EnrichmentResult",
    "OCRProvider",
    "StachePlugin",
    "apply_enrichments",
    "get_enrichment_plugins",
    "get_ocr_provider",
]
