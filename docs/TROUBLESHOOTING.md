# Troubleshooting

Common issues and solutions for stache-tools.

## OAuth Authentication Error

```
Error: invalid_client: Client authentication failed
```

**Cause**: OAuth credentials are being used but are invalid or the server doesn't expect them.

**Solutions**:
1. **For local development**: Remove all `STACHE_COGNITO_*` variables - OAuth is disabled when they're not set
2. **For deployed API**: Verify your client ID/secret from CloudFormation outputs

---

## Connection Refused

```
Error: Connection refused to localhost:8000
```

**Cause**: Stache server isn't running.

**Solution**: Start the server with `docker compose up -d` and verify with `curl http://localhost:8000/api/health`

---

## 404 Not Found on API Calls

**Cause**: Wrong API path. Local server uses `/api/` prefix.

**Solution**: Use `STACHE_API_URL=http://localhost:8000/api/` (note the `/api/` suffix)

---

## MCP Server Not Appearing

**Cause**: Claude hasn't reloaded the MCP configuration.

**Solution**: Restart Claude Code/Desktop completely after editing the config file. For VS Code, use "Developer: Reload Window" or restart VS Code entirely.

---

## Vector Dimension Mismatch

```
Error: Vector dimension error: expected dim: 1024, got 768
```

**Cause**: The Qdrant collection was created with a different embedding model dimension than what's currently configured.

**Solution**: Delete the collection and restart:
```bash
curl -X DELETE http://localhost:6333/collections/stache
docker restart stache-app
```

---

## DynamoDB Credentials Error (Local Setup)

```
Error: Unable to locate credentials
```

**Cause**: The document index provider is defaulting to DynamoDB instead of MongoDB.

**Solution**: Add to your `.env` file:
```bash
DOCUMENT_INDEX_PROVIDER=mongodb
```

Then restart:
```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d
```

---

## Ollama Connection Failed

**Cause**: Ollama container isn't healthy or model isn't pulled.

**Solutions**:
1. Check container health: `docker ps` - all containers should show "(healthy)"
2. Check Ollama logs: `docker logs stache-ollama`
3. Verify model is pulled: `docker exec stache-ollama ollama list`
4. Manually pull model: `docker exec stache-ollama ollama pull nomic-embed-text`

---

## Windows: stache-mcp command not found

**Cause**: Python Scripts directory is not in PATH.

**Solutions**:

1. Use Python module syntax instead:
   ```json
   {
     "command": "python",
     "args": ["-m", "stache_tools.mcp"]
   }
   ```

2. Or find Python path with `where python` and use full path:
   ```json
   {
     "command": "C:\\Python310\\python.exe",
     "args": ["-m", "stache_tools.mcp"]
   }
   ```

---

## MCP Server Starts But Tools Don't Work

**Cause**: The MCP server can connect but can't reach the Stache API.

**Solutions**:
1. Verify `STACHE_API_URL` includes the `/api/` path
2. Check if Stache is running: `curl http://localhost:8000/api/health`
3. Check MCP server logs in Claude's output panel

---

## Slow Embedding Performance

**Cause**: Using a large embedding model without GPU acceleration.

**Solutions**:
1. Use a smaller model like `nomic-embed-text` or `all-minilm`
2. On Mac, run Ollama on host (not in Docker) to use Metal GPU
3. Increase `OLLAMA_BATCH_SIZE` in `.env` if you have more RAM

---

## Container Keeps Restarting

**Cause**: Health check failing or resource limits exceeded.

**Solutions**:
1. Check logs: `docker logs stache-app` or `docker logs stache-ollama`
2. Increase memory limits in `docker-compose.local.yml`
3. Ensure Ollama has the required embedding model pulled
