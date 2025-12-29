"""Abstract base class for document loaders."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import BinaryIO


@dataclass
class LoadedDocument:
    """Result of loading a document."""
    text: str
    metadata: dict = field(default_factory=dict)


class DocumentLoader(ABC):
    """Base class for document loaders.

    Built-in loaders have priority 0. Plugin loaders should use 10+ to override.
    """

    @property
    @abstractmethod
    def extensions(self) -> list[str]:
        """File extensions this loader handles (e.g., ['.pdf'])."""
        pass

    @property
    def priority(self) -> int:
        """Loader priority (higher = preferred). Default 0 for built-in."""
        return 0

    @abstractmethod
    def load(self, file: BinaryIO, filename: str) -> LoadedDocument:
        """Load document and extract text."""
        pass

    def can_handle(self, filename: str) -> bool:
        """Check if this loader can handle the file."""
        lower = filename.lower()
        return any(lower.endswith(ext.lower()) for ext in self.extensions)
