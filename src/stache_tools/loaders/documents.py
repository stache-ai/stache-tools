"""Document format loaders (DOCX, PPTX, EPUB) using stache-ai-documents adapters."""

import logging
import tempfile
from pathlib import Path
from typing import BinaryIO

from .base import DocumentLoader, LoadedDocument

logger = logging.getLogger("stache-tools")


class DocxLoader(DocumentLoader):
    """Microsoft Word (.docx) document loader.

    Adapter for stache-ai-documents DocxLoader to work with stache-tools BinaryIO interface.
    """

    @property
    def extensions(self) -> list[str]:
        return [".docx"]

    def load(self, file: BinaryIO, filename: str) -> LoadedDocument:
        """Load DOCX file by writing to temp file (stache-ai loaders expect file_path)."""
        from stache_ai_documents.docx import DocxLoader as AiDocxLoader

        # Write BinaryIO to temp file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp:
            tmp.write(file.read())
            tmp_path = tmp.name

        try:
            # Use stache-ai loader
            ai_loader = AiDocxLoader()
            text = ai_loader.load(tmp_path)

            return LoadedDocument(
                text=text,
                metadata={
                    "filename": filename,
                    "type": "docx",
                    "loader": "stache-ai-documents",
                },
            )
        finally:
            # Clean up temp file
            Path(tmp_path).unlink(missing_ok=True)


class PptxLoader(DocumentLoader):
    """Microsoft PowerPoint (.pptx) presentation loader.

    Adapter for stache-ai-documents PptxLoader to work with stache-tools BinaryIO interface.
    """

    @property
    def extensions(self) -> list[str]:
        return [".pptx"]

    def load(self, file: BinaryIO, filename: str) -> LoadedDocument:
        """Load PPTX file by writing to temp file (stache-ai loaders expect file_path)."""
        from stache_ai_documents.pptx import PptxLoader as AiPptxLoader

        # Write BinaryIO to temp file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pptx") as tmp:
            tmp.write(file.read())
            tmp_path = tmp.name

        try:
            # Use stache-ai loader
            ai_loader = AiPptxLoader()
            text = ai_loader.load(tmp_path)

            return LoadedDocument(
                text=text,
                metadata={
                    "filename": filename,
                    "type": "pptx",
                    "loader": "stache-ai-documents",
                },
            )
        finally:
            # Clean up temp file
            Path(tmp_path).unlink(missing_ok=True)


class EpubLoader(DocumentLoader):
    """EPUB eBook format loader.

    Adapter for stache-ai-documents EpubLoader to work with stache-tools BinaryIO interface.
    """

    @property
    def extensions(self) -> list[str]:
        return [".epub"]

    def load(self, file: BinaryIO, filename: str) -> LoadedDocument:
        """Load EPUB file by writing to temp file (stache-ai loaders expect file_path)."""
        from stache_ai_documents.epub import EpubLoader as AiEpubLoader

        # Write BinaryIO to temp file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".epub") as tmp:
            tmp.write(file.read())
            tmp_path = tmp.name

        try:
            # Use stache-ai loader
            ai_loader = AiEpubLoader()
            text = ai_loader.load(tmp_path)

            return LoadedDocument(
                text=text,
                metadata={
                    "filename": filename,
                    "type": "epub",
                    "loader": "stache-ai-documents",
                },
            )
        finally:
            # Clean up temp file
            Path(tmp_path).unlink(missing_ok=True)
