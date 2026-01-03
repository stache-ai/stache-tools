# stache-tools

CLI and MCP server for the [Stache](https://github.com/stache-ai/stache-ai) knowledge base.

## Installation

```bash
pip install stache-tools
```

This provides two commands:
- `stache` - CLI for interacting with your knowledge base
- `stache-mcp` - MCP server for Claude Desktop/Claude Code integration

## Quick Start

### 1. Start Stache Server

See the [Stache repository](https://github.com/stache-ai/stache-ai) for full setup instructions, or quick start:

```bash
git clone https://github.com/stache-ai/stache-ai.git
cd stache
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d
```

### 2. Configure MCP Server

Add to your Claude config file:

**Claude Code** (`~/.claude.json` or `%APPDATA%\.claude\config.json` on Windows):
```json
{
  "mcpServers": {
    "stache-local": {
      "command": "stache-mcp",
      "env": {
        "STACHE_API_URL": "http://localhost:8000"
      }
    }
  }
}
```

**Claude Desktop** (`~/.config/claude/claude_desktop_config.json` or `%APPDATA%\Claude\claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "stache-local": {
      "command": "python",
      "args": ["-m", "stache_tools.mcp"],
      "env": {
        "STACHE_API_URL": "http://localhost:8000"
      }
    }
  }
}
```

### 3. Restart Claude

Restart Claude Code/Desktop to load the MCP server.

## MCP Tools

| Tool | Description |
|------|-------------|
| `search` | Semantic search in your knowledge base |
| `ingest_text` | Add text content |
| `list_namespaces` | List all namespaces |
| `list_documents` | List documents |
| `get_document` | Get document by ID |
| `delete_document` | Delete document |
| `create_namespace` | Create namespace |
| `get_namespace` | Get namespace details |
| `update_namespace` | Update namespace |
| `delete_namespace` | Delete namespace |

## CLI Usage

```bash
# Set API URL
export STACHE_API_URL=http://localhost:8000

# Health check
stache health

# Search
stache search "your query" -n namespace -k 10

# Ingest
stache ingest ./document.pdf -n research
stache ingest ./docs/ -n documentation -r  # Recursive
stache ingest -t "Some text content" -n notes

# Namespaces
stache namespace list
stache namespace create mba/finance --name "Finance Notes"

# Documents
stache doc list -n research
stache doc get DOC_ID
stache doc delete DOC_ID
```

## Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `STACHE_API_URL` | API base URL | `http://localhost:8000` |
| `STACHE_TRANSPORT` | Transport: `auto`, `http`, `lambda` | `auto` |
| `STACHE_TIMEOUT` | Request timeout (seconds) | `60` |

### AWS Lambda Transport

For direct Lambda invocation (bypasses API Gateway):

```bash
pip install stache-tools[lambda]
```

```json
{
  "mcpServers": {
    "stache": {
      "command": "stache-mcp",
      "env": {
        "STACHE_LAMBDA_FUNCTION": "stache-api",
        "AWS_REGION": "us-east-1"
      }
    }
  }
}
```

## Python API

```python
from stache_tools import StacheAPI

with StacheAPI() as api:
    # Ingest
    api.ingest_text("Your content here", namespace="examples")

    # Search
    results = api.search("query", namespace="examples")
    for source in results.get("sources", []):
        print(f"{source['score']:.3f}: {source['content'][:100]}")
```

## Documentation

- [Full Setup Guide](https://github.com/stache-ai/stache-tools/blob/main/docs/SETUP.md) - Detailed installation and configuration
- [Troubleshooting](https://github.com/stache-ai/stache-tools/blob/main/docs/TROUBLESHOOTING.md) - Common issues and solutions
- [Stache Server](https://github.com/stache-ai/stache-ai) - Main Stache repository

## License

MIT
