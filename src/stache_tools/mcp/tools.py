"""MCP tool definitions matching serverless implementation."""

import asyncio
import logging
import re
from typing import Any

from mcp.types import TextContent, Tool

from ..client import StacheAPI, StacheConfig
from .formatters import (
    format_document,
    format_document_list,
    format_ingest_result,
    format_namespace_list,
    format_search_results,
)

logger = logging.getLogger("stache-tools")

# Validation pattern for namespace/document IDs
ID_PATTERN = re.compile(r'^[a-zA-Z0-9_/-]+$')
MAX_ID_LENGTH = 200


def validate_id(id_value: str, id_type: str = "ID") -> str | None:
    """Validate namespace or document ID.

    Returns None if valid, error message if invalid.
    """
    if not id_value:
        return f"{id_type} cannot be empty"

    if len(id_value) > MAX_ID_LENGTH:
        return f"{id_type} too long (max {MAX_ID_LENGTH} characters)"

    if not ID_PATTERN.match(id_value):
        return f"{id_type} contains invalid characters (only alphanumeric, hyphens, underscores, and slashes allowed)"

    return None


def get_tool_definitions() -> list[Tool]:
    """Return MCP tool definitions including enterprise tools if available."""
    tools = [
        Tool(
            name="search",
            description="Semantic search in Stache knowledge base. Returns relevant text chunks ranked by relevance.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query", "maxLength": 10000},
                    "namespace": {"type": "string", "description": "Optional namespace filter", "maxLength": 100},
                    "top_k": {"type": "integer", "description": "Number of results (default 20, max 50)", "default": 20, "minimum": 1, "maximum": 50},
                    "rerank": {"type": "boolean", "description": "Whether to rerank results for relevance (default true)", "default": True},
                    "filter": {"type": "object", "description": "Metadata filter (e.g. {\"source\": \"docs\"})"},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="ingest_text",
            description="Add text content to Stache knowledge base. Use to save notes, documentation, or synthesized information.",
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text content to ingest (max 100KB)"},
                    "namespace": {"type": "string", "description": "Target namespace", "maxLength": 100},
                    "metadata": {"type": "object", "description": "Optional metadata to attach"},
                    "chunking_strategy": {
                        "type": "string",
                        "description": "Chunking strategy",
                        "enum": ["recursive", "markdown", "semantic", "character"],
                        "default": "recursive"
                    },
                    "prepend_metadata": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Metadata keys to prepend to chunks for better search (e.g. ['author', 'topic'])"
                    },
                },
                "required": ["text"],
            },
        ),
        Tool(
            name="list_namespaces",
            description="List all namespaces in the knowledge base.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="list_documents",
            description="List documents, optionally filtered by namespace.",
            inputSchema={
                "type": "object",
                "properties": {
                    "namespace": {"type": "string", "description": "Optional namespace filter"},
                    "limit": {"type": "integer", "description": "Max documents (default 50, max 100)", "default": 50, "maximum": 100},
                },
            },
        ),
        Tool(
            name="get_document",
            description="Get document content by ID.",
            inputSchema={
                "type": "object",
                "properties": {
                    "doc_id": {"type": "string", "description": "Document ID (UUID)"},
                    "namespace": {"type": "string", "description": "Namespace (default 'default')"},
                },
                "required": ["doc_id"],
            },
        ),
        Tool(
            name="delete_document",
            description="Delete a document by ID.",
            inputSchema={
                "type": "object",
                "properties": {
                    "doc_id": {"type": "string", "description": "Document ID to delete"},
                    "namespace": {"type": "string", "description": "Namespace (default 'default')"},
                },
                "required": ["doc_id"],
            },
        ),
        Tool(
            name="update_document",
            description="Update document metadata (namespace, filename, custom metadata)",
            inputSchema={
                "type": "object",
                "properties": {
                    "doc_id": {"type": "string", "description": "Document UUID to update"},
                    "namespace": {"type": "string", "description": "Current namespace (default 'default')"},
                    "new_namespace": {"type": "string", "description": "New namespace to migrate to (optional)"},
                    "new_filename": {"type": "string", "description": "New filename (optional)"},
                    "metadata": {"type": "object", "description": "Custom metadata dict to replace existing (optional)"},
                },
                "required": ["doc_id"],
            },
        ),
        Tool(
            name="create_namespace",
            description="Create a new namespace.",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Namespace ID (e.g., 'mba/finance')"},
                    "name": {"type": "string", "description": "Display name"},
                    "description": {"type": "string", "description": "What belongs in this namespace"},
                    "parent_id": {"type": "string", "description": "Optional parent namespace ID for hierarchy"},
                },
                "required": ["id", "name"],
            },
        ),
        Tool(
            name="get_namespace",
            description="Get namespace details.",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Namespace ID"},
                },
                "required": ["id"],
            },
        ),
        Tool(
            name="update_namespace",
            description="Update namespace properties.",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Namespace ID"},
                    "name": {"type": "string", "description": "New name"},
                    "description": {"type": "string", "description": "New description"},
                },
                "required": ["id"],
            },
        ),
        Tool(
            name="delete_namespace",
            description="Delete a namespace.",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Namespace ID"},
                    "cascade": {"type": "boolean", "description": "Delete children too", "default": False},
                },
                "required": ["id"],
            },
        ),
    ]

    # Add enterprise tools if available
    try:
        from stache_tools.mcp.enterprise import get_enterprise_tool_definitions
        tools.extend(get_enterprise_tool_definitions())
        logger.debug("Enterprise tools loaded")
    except ImportError:
        logger.debug("Enterprise tools not available")

    return tools


class ToolHandler:
    """Handles MCP tool execution.

    Note: Currently uses sync API client with asyncio.to_thread for compatibility.
    Future enhancement: Add native async HTTP client for better performance.
    """

    def __init__(self, config: StacheConfig | None = None):
        self.api = StacheAPI(config)

    def close(self) -> None:
        """Close API client and cleanup resources."""
        self.api.close()

    async def handle(self, name: str, arguments: dict[str, Any]) -> list[TextContent]:
        """Handle tool call using asyncio.to_thread."""
        logger.info(f"Tool called: {name}")

        try:
            handler = getattr(self, f"_handle_{name}", None)
            if not handler:
                # Try enterprise tools if available
                enterprise_result = await self._handle_enterprise_tool(name, arguments)
                if enterprise_result is not None:
                    return enterprise_result

                return self._error(f"Unknown tool: {name}")
            return await handler(arguments)
        except Exception as e:
            logger.exception(f"Tool {name} failed")
            return self._error(str(e))

    async def _handle_enterprise_tool(self, name: str, arguments: dict[str, Any]) -> list[TextContent] | None:
        """Route to enterprise tool handlers if available.

        Returns:
            list[TextContent] if enterprise tool found and executed, None otherwise
        """
        try:
            from stache_tools.mcp.enterprise import handle_enterprise_tool
        except ImportError:
            # Enterprise tools not available
            logger.debug(f"Enterprise tools not available for: {name}")
            return None

        return await handle_enterprise_tool(name, arguments)

    def _error(self, message: str) -> list[TextContent]:
        return [TextContent(type="text", text=f"Error: {message}")]

    async def _handle_search(self, args: dict) -> list[TextContent]:
        query = args.get("query", "").strip()
        if not query:
            return self._error("query is required")

        # Validate namespace if provided
        namespace = args.get("namespace")
        if namespace:
            namespace = namespace.strip()
            error = validate_id(namespace, "Namespace")
            if error:
                return self._error(error)

        result = await asyncio.to_thread(
            self.api.search,
            query=query,
            namespace=namespace,
            top_k=args.get("top_k", 20),
            synthesize=False,
            rerank=args.get("rerank", True),
            filter=args.get("filter"),
        )
        return [TextContent(type="text", text=format_search_results(result))]

    async def _handle_ingest_text(self, args: dict) -> list[TextContent]:
        text = args.get("text", "").strip()
        if not text:
            return self._error("text is required")

        # Validate namespace if provided
        namespace = args.get("namespace")
        if namespace:
            namespace = namespace.strip()
            error = validate_id(namespace, "Namespace")
            if error:
                return self._error(error)

        result = await asyncio.to_thread(
            self.api.ingest_text,
            text=text,
            namespace=namespace,
            metadata=args.get("metadata"),
            chunking_strategy=args.get("chunking_strategy", "recursive"),
            prepend_metadata=args.get("prepend_metadata"),
        )
        return [TextContent(type="text", text=format_ingest_result(result))]

    async def _handle_list_namespaces(self, args: dict) -> list[TextContent]:
        result = await asyncio.to_thread(self.api.list_namespaces)
        return [TextContent(type="text", text=format_namespace_list(result))]

    async def _handle_list_documents(self, args: dict) -> list[TextContent]:
        # Validate namespace if provided
        namespace = args.get("namespace")
        if namespace:
            namespace = namespace.strip()
            error = validate_id(namespace, "Namespace")
            if error:
                return self._error(error)

        result = await asyncio.to_thread(self.api.list_documents, namespace=namespace, limit=args.get("limit", 50))
        return [TextContent(type="text", text=format_document_list(result))]

    async def _handle_get_document(self, args: dict) -> list[TextContent]:
        doc_id = args.get("doc_id", "").strip()
        if not doc_id:
            return self._error("doc_id is required")

        # Validate document ID
        error = validate_id(doc_id, "Document ID")
        if error:
            return self._error(error)

        # Validate namespace
        namespace = args.get("namespace", "default").strip()
        error = validate_id(namespace, "Namespace")
        if error:
            return self._error(error)

        result = await asyncio.to_thread(self.api.get_document, doc_id=doc_id, namespace=namespace)
        return [TextContent(type="text", text=format_document(result))]

    async def _handle_delete_document(self, args: dict) -> list[TextContent]:
        doc_id = args.get("doc_id", "").strip()
        if not doc_id:
            return self._error("doc_id is required")

        # Validate document ID
        error = validate_id(doc_id, "Document ID")
        if error:
            return self._error(error)

        # Validate namespace
        namespace = args.get("namespace", "default").strip()
        error = validate_id(namespace, "Namespace")
        if error:
            return self._error(error)

        result = await asyncio.to_thread(self.api.delete_document, doc_id=doc_id, namespace=namespace)
        if result.get("success"):
            return [TextContent(type="text", text=f"Deleted document {doc_id}")]
        return self._error(result.get("error", "Delete failed"))

    async def _handle_update_document(self, args: dict) -> list[TextContent]:
        doc_id = args.get("doc_id", "").strip()
        if not doc_id:
            return self._error("doc_id is required")

        # Validate document ID
        error = validate_id(doc_id, "Document ID")
        if error:
            return self._error(error)

        # Validate namespace
        namespace = args.get("namespace", "default").strip()
        error = validate_id(namespace, "Namespace")
        if error:
            return self._error(error)

        # Build updates dict
        updates = {}
        if args.get("new_namespace"):
            new_ns = args["new_namespace"].strip()
            error = validate_id(new_ns, "New namespace")
            if error:
                return self._error(error)
            updates["namespace"] = new_ns

        if args.get("new_filename"):
            updates["filename"] = args["new_filename"].strip()

        if args.get("metadata"):
            updates["metadata"] = args["metadata"]

        if not updates:
            return self._error("At least one update field required (new_namespace, new_filename, metadata)")

        result = await asyncio.to_thread(self.api.update_document, doc_id=doc_id, namespace=namespace, updates=updates)
        chunks = result.get("updated_chunks", 0)
        new_ns = result.get("namespace", namespace)
        return [TextContent(type="text", text=f"Updated document {doc_id} ({chunks} chunks) in namespace {new_ns}")]

    async def _handle_create_namespace(self, args: dict) -> list[TextContent]:
        ns_id = args.get("id", "").strip()
        name = args.get("name", "").strip()
        if not ns_id or not name:
            return self._error("id and name are required")

        # Validate namespace ID
        error = validate_id(ns_id, "Namespace ID")
        if error:
            return self._error(error)

        # Validate parent_id if provided
        parent_id = args.get("parent_id")
        if parent_id:
            parent_id = parent_id.strip()
            error = validate_id(parent_id, "Parent namespace ID")
            if error:
                return self._error(error)

        await asyncio.to_thread(
            self.api.create_namespace,
            id=ns_id,
            name=name,
            description=args.get("description", ""),
            parent_id=parent_id
        )
        return [TextContent(type="text", text=f"Created namespace: {ns_id}")]

    async def _handle_get_namespace(self, args: dict) -> list[TextContent]:
        ns_id = args.get("id", "").strip()
        if not ns_id:
            return self._error("id is required")

        # Validate namespace ID
        error = validate_id(ns_id, "Namespace ID")
        if error:
            return self._error(error)

        result = await asyncio.to_thread(self.api.get_namespace, id=ns_id)
        ns = result.get("namespace", result)
        return [TextContent(type="text", text=f"**{ns.get('name')}** (`{ns.get('id')}`)\n{ns.get('description', '')}")]

    async def _handle_update_namespace(self, args: dict) -> list[TextContent]:
        ns_id = args.get("id", "").strip()
        if not ns_id:
            return self._error("id is required")

        # Validate namespace ID
        error = validate_id(ns_id, "Namespace ID")
        if error:
            return self._error(error)

        await asyncio.to_thread(self.api.update_namespace, id=ns_id, name=args.get("name"), description=args.get("description"))
        return [TextContent(type="text", text=f"Updated namespace: {ns_id}")]

    async def _handle_delete_namespace(self, args: dict) -> list[TextContent]:
        ns_id = args.get("id", "").strip()
        if not ns_id:
            return self._error("id is required")

        # Validate namespace ID
        error = validate_id(ns_id, "Namespace ID")
        if error:
            return self._error(error)

        result = await asyncio.to_thread(self.api.delete_namespace, id=ns_id, cascade=args.get("cascade", False))
        if result.get("success"):
            return [TextContent(type="text", text=f"Deleted namespace: {ns_id}")]
        return self._error(result.get("error", "Delete failed"))
