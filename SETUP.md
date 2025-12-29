# Stache Tools Setup

## CLI Configuration

### Option 1: Source .env file (HTTP Transport)
```bash
cd /mnt/devbuntu/dev/stache-tools
source .env
stache search "test query"
```

### Option 2: Lambda Transport (Recommended)
```bash
export STACHE_LAMBDA_FUNCTION=stache-api
export AWS_REGION=us-east-1
stache search "test query"
```

## MCP Server Configuration (Claude Desktop)

### Option 1: HTTP Transport (OAuth)

Copy the HTTP config to Claude Desktop:
```bash
cp /mnt/devbuntu/dev/stache-tools/mcp-config-http.json ~/.config/claude/claude_desktop_config.json
```

Or manually add to `~/.config/claude/claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "stache": {
      "command": "/mnt/devbuntu/dev/stache-tools/venv/bin/python",
      "args": ["-m", "stache_tools.mcp.server"],
      "env": {
        "STACHE_API_URL": "https://xxx.execute-api.us-east-1.amazonaws.com/Prod/",
        "STACHE_COGNITO_CLIENT_ID": "<from deploy output>",
        "STACHE_COGNITO_CLIENT_SECRET": "<from deploy output>",
        "STACHE_COGNITO_TOKEN_URL": "https://<domain>.auth.us-east-1.amazoncognito.com/oauth2/token",
        "STACHE_COGNITO_SCOPE": "stache-serverless-api/read stache-serverless-api/write"
      }
    }
  }
}
```

### Option 2: Lambda Transport (Recommended)

Copy the Lambda config:
```bash
cp /mnt/devbuntu/dev/stache-tools/mcp-config-lambda.json ~/.config/claude/claude_desktop_config.json
```

Or manually add:
```json
{
  "mcpServers": {
    "stache": {
      "command": "/mnt/devbuntu/dev/stache-tools/venv/bin/python",
      "args": ["-m", "stache_tools.mcp.server"],
      "env": {
        "STACHE_LAMBDA_FUNCTION": "stache-api",
        "AWS_REGION": "us-east-1"
      }
    }
  }
}
```

## Testing

### Test CLI
```bash
source /tmp/test_cli.sh
```

### Test Ingest
```bash
source /tmp/test_ingest.sh
```

### Test MCP
Restart Claude Desktop and verify the "stache" MCP server appears in the tools list.

## Current Deployment Info

Get these values from `./scripts/deploy.sh` output or CloudFormation outputs:

- **API Gateway**: `https://xxx.execute-api.us-east-1.amazonaws.com/Prod/`
- **CloudFront**: `https://xxx.cloudfront.net`
- **User Pool**: Check CloudFormation outputs
- **Region**: us-east-1
- **Lambda Function**: stache-api

## Notes

- **HTTP API**: Uses `/Prod/` stage in URL
- **JWT Authorizer**: Supports both web (ID tokens) and M2M (access tokens)
- **Lambda Transport**: Recommended for MCP - uses IAM auth, no OAuth needed
- **Synthesis**: Disabled by default for CLI (use `--synthesize` to enable)
