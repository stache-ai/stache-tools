# Stache Tools Setup Guide

Complete setup instructions for stache-tools with different deployment scenarios.

## Local Development with Docker

### Prerequisites

- Docker and Docker Compose
- Python 3.10+

### Step 1: Start Stache Server

```bash
git clone https://github.com/stache-ai/stache-ai.git
cd stache
```

**Choose your setup:**

#### Option A: Linux/Windows (Ollama in Docker)

```bash
# Start all services (Qdrant, MongoDB, Ollama, Stache)
# The embedding model is pulled automatically on first start
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d
```

The default embedding model is `nomic-embed-text` (768 dimensions). To use a different model, create a `.env` file before starting:

```bash
# Optional: Use a different embedding model
echo "OLLAMA_EMBEDDING_MODEL=mxbai-embed-large" > .env
echo "EMBEDDING_DIMENSION=1024" >> .env
```

#### Option B: Mac (Ollama on host for GPU acceleration)

```bash
# Install and start Ollama natively (uses Metal GPU)
brew install ollama
ollama serve &
ollama pull nomic-embed-text  # or mxbai-embed-large for best quality

# Start Stache services (connects to host Ollama)
docker compose -f docker-compose.yml -f docker-compose.ollama-host.yml up -d
```

#### Option C: OpenAI API

```bash
# Set your API key
echo "OPENAI_API_KEY=sk-..." > .env

# Start services
docker compose -f docker-compose.yml -f docker-compose.openai.yml up -d
```

**Verify it's running:**
```bash
curl http://localhost:8000health
```

### Embedding Model Options (Ollama)

| Model | Size | Dimensions | Best For |
|-------|------|------------|----------|
| `all-minilm` | 45MB | 384 | Quick testing, low memory |
| `nomic-embed-text` | 275MB | 768 | General use, good balance (default) |
| `mxbai-embed-large` | 670MB | 1024 | Best quality |

**Important:** The embedding dimension must match between your `.env` and the Qdrant collection. If you change models after data has been ingested, you'll need to delete the Qdrant collection first:

```bash
curl -X DELETE http://localhost:6333/collections/stache
docker restart stache-app
```

### Step 2: Install stache-tools

```bash
pip install stache-tools
```

### Step 3: Configure MCP Server

#### Claude Code

Add to your Claude Code config file:
- **Linux/macOS**: `~/.claude.json`
- **Windows**: `%APPDATA%\.claude\config.json`

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

**Windows Note:** If `stache-mcp` isn't found, use Python directly:

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

If `python` isn't in your PATH, find your Python installation path with `where python` and use the full path (e.g., `C:\\Python310\\python.exe`).

#### Claude Desktop

Add to your Claude Desktop config file:
- **Linux/macOS**: `~/.config/claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

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

### Step 4: Restart Claude

Restart Claude Code or Claude Desktop to pick up the new MCP server.

### Step 5: Test

```bash
# CLI test
export STACHE_API_URL=http://localhost:8000
stache health
stache ingest -t "The quick brown fox jumps over the lazy dog" -n test
stache search "fox"
```

---

## AWS Deployment (Lambda Transport)

For connecting to a deployed Stache serverless stack with direct Lambda invocation.

### Prerequisites

- AWS credentials configured (`aws configure` or environment variables)
- IAM permissions for `lambda:InvokeFunction` on the stache-api function

### Setup

1. Install with Lambda support:
   ```bash
   pip install stache-tools[lambda]
   ```

2. Add MCP config:
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

3. Restart Claude

---

## AWS Deployment (HTTP/OAuth Transport)

For connecting via API Gateway with Cognito authentication.

### Prerequisites

- Cognito client credentials from CloudFormation outputs

### Setup

1. Install stache-tools:
   ```bash
   pip install stache-tools
   ```

2. Add MCP config:
   ```json
   {
     "mcpServers": {
       "stache": {
         "command": "stache-mcp",
         "env": {
           "STACHE_API_URL": "https://xxx.execute-api.us-east-1.amazonaws.com/Prod/",
           "STACHE_COGNITO_CLIENT_ID": "your-client-id",
           "STACHE_COGNITO_CLIENT_SECRET": "your-client-secret",
           "STACHE_COGNITO_TOKEN_URL": "https://xxx.auth.us-east-1.amazoncognito.com/oauth2/token",
           "STACHE_COGNITO_SCOPE": "stache-serverless-api/read stache-serverless-api/write"
         }
       }
     }
   }
   ```

3. Restart Claude

---

## Environment Variables Reference

All settings use the `STACHE_` prefix.

### Transport Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `STACHE_API_URL` | API base URL | `http://localhost:8000` |
| `STACHE_TRANSPORT` | Transport mode: `auto`, `http`, `lambda` | `auto` |
| `STACHE_TIMEOUT` | Request timeout in seconds | `60` |

### Local Development (No Auth)

For local development against a Docker/local server, just set the API URL:

```bash
STACHE_API_URL=http://localhost:8000
```

OAuth is **disabled** when Cognito variables are not set.

### Lambda Transport

```bash
STACHE_TRANSPORT=lambda
STACHE_LAMBDA_FUNCTION=stache-api
AWS_REGION=us-east-1
AWS_PROFILE=my-profile  # Optional
```

### HTTP Transport with OAuth

```bash
STACHE_API_URL=https://xxx.execute-api.us-east-1.amazonaws.com/Prod/
STACHE_COGNITO_CLIENT_ID=your-client-id
STACHE_COGNITO_CLIENT_SECRET=your-client-secret
STACHE_COGNITO_TOKEN_URL=https://xxx.auth.us-east-1.amazoncognito.com/oauth2/token
STACHE_COGNITO_SCOPE=stache-serverless-api/read stache-serverless-api/write
```

OAuth is **enabled** automatically when all four Cognito variables are set.
