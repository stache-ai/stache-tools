"""Tests for document loaders (DOCX, PPTX, EPUB)."""

import io
from pathlib import Path

import pytest

from stache_tools.loaders.documents import DocxLoader, EpubLoader, PptxLoader


class TestDocxLoader:
    """Tests for DOCX loader."""

    def test_extensions(self):
        """Test DOCX loader recognizes .docx extension."""
        loader = DocxLoader()
        assert loader.extensions == [".docx"]

    def test_can_handle(self):
        """Test DOCX loader can handle .docx files."""
        loader = DocxLoader()
        assert loader.can_handle("document.docx")
        assert loader.can_handle("Document.DOCX")
        assert not loader.can_handle("document.pdf")

    @pytest.mark.integration
    def test_load_docx(self):
        """Test loading actual DOCX file."""
        # This test requires a real DOCX file to exist
        # In practice, you'd create a minimal test fixture
        pytest.skip("Requires test fixture DOCX file")


class TestPptxLoader:
    """Tests for PPTX loader."""

    def test_extensions(self):
        """Test PPTX loader recognizes .pptx extension."""
        loader = PptxLoader()
        assert loader.extensions == [".pptx"]

    def test_can_handle(self):
        """Test PPTX loader can handle .pptx files."""
        loader = PptxLoader()
        assert loader.can_handle("presentation.pptx")
        assert loader.can_handle("Presentation.PPTX")
        assert not loader.can_handle("presentation.pdf")

    @pytest.mark.integration
    def test_load_pptx(self):
        """Test loading actual PPTX file."""
        pytest.skip("Requires test fixture PPTX file")


class TestEpubLoader:
    """Tests for EPUB loader."""

    def test_extensions(self):
        """Test EPUB loader recognizes .epub extension."""
        loader = EpubLoader()
        assert loader.extensions == [".epub"]

    def test_can_handle(self):
        """Test EPUB loader can handle .epub files."""
        loader = EpubLoader()
        assert loader.can_handle("book.epub")
        assert loader.can_handle("Book.EPUB")
        assert not loader.can_handle("book.pdf")

    @pytest.mark.integration
    def test_load_epub(self):
        """Test loading actual EPUB file."""
        pytest.skip("Requires test fixture EPUB file")
