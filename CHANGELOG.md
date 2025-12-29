# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2025-01-01

### Added
- Python API client (`StacheAPI`) with OAuth2 client credentials support
- CLI (`stache`) with commands: search, ingest, namespace, doc, health
- MCP server (`stache-mcp`) for Claude Desktop integration
- Document loaders for PDF, Markdown, and plain text
- Plugin system for custom loaders via entry points
- Automatic retry with exponential backoff for transient failures
- Request ID tracking for debugging
