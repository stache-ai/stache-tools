"""Text and Markdown document loaders."""

from typing import BinaryIO

from .base import DocumentLoader, LoadedDocument


class TextLoader(DocumentLoader):
    """Loader for plain text files."""

    @property
    def extensions(self) -> list[str]:
        return [".txt"]

    def load(self, file: BinaryIO, filename: str) -> LoadedDocument:
        content = file.read()
        text = content.decode("utf-8", errors="replace")
        return LoadedDocument(
            text=text,
            metadata={"filename": filename, "type": "text"},
        )


class MarkdownLoader(DocumentLoader):
    """Loader for Markdown files."""

    @property
    def extensions(self) -> list[str]:
        return [".md", ".markdown"]

    def load(self, file: BinaryIO, filename: str) -> LoadedDocument:
        content = file.read()
        text = content.decode("utf-8", errors="replace")

        title = None
        for line in text.split("\n"):
            if line.startswith("# "):
                title = line[2:].strip()
                break

        metadata = {"filename": filename, "type": "markdown"}
        if title:
            metadata["title"] = title

        return LoadedDocument(text=text, metadata=metadata)
