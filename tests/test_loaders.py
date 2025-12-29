"""Tests for document loaders."""

import io
import pytest

from stache_tools.loaders import LoaderRegistry
from stache_tools.loaders.text import TextLoader, MarkdownLoader
from stache_tools.loaders.base import LoadedDocument


class TestTextLoader:
    """Tests for TextLoader."""

    def test_extensions(self):
        """Test supported extensions."""
        loader = TextLoader()
        assert ".txt" in loader.extensions

    def test_load_text(self):
        """Test loading text content."""
        loader = TextLoader()
        content = b"Hello, world!"
        file = io.BytesIO(content)

        result = loader.load(file, "test.txt")

        assert isinstance(result, LoadedDocument)
        assert result.text == "Hello, world!"
        assert result.metadata["filename"] == "test.txt"

    def test_can_handle(self):
        """Test file type detection."""
        loader = TextLoader()
        assert loader.can_handle("file.txt")
        assert loader.can_handle("FILE.TXT")
        assert not loader.can_handle("file.pdf")


class TestMarkdownLoader:
    """Tests for MarkdownLoader."""

    def test_extensions(self):
        """Test supported extensions."""
        loader = MarkdownLoader()
        assert ".md" in loader.extensions
        assert ".markdown" in loader.extensions

    def test_load_markdown(self):
        """Test loading markdown content."""
        loader = MarkdownLoader()
        content = b"# Title\n\nSome content"
        file = io.BytesIO(content)

        result = loader.load(file, "test.md")

        assert result.text == "# Title\n\nSome content"
        assert result.metadata["type"] == "markdown"
        assert result.metadata["title"] == "Title"


class TestLoaderRegistry:
    """Tests for LoaderRegistry."""

    def test_singleton(self):
        """Test registry is a singleton."""
        reg1 = LoaderRegistry()
        reg2 = LoaderRegistry()
        assert reg1 is reg2

    def test_get_loader_by_extension(self):
        """Test finding loader by file extension."""
        registry = LoaderRegistry()
        loader = registry.get_loader("test.txt")
        assert isinstance(loader, TextLoader)

    def test_get_loader_unknown(self):
        """Test unknown extension returns None."""
        registry = LoaderRegistry()
        loader = registry.get_loader("test.xyz")
        assert loader is None
