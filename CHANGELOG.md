# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.2] - 2026-01-15

### Added

- **OCR support** - Integrated OCR loaders (merged from stache-tools-ocr)
  - Install with `pip install stache-tools[ocr]`
  - Supports scanned PDFs (via stache-ai-ocr)
  - Supports image OCR (JPG, PNG, TIFF, etc. via pytesseract)
  - Falls back gracefully if OCR dependencies not installed
  - Auto-detects if stache-ai-ocr is installed and loads loaders

### Changed

- Document loaders (DOCX, PPTX, EPUB) now built-in (merged from stache-tools-documents)
- Simplified installation - no need for separate plugin packages

### Deprecated

- **stache-tools-ocr** package - functionality merged into stache-tools[ocr]
- **stache-tools-documents** package - functionality merged into stache-tools core

## [0.1.1] - 2026-01-11

### Added

- **Parallel Ingestion**: Multi-threaded file processing with `-P/--parallel` flag (1-32 workers)
  - Progress bars with real-time status updates
  - Per-worker error isolation with `--skip-errors` option
  - Thread-safe console output

- **Dry-Run Mode**: Preview ingestion operations without committing changes (`--dry-run`)

- **Document Format Support**: Built-in loaders for common document formats
  - DOCX (Microsoft Word) via `stache-ai-documents`
  - PPTX (PowerPoint) via `stache-ai-documents`
  - EPUB (e-books) via `stache-ai-documents`
  - Adapter pattern wraps `stache-ai-documents` loaders for CLI use

- **Enhanced CLI Options**:
  - `--pattern` flag for glob-based file filtering
  - `-y/--yes` flag to skip confirmation prompts
  - `--skip-errors` for fault-tolerant bulk imports

- **Lambda Transport Improvements**:
  - Updated to HTTP API v2 format (compatible with Mangum)
  - Better error handling and response parsing

### Changed

- `StacheAPI` client converted to context manager pattern for proper resource cleanup
- All CLI commands now use `with StacheAPI()` for automatic client lifecycle management
- Document loaders registry now supports external plugin discovery
- MCP tools updated to use context manager for API clients

### Fixed

- Thread safety in parallel ingestion with proper client isolation
- Lambda transport event format compatibility with HTTP API v2
- Resource cleanup in document loaders with proper temp file handling

## [0.1.0] - 2025-01-01

### Added
- Python API client (`StacheAPI`) with OAuth2 client credentials support
- CLI (`stache`) with commands: search, ingest, namespace, doc, health
- MCP server (`stache-mcp`) for Claude Desktop integration
- Document loaders for PDF, Markdown, and plain text
- Plugin system for custom loaders via entry points
- Automatic retry with exponential backoff for transient failures
- Request ID tracking for debugging
