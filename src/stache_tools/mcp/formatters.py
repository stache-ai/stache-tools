"""Output formatters for MCP responses."""

from typing import Any

MAX_CHUNK_LENGTH = 1000


def format_search_results(result: dict[str, Any]) -> str:
    """Format search results as Markdown."""
    lines = ["# Search Results\n"]

    chunks = result.get("sources", [])
    if not chunks:
        lines.append("No results found.")
        return "\n".join(lines)

    for i, chunk in enumerate(chunks, 1):
        score = chunk.get("score", 0)
        text = chunk.get("content", "")
        metadata = chunk.get("metadata", {})
        filename = metadata.get("filename", "Unknown")
        namespace = metadata.get("namespace", "default")

        if len(text) > MAX_CHUNK_LENGTH:
            text = text[:MAX_CHUNK_LENGTH] + "..."

        lines.append(f"### {i}. (score: {score:.3f})")
        lines.append(f"**Source:** {filename} | **Namespace:** {namespace}")
        lines.append(f"\n{text}\n")

    return "\n".join(lines)


def format_ingest_result(result: dict[str, Any]) -> str:
    """Format ingest result."""
    chunks = result.get("chunks_created", 0)
    doc_id = result.get("doc_id", "")
    return f"Ingested successfully: {chunks} chunks created (doc_id: {doc_id})"


def format_namespace_list(result: dict[str, Any]) -> str:
    """Format namespace list."""
    namespaces = result.get("namespaces", [])
    if not namespaces:
        return "No namespaces found."

    lines = ["# Namespaces\n"]
    for ns in namespaces:
        name = ns.get("name", "Unknown")
        ns_id = ns.get("id", "")
        desc = ns.get("description", "")
        lines.append(f"- **{name}** (`{ns_id}`)")
        if desc:
            lines.append(f"  {desc}")

    return "\n".join(lines)


def format_document_list(result: dict[str, Any]) -> str:
    """Format document list."""
    documents = result.get("documents", [])
    if not documents:
        return "No documents found."

    lines = ["# Documents\n"]
    for doc in documents:
        filename = doc.get("filename", "Untitled")
        doc_id = doc.get("doc_id", "")
        chunks = doc.get("chunk_count", doc.get("total_chunks", "?"))
        lines.append(f"- **{filename}** (`{doc_id}`) - {chunks} chunks")

    return "\n".join(lines)


def format_document(result: dict[str, Any]) -> str:
    """Format document metadata and summary.

    The get_document endpoint returns metadata only (no chunk text), so the
    body is the AI summary; full text requires the chunks endpoint.
    """
    filename = result.get("filename", "Untitled")
    doc_id = result.get("doc_id", "")
    namespace = result.get("namespace", "default")
    text = result.get("reconstructed_text") or result.get("text")

    lines = [
        f"# {filename}",
        f"**ID:** `{doc_id}` | **Namespace:** {namespace} | **Chunks:** {result.get('chunk_count', '?')}",
        "---",
    ]
    if text:
        lines.append(text)
    elif summary := result.get("summary"):
        lines.append(f"**Summary:** {summary}")
    else:
        lines.append("(no summary available; document content is stored as chunks)")
    if headings := result.get("headings"):
        lines.append("\n**Headings:** " + "; ".join(str(h) for h in headings[:20]))

    return "\n".join(lines)
