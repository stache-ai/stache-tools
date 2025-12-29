"""OCR plugin interface for scanned document support."""

import logging
import os
from abc import abstractmethod
from importlib.metadata import entry_points

from .base import StachePlugin

logger = logging.getLogger("stache-tools")

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    Image = None


class OCRProvider(StachePlugin):
    """Base class for OCR providers."""

    @abstractmethod
    def extract_text(self, image: "Image.Image") -> str:
        """Extract text from an image."""
        pass

    def extract_text_from_path(self, image_path: str) -> str:
        """Extract text from image file path."""
        if not PIL_AVAILABLE:
            raise RuntimeError("PIL/Pillow required for OCR")

        with Image.open(image_path) as img:
            return self.extract_text(img)


def get_ocr_provider() -> OCRProvider | None:
    """Get configured OCR provider."""
    preferred = os.environ.get("STACHE_OCR_PROVIDER")

    try:
        eps = entry_points(group="stache_tools.ocr")

        if preferred:
            for ep in eps:
                if ep.name == preferred:
                    try:
                        provider_class = ep.load()
                        return provider_class()
                    except Exception as e:
                        logger.warning(f"Failed to load preferred OCR '{preferred}': {e}")

        for ep in eps:
            try:
                provider_class = ep.load()
                return provider_class()
            except Exception:
                continue

    except Exception as e:
        logger.debug(f"No OCR plugins found: {e}")

    return None
