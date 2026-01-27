"""PDF and image loaders with OCR using Tesseract/ocrmypdf.

This module provides thin adapters that wrap stache-ai-ocr to provide
BinaryIO-compatible interfaces for the stache-tools CLI.
"""

import logging
import tempfile
from pathlib import Path
from typing import BinaryIO

from .base import DocumentLoader, LoadedDocument

logger = logging.getLogger(__name__)

# Optional dependency - only import if stache-ai-ocr is installed
try:
    from stache_ai_ocr import OcrPdfLoader as AiOcrPdfLoader
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False

# Optional dependency - only needed for image OCR
try:
    from PIL import Image
    import pytesseract
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False


class OcrPdfLoader(DocumentLoader):
    """Adapter: wraps stache-ai-ocr for BinaryIO interface.

    This is a thin adapter that converts BinaryIO input to file paths
    for stache-ai-ocr, then maps the OcrLoadResult back to LoadedDocument.

    All OCR logic lives in stache-ai-ocr - this just handles the interface gap.

    Requires: pip install stache-ai-ocr
    """

    def __init__(self, timeout: int | None = None):
        """Initialize adapter with stache-ai-ocr loader.

        Args:
            timeout: OCR timeout in seconds (default: 300). Overrides STACHE_OCR_TIMEOUT env var.
        """
        if not OCR_AVAILABLE:
            raise ImportError(
                "stache-ai-ocr is required for OCR support. Install with:\n"
                "  pip install stache-tools[ocr]\n"
                "or:\n"
                "  pip install stache-ai-ocr"
            )
        self._ai_loader = AiOcrPdfLoader(timeout=timeout)

    @property
    def extensions(self) -> list[str]:
        return ['.pdf']

    @property
    def priority(self) -> int:
        return 10  # Override BasicPDFLoader (priority 0)

    def load(self, file: BinaryIO, filename: str) -> LoadedDocument:
        """Load PDF with OCR support.

        Args:
            file: Binary file object to read from
            filename: Name of the file (for logging and metadata)

        Returns:
            LoadedDocument with extracted text and OCR metadata
        """
        # Write BinaryIO to temp file (stache-ai-ocr expects file_path)
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir) / filename
            tmp_path.write_bytes(file.read())

            # Delegate to stache-ai-ocr
            result = self._ai_loader.load_with_metadata(str(tmp_path))

            # Map OcrLoadResult → LoadedDocument
            # Only include source - other OCR metadata is internal diagnostics
            return LoadedDocument(
                text=result.text,
                metadata={'source': filename}
            )


class OcrImageLoader(DocumentLoader):
    """Image loader using Tesseract OCR.

    Requires pytesseract and Pillow:
    - pip install pytesseract pillow
    - Ubuntu/Debian: apt install tesseract-ocr
    - macOS: brew install tesseract
    - Windows: choco install tesseract

    Falls back gracefully if not installed.
    """

    @property
    def extensions(self) -> list[str]:
        return ['.jpg', '.jpeg', '.png', '.tiff', '.tif', '.bmp', '.gif']

    @property
    def priority(self) -> int:
        return 5  # Standard priority for OCR

    def load(self, file: BinaryIO, filename: str) -> LoadedDocument:
        """Extract text from image using Tesseract OCR."""
        if not TESSERACT_AVAILABLE:
            logger.warning(
                f"Cannot OCR {filename}: pytesseract not installed. Install with:\n"
                "  pip install pytesseract pillow\n"
                "  Ubuntu/Debian: sudo apt install tesseract-ocr\n"
                "  macOS: brew install tesseract\n"
                "  Windows: choco install tesseract"
            )
            return LoadedDocument(
                text="",
                metadata={'source': filename}
            )

        try:
            # Load image
            image = Image.open(file)

            # Extract text with Tesseract
            text = pytesseract.image_to_string(image)

            logger.info(f"OCR extracted {len(text)} characters from {filename}")

            return LoadedDocument(
                text=text,
                metadata={'source': filename}
            )

        except FileNotFoundError as e:
            # Tesseract binary not found
            if 'tesseract' in str(e).lower():
                logger.warning(
                    f"Tesseract binary not found. Install with:\n"
                    "  Ubuntu/Debian: sudo apt install tesseract-ocr\n"
                    "  macOS: brew install tesseract\n"
                    "  Windows: choco install tesseract"
                )
            else:
                logger.warning(f"File error during OCR: {e}")

            return LoadedDocument(
                text="",
                metadata={'source': filename}
            )

        except Exception as e:
            logger.warning(f"OCR error on {filename}: {e}")
            return LoadedDocument(
                text="",
                metadata={'source': filename}
            )
