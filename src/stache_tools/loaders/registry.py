"""Plugin discovery and registration for document loaders."""

import logging
import os
import threading
from importlib.metadata import entry_points
from typing import Optional

from .base import DocumentLoader

logger = logging.getLogger("stache-tools")


class LoaderRegistry:
    """Thread-safe singleton registry for document loaders."""

    _instance: Optional["LoaderRegistry"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "LoaderRegistry":
        """Ensure singleton via __new__."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    instance = super().__new__(cls)
                    instance._loaders = []
                    instance._extension_overrides = {}
                    instance._initialized = False
                    cls._instance = instance
        return cls._instance

    def __init__(self):
        """Initialize the registry (only runs once)."""
        if self._initialized:
            return

        with LoaderRegistry._lock:
            if self._initialized:
                return

            self._load_overrides()
            self._load_builtin()
            self._load_plugins()
            self._initialized = True

    def _load_overrides(self) -> None:
        """Load extension overrides from environment."""
        for key, value in os.environ.items():
            if key.startswith("STACHE_LOADER_"):
                ext = "." + key[14:].lower()
                self._extension_overrides[ext] = value
                logger.debug(f"Loader override: {ext} -> {value}")

    def _load_builtin(self) -> None:
        """Load built-in loaders."""
        from .documents import DocxLoader, EpubLoader, PptxLoader
        from .pdf import BasicPDFLoader
        from .text import MarkdownLoader, TextLoader

        self._loaders.extend([
            TextLoader(),
            MarkdownLoader(),
            BasicPDFLoader(),
            DocxLoader(),
            PptxLoader(),
            EpubLoader(),
        ])
        logger.debug(f"Loaded {len(self._loaders)} built-in loaders")

    def _load_plugins(self) -> None:
        """Discover and load plugin loaders."""
        try:
            eps = entry_points(group="stache_tools.loaders")
            for ep in eps:
                try:
                    loader_class = ep.load()
                    loader = loader_class()
                    self._loaders.append(loader)
                    logger.info(f"Loaded plugin loader: {ep.name}")
                except Exception as e:
                    logger.warning(f"Failed to load plugin {ep.name}: {e}")
        except Exception as e:
            logger.warning(f"Error discovering plugins: {e}")

    def get_loader(self, filename: str) -> DocumentLoader | None:
        """Get loader for file (checks overrides, then priority)."""
        ext = "." + filename.lower().split(".")[-1] if "." in filename else ""

        if ext in self._extension_overrides:
            override_name = self._extension_overrides[ext]
            for loader in self._loaders:
                if type(loader).__name__.lower() == override_name.lower():
                    return loader
            logger.warning(f"Override loader '{override_name}' not found for {ext}")

        candidates = [ldr for ldr in self._loaders if ldr.can_handle(filename)]
        if not candidates:
            return None

        return max(candidates, key=lambda ldr: ldr.priority)

    def supported_extensions(self) -> list[str]:
        """List all supported extensions."""
        exts = set()
        for loader in self._loaders:
            exts.update(ext.lower() for ext in loader.extensions)
        return sorted(exts)

    def register(self, loader: DocumentLoader) -> None:
        """Manually register a loader."""
        with LoaderRegistry._lock:
            self._loaders.append(loader)

    @classmethod
    def _reset(cls) -> None:
        """Reset singleton for testing. Do not use in production."""
        with cls._lock:
            cls._instance = None
