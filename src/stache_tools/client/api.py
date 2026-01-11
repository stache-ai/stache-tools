"""High-level API for Stache operations.

This module provides the main client interface for interacting with Stache.
It automatically selects the appropriate transport (HTTP or Lambda) based
on configuration.
"""

from typing import Any

from .config import StacheConfig
from .factory import create_transport
from .transport import StacheTransport


class StacheAPI:
    """High-level API for Stache operations.

    Automatically selects HTTP or Lambda transport based on configuration.
    Provides methods for all Stache operations: search, ingest, namespace
    management, and document operations.

    Usage:
        # Auto-configure from environment
        api = StacheAPI()
        results = api.search("my query")

        # Explicit configuration
        config = StacheConfig(lambda_function_name="stache-api")
        api = StacheAPI(config)

        # Inject custom transport (for testing)
        api = StacheAPI(transport=mock_transport)
    """

    def __init__(
        self,
        config: StacheConfig | None = None,
        transport: StacheTransport | None = None,
    ):
        """Initialize API client.

        Args:
            config: Configuration (loads from environment if None)
            transport: Optional pre-configured transport (for testing/advanced use).
                If provided, config is still stored but not used to create transport.
        """
        self.config = config or StacheConfig()
        self._client = transport or create_transport(self.config)

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
        return False

    @property
    def last_request_id(self) -> str | None:
        """Get request_id from last API call."""
        return self._client.last_request_id

    def close(self) -> None:
        """Close API client and release resources."""
        self._client.close()

    def search(
        self,
        query: str,
        namespace: str | None = None,
        top_k: int = 20,
        rerank: bool = True,
        filter: dict | None = None,
        synthesize: bool = True,
        model: str | None = None,
    ) -> dict[str, Any]:
        """Semantic search.

        Args:
            query: Search query text
            namespace: Optional namespace to search within
            top_k: Maximum number of results (capped at 50)
            rerank: Whether to rerank results for relevance
            filter: Optional metadata filter
            synthesize: Whether to synthesize an answer using LLM (default True)
            model: Optional model ID to override default LLM for synthesis

        Returns:
            Search results with matches and optional synthesis
        """
        data: dict[str, Any] = {
            "query": query,
            "top_k": min(top_k, 50),
            "rerank": rerank,
            "synthesize": synthesize,
        }
        if namespace:
            data["namespace"] = namespace
        if filter:
            data["filter"] = filter
        if model:
            data["model"] = model
        return self._client.post("/api/query", data)

    def ingest_text(
        self,
        text: str,
        namespace: str | None = None,
        metadata: dict | None = None,
        chunking_strategy: str = "recursive",
        prepend_metadata: list[str] | None = None,
    ) -> dict[str, Any]:
        """Ingest text content.

        Args:
            text: Text content to ingest (max 10MB, server-side configurable)
            namespace: Target namespace
            metadata: Optional metadata to attach
            chunking_strategy: Chunking strategy (recursive, markdown, semantic, character)
            prepend_metadata: Metadata keys to prepend to each chunk for better search

        Returns:
            Ingest result with document ID and chunk count

        Raises:
            ValueError: If text exceeds 10MB (or server's configured limit)
        """
        # Client-side check matches default server limit
        # Server may have different limit via MAX_INGEST_TEXT_BYTES env var
        if len(text.encode("utf-8")) > 10 * 1024 * 1024:
            raise ValueError("Text exceeds maximum size of 10MB")

        data: dict[str, Any] = {
            "text": text,
            "chunking_strategy": chunking_strategy,
        }
        if namespace:
            data["namespace"] = namespace
        if metadata:
            data["metadata"] = metadata
        if prepend_metadata:
            data["prepend_metadata"] = prepend_metadata

        return self._client.post("/api/capture", data)

    def list_namespaces(self) -> dict[str, Any]:
        """List all namespaces.

        Returns:
            Dictionary with 'namespaces' list
        """
        return self._client.get("/api/namespaces", {"include_children": "true"})

    def create_namespace(
        self,
        id: str,
        name: str,
        description: str = "",
        parent_id: str | None = None,
        metadata: dict | None = None,
    ) -> dict[str, Any]:
        """Create a namespace.

        Args:
            id: Unique namespace identifier
            name: Human-readable name
            description: Optional description
            parent_id: Optional parent namespace ID
            metadata: Optional metadata

        Returns:
            Created namespace details
        """
        data = {"id": id, "name": name, "description": description}
        if parent_id:
            data["parent_id"] = parent_id
        if metadata:
            data["metadata"] = metadata
        return self._client.post("/api/namespaces", data)

    def get_namespace(self, id: str) -> dict[str, Any]:
        """Get namespace by ID.

        Args:
            id: Namespace identifier

        Returns:
            Namespace details
        """
        return self._client.get(f"/api/namespaces/{id}")

    def update_namespace(
        self,
        id: str,
        name: str | None = None,
        description: str | None = None,
        metadata: dict | None = None,
    ) -> dict[str, Any]:
        """Update a namespace.

        Args:
            id: Namespace identifier
            name: New name (optional)
            description: New description (optional)
            metadata: New metadata (optional)

        Returns:
            Updated namespace details
        """
        data = {}
        if name is not None:
            data["name"] = name
        if description is not None:
            data["description"] = description
        if metadata is not None:
            data["metadata"] = metadata
        return self._client.put(f"/api/namespaces/{id}", data)

    def delete_namespace(self, id: str, cascade: bool = False) -> dict[str, Any]:
        """Delete a namespace.

        Args:
            id: Namespace identifier
            cascade: If True, delete all documents in namespace

        Returns:
            Deletion result
        """
        return self._client.delete(f"/api/namespaces/{id}", {"cascade": cascade})

    def list_documents(
        self,
        namespace: str | None = None,
        limit: int = 50,
        next_key: str | None = None,
    ) -> dict[str, Any]:
        """List documents.

        Args:
            namespace: Optional namespace filter
            limit: Maximum documents to return (capped at 100)
            next_key: Pagination key from previous response

        Returns:
            Dictionary with 'documents' list and optional 'next_key'
        """
        params: dict[str, Any] = {"limit": min(limit, 100)}
        if namespace:
            params["namespace"] = namespace
        if next_key:
            params["next_key"] = next_key
        return self._client.get("/api/documents", params)

    def get_document(self, doc_id: str, namespace: str = "default") -> dict[str, Any]:
        """Get document by ID.

        Args:
            doc_id: Document identifier
            namespace: Namespace containing the document

        Returns:
            Document details
        """
        return self._client.get(f"/api/documents/id/{doc_id}", {"namespace": namespace})

    def delete_document(self, doc_id: str, namespace: str = "default") -> dict[str, Any]:
        """Delete a document.

        Args:
            doc_id: Document identifier
            namespace: Namespace containing the document

        Returns:
            Deletion result
        """
        return self._client.delete(f"/api/documents/id/{doc_id}", {"namespace": namespace})

    def health(self, include_auth: bool = False) -> dict[str, Any]:
        """Check API health.

        Args:
            include_auth: If True, also verify authentication works

        Returns:
            Health status with optional auth_status field
        """
        result = self._client.get("/health")

        if include_auth and self.config.oauth_enabled:
            try:
                self._client.get("/api/namespaces", {"limit": 1})
                result["auth_status"] = "valid"
            except Exception as e:
                result["auth_status"] = f"failed: {e}"

        return result

    def list_models(self) -> dict[str, Any]:
        """List available LLM models.

        Returns:
            Dictionary with 'models' list, 'grouped' by tier, 'default', and 'provider'
        """
        return self._client.get("/api/models")

    def upload(
        self,
        file_path: str,
        namespace: str = "default",
        metadata: dict | None = None,
    ) -> dict[str, Any]:
        """Upload a file directly to the API.

        Note: For local files, prefer using ingest_text() with a loader.
        This method sends the file to the API for server-side processing.

        Args:
            file_path: Path to the file to upload
            namespace: Target namespace
            metadata: Optional metadata to attach

        Returns:
            Upload result with document ID
        """
        import base64
        from pathlib import Path

        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        with open(path, "rb") as f:
            content = base64.b64encode(f.read()).decode("utf-8")

        return self._client.post("/api/upload", {
            "filename": path.name,
            "content": content,
            "content_type": "application/octet-stream",
            "namespace": namespace,
            "metadata": metadata or {},
        })
