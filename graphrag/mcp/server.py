"""GraphRAG MCP Server - exposes graph queries as agent-callable tools."""

import argparse
import os
from collections.abc import Iterable
from typing import Any

from dotenv import load_dotenv
from neo4j import Driver, GraphDatabase, Record

try:
    from mcp.server.fastmcp import FastMCP
except ModuleNotFoundError:
    class FastMCP:  # type: ignore[no-redef]
        """Fallback stub used when the MCP SDK is not installed."""

        def __init__(self, name: str, instructions: str) -> None:
            self.name = name
            self.instructions = instructions

        def tool(self) -> Any:
            def decorator(func: Any) -> Any:
                return func

            return decorator

        def run(self, transport: str, port: int | None = None) -> None:
            raise RuntimeError(
                "The 'mcp' package is not installed. Install dependencies with "
                "`mcp[cli]>=1.0.0` to run the MCP server."
            )

load_dotenv()

mcp = FastMCP(
    name="graphrag",
    instructions="""
    You are connected to a Polyglot GraphRAG server with deterministic
    knowledge of a source code repository. Use these tools to answer
    questions about code architecture, dependencies, and execution flow
    with mathematical precision. Always prefer these tools over your
    training knowledge when answering questions about this codebase.
    """,
)

_driver: Driver | None = None


def _get_driver() -> Driver:
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(
            os.getenv("NEO4J_URI", "bolt://localhost:7687"),
            auth=(
                os.getenv("NEO4J_USERNAME", "neo4j"),
                os.getenv("NEO4J_PASSWORD", "neo4j_password"),
            ),
        )
    return _driver


def _error_response(exc: Exception) -> dict[str, str]:
    return {"error": f"Neo4j unreachable: {exc}"}


def _records_to_dicts(records: Iterable[Record]) -> list[dict[str, Any]]:
    return [dict(record.items()) for record in records]


def _run_records(query: str, **parameters: Any) -> list[dict[str, Any]] | dict[str, str]:
    try:
        with _get_driver().session() as session:
            return _records_to_dicts(session.run(query, **parameters))
    except Exception as exc:  # noqa: BLE001
        return _error_response(exc)


def _run_single(query: str, **parameters: Any) -> dict[str, Any] | dict[str, str]:
    try:
        with _get_driver().session() as session:
            record = session.run(query, **parameters).single()
    except Exception as exc:  # noqa: BLE001
        return _error_response(exc)

    if record is None:
        return {}
    return dict(record.items())


@mcp.tool()
def explore_architecture(repo_root: str = "") -> dict[str, Any]:
    """
    Returns a high-level overview of the ingested repository:
    language breakdown, top-level module count, class count,
    method count, and detected frameworks/patterns.

    Args:
        repo_root: Optional filter to scope results to a specific
                   repo path prefix. Leave empty for all ingested data.
    """
    language_rows = _run_records(
        """
        MATCH (f:File)
        WHERE $repo_root = "" OR f.path STARTS WITH $repo_root
        RETURN f.language AS language, count(f) AS file_count
        ORDER BY file_count DESC
        """,
        repo_root=repo_root,
    )
    if isinstance(language_rows, dict):
        return language_rows

    class_total = _run_single(
        """
        MATCH (c:Class)
        WHERE $repo_root = "" OR c.file STARTS WITH $repo_root
        RETURN count(c) AS class_count
        """,
        repo_root=repo_root,
    )
    if "error" in class_total:
        return class_total

    method_total = _run_single(
        """
        MATCH (m:Method)
        WHERE $repo_root = "" OR m.file STARTS WITH $repo_root
        RETURN count(m) AS method_count
        """,
        repo_root=repo_root,
    )
    if "error" in method_total:
        return method_total

    endpoint_total = _run_single(
        """
        MATCH (e:Endpoint)
        WHERE $repo_root = "" OR e.file STARTS WITH $repo_root
        RETURN count(e) AS endpoint_count
        """,
        repo_root=repo_root,
    )
    if "error" in endpoint_total:
        return endpoint_total

    package_rows = _run_records(
        """
        MATCH (p:Package)
        RETURN p.name AS package_name
        ORDER BY p.name
        LIMIT 20
        """
    )
    if isinstance(package_rows, dict):
        return package_rows

    languages: dict[str, int] = {}
    total_files = 0
    for row in language_rows:
        language = str(row.get("language") or "unknown")
        file_count = int(row.get("file_count", 0))
        languages[language] = file_count
        total_files += file_count

    return {
        "languages": languages,
        "totals": {
            "files": total_files,
            "classes": int(class_total.get("class_count", 0)),
            "methods": int(method_total.get("method_count", 0)),
            "endpoints": int(endpoint_total.get("endpoint_count", 0)),
        },
        "top_packages": [
            str(row["package_name"])
            for row in package_rows
            if row.get("package_name") is not None
        ],
        "repo_root": repo_root or "all",
    }


@mcp.tool()
def find_by_fqn(fqn: str) -> dict[str, Any]:
    """
    Locate a class or method by fully-qualified name and return its core metadata.

    Args:
        fqn: Fully-qualified class or method name to search for.
    """
    node = _run_single(
        """
        MATCH (n)
        WHERE (n:Class OR n:Method) AND n.fqn = $fqn
        RETURN labels(n)[0] AS node_type,
               n.fqn AS fqn,
               n.name AS name,
               n.file AS file,
               n.line AS line,
               n.signature AS signature
        LIMIT 1
        """,
        fqn=fqn,
    )
    if "error" in node:
        return node
    if not node:
        return {"error": f"No class or method found for FQN '{fqn}'"}

    callers = _run_records(
        """
        MATCH (caller:Method)-[:CALLS]->(target:Method {fqn: $fqn})
        RETURN caller.fqn AS fqn, caller.name AS name, caller.file AS file, caller.line AS line
        ORDER BY caller.fqn
        LIMIT 20
        """,
        fqn=fqn,
    )
    if isinstance(callers, dict):
        return callers

    callees = _run_records(
        """
        MATCH (source:Method {fqn: $fqn})-[:CALLS]->(callee:Method)
        RETURN callee.fqn AS fqn, callee.name AS name, callee.file AS file, callee.line AS line
        ORDER BY callee.fqn
        LIMIT 20
        """,
        fqn=fqn,
    )
    if isinstance(callees, dict):
        return callees

    return {
        "query": fqn,
        "match": {
            "node_type": node.get("node_type"),
            "fqn": node.get("fqn"),
            "name": node.get("name"),
            "file": node.get("file"),
            "line": int(node["line"]) if node.get("line") is not None else None,
            "signature": node.get("signature"),
        },
        "callers": [
            {
                "fqn": row.get("fqn"),
                "name": row.get("name"),
                "file": row.get("file"),
                "line": int(row["line"]) if row.get("line") is not None else None,
            }
            for row in callers
        ],
        "callees": [
            {
                "fqn": row.get("fqn"),
                "name": row.get("name"),
                "file": row.get("file"),
                "line": int(row["line"]) if row.get("line") is not None else None,
            }
            for row in callees
        ],
    }


@mcp.tool()
def search_ontology(keyword: str = "") -> dict[str, Any]:
    """
    Search across files, classes, methods, endpoints, and packages.

    Args:
        keyword: Optional search term matched against key graph entities.
    """
    query = keyword.strip()
    if not query:
        return {
            "keyword": "",
            "count": 0,
            "results": [],
        }

    rows = _run_records(
        """
        MATCH (n)
        WHERE (n:File AND (n.path CONTAINS $keyword OR coalesce(n.module_name, "") CONTAINS $keyword))
           OR ((n:Class OR n:Method) AND (n.name CONTAINS $keyword OR n.fqn CONTAINS $keyword))
           OR (n:Endpoint AND n.path CONTAINS $keyword)
           OR (n:Package AND n.name CONTAINS $keyword)
        RETURN labels(n)[0] AS node_type,
               coalesce(n.fqn, n.path, n.name) AS identifier,
               n.name AS name,
               n.path AS path,
               n.file AS file,
               n.line AS line
        ORDER BY node_type, identifier
        LIMIT 50
        """,
        keyword=query,
    )
    if isinstance(rows, dict):
        return rows

    results = [
        {
            "node_type": row.get("node_type"),
            "identifier": row.get("identifier"),
            "name": row.get("name"),
            "path": row.get("path"),
            "file": row.get("file"),
            "line": int(row["line"]) if row.get("line") is not None else None,
        }
        for row in rows
    ]
    return {
        "keyword": query,
        "count": len(results),
        "results": results,
    }


@mcp.tool()
def get_file_context(file_path: str) -> dict[str, Any]:
    """
    Returns all classes, methods, imports, and immediate call edges
    for a specific file. Use this to understand what a file does
    before making changes to it.

    Args:
        file_path: Relative or absolute path to the source file.
                   Partial paths are matched with CONTAINS.
    """
    file_metadata = _run_single(
        """
        MATCH (f:File)
        WHERE f.path CONTAINS $file_path
        RETURN f.path AS path,
               f.language AS language,
               f.module_name AS module_name,
               f.last_parsed AS last_parsed
        LIMIT 1
        """,
        file_path=file_path,
    )
    if "error" in file_metadata:
        return file_metadata
    if not file_metadata:
        return {"error": f"No file found matching '{file_path}'"}

    class_rows = _run_records(
        """
        MATCH (f:File)-[:CONTAINS]->(c:Class)
        WHERE f.path CONTAINS $file_path
        RETURN c.fqn AS fqn, c.name AS name, c.line AS line
        ORDER BY c.line
        """,
        file_path=file_path,
    )
    if isinstance(class_rows, dict):
        return class_rows

    method_rows = _run_records(
        """
        MATCH (f:File)-[:CONTAINS*1..2]->(m:Method)
        WHERE f.path CONTAINS $file_path
        OPTIONAL MATCH (m)-[:CALLS]->(callee:Method)
        RETURN m.fqn AS fqn,
               m.name AS name,
               m.line AS line,
               m.signature AS signature,
               count(callee) AS outgoing_calls
        ORDER BY m.line
        """,
        file_path=file_path,
    )
    if isinstance(method_rows, dict):
        return method_rows

    import_rows = _run_records(
        """
        MATCH (f:File)-[:IMPORTS]->(target)
        WHERE f.path CONTAINS $file_path
        RETURN labels(target)[0] AS target_type,
               coalesce(target.path, target.name) AS target_name
        """,
        file_path=file_path,
    )
    if isinstance(import_rows, dict):
        return import_rows

    return {
        "file": {
            "path": file_metadata.get("path"),
            "language": file_metadata.get("language"),
            "module_name": file_metadata.get("module_name"),
            "last_parsed": file_metadata.get("last_parsed"),
        },
        "classes": [
            {
                "fqn": row.get("fqn"),
                "name": row.get("name"),
                "line": int(row["line"]) if row.get("line") is not None else None,
            }
            for row in class_rows
        ],
        "methods": [
            {
                "fqn": row.get("fqn"),
                "name": row.get("name"),
                "line": int(row["line"]) if row.get("line") is not None else None,
                "signature": row.get("signature"),
                "outgoing_calls": int(row.get("outgoing_calls", 0)),
            }
            for row in method_rows
        ],
        "imports": [
            {
                "target_type": row.get("target_type"),
                "target_name": row.get("target_name"),
            }
            for row in import_rows
        ],
    }


@mcp.tool()
def find_endpoints(keyword: str = "") -> dict[str, Any]:
    """
    Find all HTTP endpoints in the ingested codebase.
    Optionally filter by a keyword matched against the path or handler name.

    Args:
        keyword: Optional search term. Matches against endpoint path
                 and handler FQN. Leave empty to list all endpoints.
    """
    endpoint_rows = _run_records(
        """
        MATCH (m:Method)-[:HANDLES]->(e:Endpoint)
        WHERE $keyword = ""
              OR e.path CONTAINS $keyword
              OR m.name CONTAINS $keyword
              OR m.fqn CONTAINS $keyword
        RETURN e.path AS path,
               e.http_method AS http_method,
               m.fqn AS handler_fqn,
               m.name AS handler_name,
               m.language AS language,
               m.file AS file,
               m.line AS line
        ORDER BY e.path, e.http_method
        """,
        keyword=keyword,
    )
    if isinstance(endpoint_rows, dict):
        return endpoint_rows

    endpoints = [
        {
            "path": row.get("path"),
            "http_method": row.get("http_method"),
            "handler_fqn": row.get("handler_fqn"),
            "handler_name": row.get("handler_name"),
            "language": row.get("language"),
            "file": row.get("file"),
            "line": int(row["line"]) if row.get("line") is not None else None,
        }
        for row in endpoint_rows
    ]
    return {
        "keyword": keyword,
        "count": len(endpoints),
        "endpoints": endpoints,
    }


def serve() -> None:
    """Entry point for the graphrag-mcp CLI command."""
    parser = argparse.ArgumentParser(description="GraphRAG MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="Transport protocol (default: stdio for Claude Desktop / Cursor)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8001,
        help="Port for SSE transport (default: 8001)",
    )
    args = parser.parse_args()

    if args.transport == "stdio":
        mcp.run(transport="stdio")
    else:
        mcp.run(transport="sse", port=args.port)


if __name__ == "__main__":
    serve()

