"""PDF document loader using pypdf."""

import logging
import warnings
from typing import BinaryIO

from pypdf import PdfReader

from .base import DocumentLoader, LoadedDocument

logger = logging.getLogger("stache-tools")


class BasicPDFLoader(DocumentLoader):
    """Basic PDF loader using pypdf (no OCR)."""

    @property
    def extensions(self) -> list[str]:
        return [".pdf"]

    def load(self, file: BinaryIO, filename: str) -> LoadedDocument:
        # Suppress pypdf warnings about malformed PDFs (they usually still extract fine)
        # These warnings like "Ignoring wrong pointing object" are common in PDFs
        # converted from other formats or with complex layouts
        pypdf_logger = logging.getLogger('pypdf._reader')
        original_level = pypdf_logger.level
        pypdf_logger.setLevel(logging.ERROR)

        try:
            reader = PdfReader(file)
        finally:
            pypdf_logger.setLevel(original_level)

        text_parts = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                text_parts.append(text)

        metadata = {"filename": filename, "type": "pdf"}

        if not text_parts:
            logger.warning(f"No text extracted from {filename} - may be scanned PDF")
            metadata["extraction_failed"] = True
        if reader.metadata:
            if reader.metadata.title:
                metadata["title"] = reader.metadata.title
            if reader.metadata.author:
                metadata["author"] = reader.metadata.author

        metadata["page_count"] = len(reader.pages)

        return LoadedDocument(
            text="\n\n".join(text_parts),
            metadata=metadata,
        )
