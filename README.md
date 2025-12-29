# stache-tools

Client library, CLI, and MCP server for the Stache RAG system.

## Features

- **Python API** - Programmatic access to all Stache operations
- **CLI** - Command-line interface for search, ingestion, and management
- **MCP Server** - Integration with Claude Desktop and MCP-compatible clients
- **Two Transport Modes** - HTTP (API Gateway) or Lambda (direct invocation)
- **Document Loaders** - Extensible system for text, markdown, PDF, and custom formats

## Installation

```bash
pip install stache-tools
```

For Lambda direct invocation support:

```bash
pip install stache-tools[lambda]
```

For development:

```bash
pip install stache-tools[dev]
```

**Requirements**: Python 3.10+

---

## Transport Modes

stache-tools supports two transport modes for communicating with the Stache backend:

| Transport | Authentication | Best For | Latency |
|-----------|---------------|----------|---------|
| **HTTP** | OAuth (Cognito) | Production with API Gateway | Standard |
| **Lambda** | AWS credentials | Direct invocation, local dev | Lower |

### HTTP Transport (Default)

Uses API Gateway with OAuth authentication. This is the standard production setup.

```bash
# Required
STACHE_API_URL=https://api.stache.example.com

# OAuth credentials
STACHE_COGNITO_CLIENT_ID=your-client-id
STACHE_COGNITO_CLIENT_SECRET=your-client-secret
STACHE_COGNITO_TOKEN_URL=https://auth.example.com/oauth2/token
```

### Lambda Transport

Invokes the Lambda function directly using AWS credentials. Benefits:

- **No OAuth setup** - Uses your existing AWS credential chain
- **Lower latency** - Bypasses API Gateway
- **Simpler local development** - Just configure AWS profile
- **Works everywhere** - EC2, ECS, Lambda, local machine with AWS CLI

```bash
# Enable Lambda transport
STACHE_LAMBDA_FUNCTION=stache-api  # or full ARN

# Optional AWS configuration
AWS_PROFILE=my-profile             # Uses default chain if not set
AWS_REGION=us-east-1               # Defaults to us-east-1
```

**IAM Permissions Required**:
```json
{
  "Effect": "Allow",
  "Action": "lambda:InvokeFunction",
  "Resource": "arn:aws:lambda:REGION:ACCOUNT:function:stache-api"
}
```

### Transport Selection

The transport is selected based on the `STACHE_TRANSPORT` environment variable:

| Value | Behavior |
|-------|----------|
| `auto` (default) | Uses Lambda if `STACHE_LAMBDA_FUNCTION` is set, otherwise HTTP |
| `http` | Forces HTTP transport |
| `lambda` | Forces Lambda transport |

---

## Quick Start

### Basic Usage

```python
from stache_tools import StacheClient

# Transport is auto-detected from environment variables
with StacheClient() as client:
    # Ingest content
    result = client.ingest_text(
        text="The quick brown fox jumps over the lazy dog.",
        namespace="examples",
        metadata={"source": "demo"}
    )
    print(f"Document ID: {result['document_id']}")

    # Search
    results = client.search("quick fox", namespace="examples")
    for source in results.get("sources", []):
        print(f"Score: {source['score']:.3f} - {source['content'][:100]}")
```

### HTTP Transport Example

```python
from stache_tools import StacheClient, StacheConfig

config = StacheConfig(
    transport="http",
    api_url="https://api.stache.example.com",
    cognito_client_id="abc123",
    cognito_client_secret="secret",
    cognito_token_url="https://auth.example.com/oauth2/token"
)

with StacheClient(config) as client:
    results = client.search("machine learning")
```

### Lambda Transport Example

```python
from stache_tools import StacheClient, StacheConfig

config = StacheConfig(
    transport="lambda",
    lambda_function_name="stache-api",
    aws_region="us-east-1"
)

with StacheClient(config) as client:
    results = client.search("machine learning")
```

---

## Configuration Reference

All settings use the `STACHE_` prefix and can be set via environment variables or a `.env` file.

### Core Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `STACHE_TRANSPORT` | Transport mode: `auto`, `http`, or `lambda` | `auto` |
| `STACHE_TIMEOUT` | Request timeout in seconds (1-300) | `60.0` |
| `STACHE_LOG_LEVEL` | Logging level | `INFO` |

### HTTP Transport Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `STACHE_API_URL` | API Gateway base URL | `http://localhost:8000` |
| `STACHE_COGNITO_CLIENT_ID` | OAuth client ID | (none) |
| `STACHE_COGNITO_CLIENT_SECRET` | OAuth client secret | (none) |
| `STACHE_COGNITO_TOKEN_URL` | OAuth token endpoint | (none) |
| `STACHE_COGNITO_SCOPE` | OAuth scope | (none) |

OAuth is enabled automatically when `STACHE_COGNITO_CLIENT_ID`, `STACHE_COGNITO_CLIENT_SECRET`, and `STACHE_COGNITO_TOKEN_URL` are all set.

### Lambda Transport Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `STACHE_LAMBDA_FUNCTION` | Lambda function name or ARN | (none) |
| `AWS_PROFILE` | AWS profile name | (default chain) |
| `AWS_REGION` | AWS region | `us-east-1` |
| `STACHE_LAMBDA_TIMEOUT` | Lambda read timeout in seconds (1-900) | `60.0` |

### Example .env Files

**HTTP Transport:**
```bash
STACHE_TRANSPORT=http
STACHE_API_URL=https://xxx.execute-api.us-east-1.amazonaws.com/Prod/
STACHE_COGNITO_CLIENT_ID=abc123...
STACHE_COGNITO_CLIENT_SECRET=xyz789...
STACHE_COGNITO_TOKEN_URL=https://stache-serverless-123456789.auth.us-east-1.amazoncognito.com/oauth2/token
STACHE_COGNITO_SCOPE=stache-serverless-api/read stache-serverless-api/write
```

**Lambda Transport:**
```bash
STACHE_TRANSPORT=lambda
STACHE_LAMBDA_FUNCTION=stache-api
AWS_PROFILE=my-profile
AWS_REGION=us-east-1
```

**Auto-detect (Lambda preferred):**
```bash
# When STACHE_LAMBDA_FUNCTION is set and transport=auto, Lambda is used
STACHE_LAMBDA_FUNCTION=stache-api
```

---

## Python API

The `StacheClient` class (alias for `StacheAPI`) provides high-level access to all Stache operations.

### Initialization

```python
from stache_tools import StacheClient, StacheConfig

# Use defaults (reads from environment)
client = StacheClient()

# With explicit config
config = StacheConfig(api_url="http://localhost:8000", timeout=30.0)
client = StacheClient(config)

# As context manager (recommended - auto-closes connections)
with StacheClient() as client:
    result = client.search("query")
```

### API Methods

| Method | Signature | Description |
|--------|-----------|-------------|
| `search` | `(query, namespace=None, top_k=20, rerank=True, filter=None) -> dict` | Semantic search with optional reranking and metadata filter |
| `ingest_text` | `(text, namespace="default", metadata=None) -> dict` | Ingest text content (max 100KB) |
| `list_namespaces` | `() -> dict` | List all namespaces with children |
| `create_namespace` | `(id, name, description="", parent_id=None, metadata=None) -> dict` | Create a new namespace |
| `get_namespace` | `(id) -> dict` | Get namespace by ID |
| `update_namespace` | `(id, name=None, description=None, metadata=None) -> dict` | Update namespace properties |
| `delete_namespace` | `(id, cascade=False) -> dict` | Delete namespace (cascade deletes children) |
| `list_documents` | `(namespace=None, limit=50, next_key=None) -> dict` | List documents with pagination |
| `get_document` | `(doc_id, namespace="default") -> dict` | Get document by ID |
| `delete_document` | `(doc_id, namespace="default") -> dict` | Delete document by ID |
| `health` | `(include_auth=False) -> dict` | Check API health and optionally validate auth |
| `close` | `() -> None` | Close transport connections |

### Request Tracking

Every API response includes a `request_id` for debugging:

```python
with StacheClient() as client:
    try:
        client.search("query")
    except StacheError as e:
        print(f"Request ID: {client.last_request_id}")
        # Or from the exception
        print(f"Request ID: {e.request_id}")
```

---

## CLI Reference

The CLI is installed as `stache` and works with both transport modes.

### CLI with Lambda Transport

```bash
# Set environment variables
export STACHE_LAMBDA_FUNCTION=stache-api
export AWS_PROFILE=my-profile

# All commands now use Lambda transport
stache search "machine learning"
stache namespace list
```

### search

Search the knowledge base.

```bash
stache search "your query" [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `-n, --namespace` | Filter by namespace |
| `-k, --top-k` | Number of results (default: 10) |
| `--synthesize` | Enable LLM synthesis (off by default) |
| `--no-rerank` | Skip reranking (faster, less accurate) |
| `--json` | Output as JSON |

Examples:

```bash
stache search "machine learning basics"
stache search "python async" -n docs -k 5
stache search "error handling" --json
stache search "explain RAG" --synthesize  # Use LLM to synthesize answer
```

### ingest

Ingest files into Stache.

```bash
stache ingest PATH [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `-n, --namespace` | Target namespace |
| `-r, --recursive` | Process directories recursively |

Examples:

```bash
stache ingest ./document.pdf -n research
stache ingest ./docs/ -n documentation -r
```

### namespace

Manage namespaces.

```bash
stache namespace list
stache namespace create ID --name NAME [--description DESC]
stache namespace delete ID [--cascade]
```

| Subcommand | Description |
|------------|-------------|
| `list` | List all namespaces |
| `create` | Create a new namespace |
| `delete` | Delete a namespace (with confirmation) |

Examples:

```bash
stache namespace list
stache namespace create mba/finance --name "Finance Notes" --description "MBA finance coursework"
stache namespace delete mba/finance --cascade
```

### doc

Manage documents.

```bash
stache doc list [OPTIONS]
stache doc get DOC_ID [OPTIONS]
stache doc delete DOC_ID [OPTIONS]
```

| Subcommand | Description |
|------------|-------------|
| `list` | List documents |
| `get` | Get document content |
| `delete` | Delete a document (with confirmation) |

| Option | Description |
|--------|-------------|
| `-n, --namespace` | Filter/specify namespace |
| `-l, --limit` | Max documents for list (default: 50) |

Examples:

```bash
stache doc list -n research
stache doc get abc123-def456 -n research
stache doc delete abc123-def456 -n research
```

### health

Check API connectivity and health.

```bash
stache health [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--check-auth` | Validate authentication |

Example:

```bash
stache health
stache health --check-auth
```

---

## MCP Server

The MCP server enables Stache integration with Claude Desktop and other MCP-compatible clients.

### Configuration

Add to `~/.config/claude/claude_desktop_config.json` (Linux/macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

**Using HTTP Transport:**
```json
{
  "mcpServers": {
    "stache": {
      "command": "stache-mcp",
      "env": {
        "STACHE_API_URL": "https://xxx.execute-api.us-east-1.amazonaws.com/Prod/",
        "STACHE_COGNITO_CLIENT_ID": "abc123...",
        "STACHE_COGNITO_CLIENT_SECRET": "xyz789...",
        "STACHE_COGNITO_TOKEN_URL": "https://stache-serverless-xxx.auth.us-east-1.amazoncognito.com/oauth2/token",
        "STACHE_COGNITO_SCOPE": "stache-serverless-api/read stache-serverless-api/write"
      }
    }
  }
}
```

**Using Lambda Transport (Recommended):**
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

Note: Lambda transport uses your default AWS credential chain. Add `AWS_PROFILE` if needed.

### Available Tools

| Tool | Description | Required Parameters |
|------|-------------|---------------------|
| `search` | Semantic search in knowledge base | `query` |
| `ingest_text` | Add text content to knowledge base | `text` |
| `list_namespaces` | List all namespaces | (none) |
| `list_documents` | List documents (optionally filtered) | (none) |
| `get_document` | Get document by ID | `doc_id` |
| `delete_document` | Delete a document | `doc_id` |
| `create_namespace` | Create a new namespace | `id`, `name` |
| `get_namespace` | Get namespace details | `id` |
| `update_namespace` | Update namespace properties | `id` |
| `delete_namespace` | Delete a namespace | `id` |

### Tool Parameters

**search**
- `query` (required): Search query (max 10,000 chars)
- `namespace` (optional): Namespace filter
- `top_k` (optional): Results count (default: 20, max: 50)

**ingest_text**
- `text` (required): Text content (max 100KB)
- `namespace` (optional): Target namespace (default: "default")
- `metadata` (optional): Additional metadata object

**list_documents**
- `namespace` (optional): Filter by namespace
- `limit` (optional): Max results (default: 50, max: 100)

**get_document / delete_document**
- `doc_id` (required): Document ID
- `namespace` (optional): Namespace (default: "default")

**create_namespace**
- `id` (required): Namespace ID (e.g., "mba/finance")
- `name` (required): Display name
- `description` (optional): Description

**update_namespace**
- `id` (required): Namespace ID
- `name` (optional): New name
- `description` (optional): New description

**delete_namespace**
- `id` (required): Namespace ID
- `cascade` (optional): Delete children (default: false)

---

## Document Loaders

The loader system extracts text from various file formats.

### Built-in Loaders

| Loader | Extensions | Description |
|--------|------------|-------------|
| `TextLoader` | `.txt` | Plain text files (UTF-8) |
| `MarkdownLoader` | `.md`, `.markdown` | Markdown files (extracts title from first `#` heading) |
| `BasicPDFLoader` | `.pdf` | PDF files via pypdf (no OCR) |

### Usage

```python
from stache_tools.loaders import load_document, LoaderRegistry

# Simple usage
doc = load_document("path/to/file.pdf")
print(doc.text)
print(doc.metadata)  # {"filename": "file.pdf", "type": "pdf", "page_count": 5, ...}

# Check supported extensions
registry = LoaderRegistry()
print(registry.supported_extensions())  # ['.md', '.markdown', '.pdf', '.txt']
```

### Plugin System

External packages can register custom loaders via entry points.

In your plugin's `pyproject.toml`:

```toml
[project.entry-points."stache_tools.loaders"]
my_loader = "my_plugin.loaders:MyCustomLoader"
```

Your loader must extend `DocumentLoader`:

```python
from stache_tools import DocumentLoader, LoadedDocument
from typing import BinaryIO

class MyCustomLoader(DocumentLoader):
    @property
    def extensions(self) -> list[str]:
        return [".docx"]

    @property
    def priority(self) -> int:
        return 10  # Higher than built-in (0) to override

    def load(self, file: BinaryIO, filename: str) -> LoadedDocument:
        # Extract text from file
        text = extract_text_somehow(file)
        return LoadedDocument(
            text=text,
            metadata={"filename": filename, "type": "docx"}
        )
```

### Environment Variable Overrides

Force a specific loader for an extension using `STACHE_LOADER_{EXT}`:

```bash
# Use a plugin loader named "BetterPDFLoader" for .pdf files
export STACHE_LOADER_PDF=BetterPDFLoader
```

The value must match the loader class name (case-insensitive).

---

## Error Handling

All errors inherit from `StacheError` and include the `request_id` when available.

### Exception Hierarchy

```
StacheError                    # Base exception
    StacheConnectionError      # Cannot reach API server / Lambda function
    StacheAuthError            # Authentication failed (401/403 or AWS access denied)
    StacheNotFoundError        # Resource not found (404)
    StacheAPIError             # Server error (5xx) or other API error
        .status_code           # HTTP status code
```

### Examples

```python
from stache_tools import (
    StacheClient,
    StacheError,
    StacheConnectionError,
    StacheAuthError,
    StacheNotFoundError,
    StacheAPIError,
)

with StacheClient() as client:
    try:
        result = client.get_document("nonexistent-id")
    except StacheNotFoundError as e:
        print(f"Document not found (request_id: {e.request_id})")
    except StacheAuthError as e:
        print(f"Authentication failed: {e}")
    except StacheConnectionError as e:
        print(f"Cannot reach API: {e}")
    except StacheAPIError as e:
        print(f"API error {e.status_code}: {e}")
    except StacheError as e:
        print(f"General error: {e}")
```

### Transport-Specific Errors

**Lambda Transport:**
- `StacheConnectionError` - Lambda function not found
- `StacheAuthError` - IAM permission denied (`lambda:InvokeFunction` missing)
- `StacheAPIError` with 503 - Throttling or service unavailable

**HTTP Transport:**
- `StacheConnectionError` - Cannot reach API Gateway
- `StacheAuthError` - OAuth token expired or invalid
- `StacheAPIError` - HTTP errors from API

### Exception Attributes

| Exception | Attributes |
|-----------|------------|
| `StacheError` | `message`, `request_id` |
| `StacheAPIError` | `message`, `request_id`, `status_code` |

---

## Development

### Setup

```bash
git clone https://github.com/your-org/stache-tools.git
cd stache-tools
pip install -e ".[dev]"
```

### Running Tests

```bash
# All tests
pytest

# With coverage
pytest --cov=stache_tools --cov-report=term-missing

# Specific test file
pytest tests/test_client.py -v
```

### Code Quality

```bash
# Linting and formatting
ruff check src/
ruff format src/
```

### Test Configuration

Tests use `respx` for HTTP mocking, `moto` for AWS mocking, and `pytest-asyncio` for async tests. See `pyproject.toml` for full pytest configuration.

---

## License

MIT
