"""Document loaders with plugin architecture."""

from pathlib import Path
from typing import BinaryIO

from .base import DocumentLoader, LoadedDocument
from .pdf import BasicPDFLoader
from .registry import LoaderRegistry
from .text import MarkdownLoader, TextLoader


def load_document(file_or_path: str | Path | BinaryIO, filename: str | None = None) -> LoadedDocument:
    """Load document using appropriate loader."""
    registry = LoaderRegistry()

    if isinstance(file_or_path, (str, Path)):
        path = Path(file_or_path)
        filename = filename or path.name
        with open(path, "rb") as f:
            loader = registry.get_loader(filename)
            if not loader:
                supported = ", ".join(registry.supported_extensions())
                raise ValueError(f"Unsupported file type: {filename}. Supported: {supported}")
            return loader.load(f, filename)
    else:
        if not filename:
            raise ValueError("filename required for file-like objects")
        loader = registry.get_loader(filename)
        if not loader:
            supported = ", ".join(registry.supported_extensions())
            raise ValueError(f"Unsupported file type: {filename}. Supported: {supported}")
        return loader.load(file_or_path, filename)


__all__ = [
    "BasicPDFLoader",
    "DocumentLoader",
    "LoadedDocument",
    "LoaderRegistry",
    "MarkdownLoader",
    "TextLoader",
    "load_document",
]
