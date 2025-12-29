"""MCP server for Stache RAG system."""

import asyncio
import logging
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent

from stache_tools.client.config import StacheConfig
from stache_tools.mcp.tools import ToolHandler, get_tool_definitions

logger = logging.getLogger("stache-tools")


def create_server() -> tuple[Server, ToolHandler]:
    """Create and configure MCP server.

    Returns:
        Tuple of (server, handler) for proper cleanup.
    """
    server = Server("stache")
    config = StacheConfig()
    handler = ToolHandler(config)

    @server.list_tools()
    async def list_tools():
        """List available tools."""
        return get_tool_definitions()

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        """Execute a tool."""
        try:
            # Run async handler directly
            return await handler.handle(name, arguments)
        except Exception as e:
            logger.exception(f"Tool {name} failed: {e}")
            return [TextContent(type="text", text=f"Error: {e!s}")]

    return server, handler


async def run_server() -> None:
    """Run the MCP server via stdio transport."""
    server, handler = create_server()
    logger.info("Starting Stache MCP server on stdio transport")

    try:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options(),
            )
    finally:
        # Clean up the handler's API client
        logger.info("Shutting down Stache MCP server")
        handler.close()


def main() -> None:
    """Entry point for stache-mcp command."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    try:
        asyncio.run(run_server())
    except KeyboardInterrupt:
        logger.info("Stache MCP server shutdown")
    except Exception as e:
        logger.exception(f"Stache MCP server error: {e}")
        raise


if __name__ == "__main__":
    main()
