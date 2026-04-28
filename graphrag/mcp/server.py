"""GraphRAG MCP Server - exposes graph queries as agent-callable tools."""

import argparse
import os
import re
import subprocess
from collections.abc import Iterable
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from neo4j import Driver, GraphDatabase, Record

from graphrag.graph.sync import (
    auto_sync_graph as _auto_sync_graph_impl,
    safe_write_file as _safe_write_file_impl,
)

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


def _run_records(cypher: str, **parameters: Any) -> list[dict[str, Any]] | dict[str, str]:
    try:
        with _get_driver().session() as session:
            return _records_to_dicts(session.run(cypher, **parameters))
    except Exception as exc:  # noqa: BLE001
        return _error_response(exc)


def _run_single(cypher: str, **parameters: Any) -> dict[str, Any] | dict[str, str]:
    try:
        with _get_driver().session() as session:
            record = session.run(cypher, **parameters).single()
    except Exception as exc:  # noqa: BLE001
        return _error_response(exc)

    if record is None:
        return {}
    return dict(record.items())


def _as_int(value: Any) -> int | None:
    return int(value) if value is not None else None


def _as_float(value: Any) -> float:
    return float(value) if value is not None else 0.0


def _safe_depth(value: int, default: int) -> int:
    if value < 1:
        return default
    return min(value, 10)


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


@mcp.tool()
def trace_execution_flow(
    fqn: str,
    max_depth: int = 5,
    min_confidence: float = 0.4,
) -> dict[str, Any]:
    """
    Trace all downstream function calls from a given method.
    Returns a tree of every function this method calls, recursively.
    Use this to understand what a function does end-to-end.

    Args:
        fqn: Fully-qualified name of the starting method.
        max_depth: Maximum call depth to traverse (default: 5).
        min_confidence: Minimum edge confidence to include (default: 0.4).
    """
    depth_limit = _safe_depth(max_depth, default=5)
    rows = _run_records(
        f"""
        MATCH path = (start:Method {{fqn: $fqn}})-[:CALLS*1..{depth_limit}]->(callee:Method)
        WHERE ALL(r IN relationships(path) WHERE r.confidence >= $min_confidence)
        WITH callee,
             relationships(path) AS rels,
             length(path) AS depth
        WITH callee,
             depth,
             reduce(conf = 1.0, r IN rels | conf * r.confidence) AS path_confidence
        RETURN callee.fqn AS callee_fqn,
               callee.name AS callee_name,
               callee.file AS callee_file,
               callee.line AS callee_line,
               depth,
               path_confidence
        ORDER BY depth ASC, path_confidence DESC
        LIMIT 100
        """,
        fqn=fqn,
        min_confidence=min_confidence,
    )
    if isinstance(rows, dict):
        return rows

    call_tree = [
        {
            "fqn": row.get("callee_fqn"),
            "name": row.get("callee_name"),
            "file": row.get("callee_file"),
            "line": _as_int(row.get("callee_line")),
            "depth": int(row.get("depth", 0)),
            "path_confidence": round(_as_float(row.get("path_confidence")), 3),
        }
        for row in rows
    ]
    return {
        "root_fqn": fqn,
        "max_depth": depth_limit,
        "min_confidence": min_confidence,
        "total_nodes": len(call_tree),
        "call_tree": call_tree,
    }


@mcp.tool()
def analyze_blast_radius(
    fqn: str,
    max_depth: int = 5,
    min_confidence: float = 0.4,
    fan_out_threshold: int = 20,
) -> dict[str, Any]:
    """
    Find everything that will break if you change this method.
    Traverses UPSTREAM - returns all callers, their callers, tests,
    and frontend components that depend on this method.
    This is your most important tool before refactoring anything.

    Args:
        fqn: Fully-qualified name of the method you want to change.
        max_depth: Maximum upstream depth to traverse (default: 5).
        min_confidence: Minimum edge confidence to include (default: 0.4).
        fan_out_threshold: Skip nodes with more than this many outgoing
                           calls - they are utilities, not real dependents
                           (default: 20).
    """
    depth_limit = _safe_depth(max_depth, default=5)
    method_rows = _run_records(
        f"""
        MATCH path = (caller:Method)-[:CALLS*1..{depth_limit}]->(target:Method {{fqn: $fqn}})
        WHERE ALL(r IN relationships(path) WHERE r.confidence >= $min_confidence)
        WITH caller,
             length(path) AS depth,
             reduce(conf = 1.0, r IN relationships(path) | conf * r.confidence) AS path_confidence
        WHERE path_confidence >= $min_confidence
        WITH caller, depth, path_confidence
        WHERE size([(caller)-[:CALLS]->() | 1]) <= $fan_out_threshold
        RETURN caller.fqn AS caller_fqn,
               caller.name AS caller_name,
               caller.file AS caller_file,
               caller.line AS caller_line,
               caller.language AS language,
               depth,
               path_confidence
        ORDER BY path_confidence DESC, depth ASC
        LIMIT 100
        """,
        fqn=fqn,
        min_confidence=min_confidence,
        fan_out_threshold=fan_out_threshold,
    )
    if isinstance(method_rows, dict):
        return method_rows

    frontend_rows = _run_records(
        """
        MATCH (rc:RouteCall)-[:ROUTES_TO]->(e:Endpoint)<-[:HANDLES]-(target:Method {fqn: $fqn})
        RETURN rc.source_method_fqn AS source_fqn,
               rc.path AS api_path,
               rc.http_method AS http_method
        """,
        fqn=fqn,
    )
    if isinstance(frontend_rows, dict):
        return frontend_rows

    affected_methods = [
        {
            "fqn": row.get("caller_fqn"),
            "name": row.get("caller_name"),
            "file": row.get("caller_file"),
            "line": _as_int(row.get("caller_line")),
            "language": row.get("language"),
            "depth": int(row.get("depth", 0)),
            "path_confidence": round(_as_float(row.get("path_confidence")), 3),
        }
        for row in method_rows
    ]
    frontend_callers = [
        {
            "source_fqn": row.get("source_fqn"),
            "api_path": row.get("api_path"),
            "http_method": row.get("http_method"),
        }
        for row in frontend_rows
    ]
    return {
        "target_fqn": fqn,
        "total_affected": len(affected_methods) + len(frontend_callers),
        "affected_methods": affected_methods,
        "frontend_callers": frontend_callers,
    }


@mcp.tool()
def trace_network_boundary(path_or_method: str) -> dict[str, Any]:
    """
    Trace the complete request lifecycle from a frontend API call to
    its backend handler. Input either a URL path ("/api/users") or
    a frontend method name/FQN.
    This is the cross-language killer feature - it works across
    TypeScript frontend and Python/Java/Go backend with zero guessing.

    Args:
        path_or_method: Either a URL path like "/api/users" or a
                        method name/FQN from the frontend code.
    """
    route_rows = _run_records(
        """
        MATCH (m:Method)-[:MAKES_CALL]->(rc:RouteCall)
        WHERE rc.path CONTAINS $search_term
           OR m.name CONTAINS $search_term
           OR m.fqn CONTAINS $search_term
        RETURN m.fqn AS source_fqn,
               m.name AS source_name,
               m.file AS source_file,
               m.language AS source_language,
               rc.path AS route_path,
               rc.http_method AS http_method,
               rc.confidence AS call_confidence
        ORDER BY rc.path
        LIMIT 10
        """,
        search_term=path_or_method,
    )
    if isinstance(route_rows, dict):
        return route_rows

    chains: list[dict[str, Any]] = []
    for route in route_rows:
        backend_rows = _run_records(
            """
            MATCH (rc:RouteCall {path: $path, http_method: $http_method})
                  -[r1:ROUTES_TO]->(e:Endpoint)<-[:HANDLES]-(handler:Method)
            RETURN e.path AS endpoint_path,
                   e.http_method AS endpoint_method,
                   r1.confidence AS stitch_confidence,
                   r1.match_type AS match_type,
                   handler.fqn AS handler_fqn,
                   handler.name AS handler_name,
                   handler.file AS handler_file,
                   handler.language AS handler_language,
                   handler.line AS handler_line
            LIMIT 5
            """,
            path=route.get("route_path"),
            http_method=route.get("http_method"),
        )
        if isinstance(backend_rows, dict):
            return backend_rows

        for backend in backend_rows:
            downstream_rows = _run_records(
                """
                MATCH (handler:Method {fqn: $handler_fqn})-[:CALLS*1..3]->(downstream:Method)
                RETURN downstream.fqn AS fqn,
                       downstream.name AS name,
                       downstream.file AS file,
                       downstream.language AS language
                ORDER BY downstream.fqn
                LIMIT 20
                """,
                handler_fqn=backend.get("handler_fqn"),
            )
            if isinstance(downstream_rows, dict):
                return downstream_rows

            chains.append(
                {
                    "frontend": {
                        "method_fqn": route.get("source_fqn"),
                        "method_name": route.get("source_name"),
                        "file": route.get("source_file"),
                        "language": route.get("source_language"),
                    },
                    "route_call": {
                        "path": route.get("route_path"),
                        "http_method": route.get("http_method"),
                        "confidence": _as_float(route.get("call_confidence")),
                    },
                    "stitch": {
                        "confidence": _as_float(backend.get("stitch_confidence")),
                        "match_type": backend.get("match_type"),
                    },
                    "backend_handler": {
                        "fqn": backend.get("handler_fqn"),
                        "name": backend.get("handler_name"),
                        "file": backend.get("handler_file"),
                        "language": backend.get("handler_language"),
                        "line": _as_int(backend.get("handler_line")),
                    },
                    "downstream_calls": [
                        {
                            "fqn": row.get("fqn"),
                            "name": row.get("name"),
                            "file": row.get("file"),
                            "language": row.get("language"),
                        }
                        for row in downstream_rows
                    ],
                }
            )

    return {
        "query": path_or_method,
        "chains": chains,
    }


@mcp.tool()
def find_data_lineage(
    method_fqn: str,
    max_depth: int = 6,
) -> dict[str, Any]:
    """
    Trace where data goes after entering a method - follow the call
    chain downstream to find where it is persisted, returned, or
    transformed. Useful for finding data flow bugs and understanding
    what a payload touches.

    Args:
        method_fqn: FQN of the entry point method (e.g. an API handler).
        max_depth: Maximum depth to trace downstream (default: 6).
    """
    depth_limit = _safe_depth(max_depth, default=6)
    rows = _run_records(
        f"""
        MATCH path = (entry:Method {{fqn: $fqn}})-[:CALLS*1..{depth_limit}]->(node:Method)
        WITH node,
             length(path) AS depth,
             reduce(conf = 1.0, r IN relationships(path) | conf * r.confidence) AS path_confidence
        RETURN node.fqn AS fqn,
               node.name AS name,
               node.file AS file,
               node.language AS language,
               node.source_code AS source_code,
               depth,
               path_confidence
        ORDER BY depth ASC, path_confidence DESC
        LIMIT 50
        """,
        fqn=method_fqn,
    )
    if isinstance(rows, dict):
        return rows

    db_patterns = ("SELECT", "INSERT", "UPDATE", "DELETE", "query(", "execute(")
    lineage = []
    for row in rows:
        source_code = str(row.get("source_code") or "")
        lineage.append(
            {
                "fqn": row.get("fqn"),
                "name": row.get("name"),
                "file": row.get("file"),
                "language": row.get("language"),
                "depth": int(row.get("depth", 0)),
                "path_confidence": round(_as_float(row.get("path_confidence")), 3),
                "is_db_interaction": any(pattern in source_code for pattern in db_patterns),
            }
        )

    return {
        "entry_fqn": method_fqn,
        "total_nodes": len(lineage),
        "lineage": lineage,
    }


@mcp.tool()
def find_circular_dependencies(scope: str = "") -> dict[str, Any]:
    """
    Find all circular import dependencies in the codebase.
    Circular deps cause import errors, tight coupling, and make
    refactoring extremely painful.

    Args:
        scope: Optional file path prefix to limit the search scope.
               Leave empty to check the entire codebase.
    """
    rows = _run_records(
        """
        MATCH (a:File)-[:IMPORTS*2..6]->(a)
        WHERE $scope = "" OR a.path STARTS WITH $scope
        WITH DISTINCT a
        MATCH (a)-[:IMPORTS]->(b:File)
        WHERE (b)-[:IMPORTS*1..5]->(a)
          AND ($scope = "" OR a.path STARTS WITH $scope)
        RETURN a.path AS file_a,
               b.path AS file_b
        ORDER BY file_a
        LIMIT 50
        """,
        scope=scope,
    )
    if isinstance(rows, dict):
        return rows

    cycles = [
        {
            "file_a": row.get("file_a"),
            "file_b": row.get("file_b"),
        }
        for row in rows
    ]
    cycle_count = len(cycles)
    scope_label = scope or "all"
    message = (
        f"Found {cycle_count} circular import dependencies in {scope_label}."
        if cycle_count
        else f"No circular import dependencies found in {scope_label}."
    )
    return {
        "scope": scope,
        "cycle_count": cycle_count,
        "cycles": cycles,
        "message": message,
    }


@mcp.tool()
def find_dead_code(scope: str = "") -> dict[str, Any]:
    """
    Find all methods that are never called by anything.
    These are safe deletion candidates - they add complexity with
    zero value. Does not flag known entrypoints (main, __init__,
    setUp, test_*, handle*, on_*).

    Args:
        scope: Optional file path prefix to limit search scope.
    """
    rows = _run_records(
        """
        MATCH (m:Method)
        WHERE NOT (m)<-[:CALLS]-()
          AND NOT m.name IN [
            'main', '__init__', '__new__', '__str__', '__repr__',
            'setUp', 'tearDown', 'setUpClass', 'tearDownClass'
          ]
          AND NOT m.name STARTS WITH 'test_'
          AND NOT m.name STARTS WITH 'handle'
          AND NOT m.name STARTS WITH 'on_'
          AND ($scope = "" OR m.file STARTS WITH $scope)
          AND NOT m.fqn STARTS WITH "unresolved."
        RETURN m.fqn AS fqn,
               m.name AS name,
               m.file AS file,
               m.line AS line,
               m.language AS language
        ORDER BY m.file, m.line
        LIMIT 100
        """,
        scope=scope,
    )
    if isinstance(rows, dict):
        return rows

    dead_methods = [
        {
            "fqn": row.get("fqn"),
            "name": row.get("name"),
            "file": row.get("file"),
            "line": _as_int(row.get("line")),
            "language": row.get("language"),
        }
        for row in rows
    ]
    return {
        "scope": scope,
        "total_dead_methods": len(dead_methods),
        "dead_methods": dead_methods,
    }


@mcp.tool()
def identify_god_classes(
    scope: str = "",
    threshold: int = 10,
) -> dict[str, Any]:
    """
    Find classes that do too much - high number of methods and
    outgoing dependencies. These are your top refactoring targets.
    God classes are the #1 cause of brittle, hard-to-test code.

    Args:
        scope: Optional file path prefix.
        threshold: Minimum method count to flag as god class (default: 10).
    """
    rows = _run_records(
        """
        MATCH (c:Class)-[:CONTAINS]->(m:Method)
        WHERE ($scope = "" OR c.file STARTS WITH $scope)
        WITH c, count(m) AS method_count
        WHERE method_count >= $threshold
        OPTIONAL MATCH (c)-[:CONTAINS]->(m2:Method)-[:CALLS]->(dep:Method)
        WHERE dep.file <> c.file
        WITH c, method_count, count(DISTINCT dep) AS external_deps
        RETURN c.fqn AS fqn,
               c.name AS name,
               c.file AS file,
               c.language AS language,
               method_count,
               external_deps,
               method_count + external_deps AS complexity_score
        ORDER BY complexity_score DESC
        LIMIT 20
        """,
        scope=scope,
        threshold=threshold,
    )
    if isinstance(rows, dict):
        return rows

    god_classes = [
        {
            "fqn": row.get("fqn"),
            "name": row.get("name"),
            "file": row.get("file"),
            "language": row.get("language"),
            "method_count": int(row.get("method_count", 0)),
            "external_deps": int(row.get("external_deps", 0)),
            "complexity_score": int(row.get("complexity_score", 0)),
        }
        for row in rows
    ]
    return {
        "scope": scope,
        "threshold": threshold,
        "total_found": len(god_classes),
        "god_classes": god_classes,
    }


@mcp.tool()
def check_architecture_drift(
    rules: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """
    Check if any imports violate defined architectural layer rules.
    Example rule: database layer must not import from UI layer.
    Catches architectural decay before it becomes unmaintainable.

    Args:
        rules: List of violation rules. Each rule is a dict with:
               {"from_layer": "db", "must_not_import": "ui"}
               Layer names are matched as path prefixes.
               If None, uses default rules.
    """
    default_rules = [
        {"from_layer": "repository", "must_not_import": "controller"},
        {"from_layer": "repository", "must_not_import": "router"},
        {"from_layer": "database", "must_not_import": "view"},
        {"from_layer": "database", "must_not_import": "ui"},
        {"from_layer": "model", "must_not_import": "controller"},
        {"from_layer": "model", "must_not_import": "router"},
    ]
    rules_to_check = rules if rules is not None else default_rules
    violations: list[dict[str, Any]] = []

    for rule in rules_to_check:
        rows = _run_records(
            """
            MATCH (a:File)-[:IMPORTS]->(b:File)
            WHERE a.path CONTAINS $from_layer
              AND b.path CONTAINS $must_not_import
            RETURN a.path AS violating_file,
                   b.path AS imported_file
            ORDER BY a.path
            LIMIT 20
            """,
            from_layer=rule["from_layer"],
            must_not_import=rule["must_not_import"],
        )
        if isinstance(rows, dict):
            return rows

        violations.extend(
            {
                "rule": rule,
                "violating_file": row.get("violating_file"),
                "imported_file": row.get("imported_file"),
            }
            for row in rows
        )

    return {
        "rules_checked": len(rules_to_check),
        "total_violations": len(violations),
        "violations": violations,
    }


@mcp.tool()
def map_third_party_deps(package_name: str) -> dict[str, Any]:
    """
    Find every internal method that touches a specific third-party
    package. Use this before upgrading or removing a dependency to
    understand the full blast radius of that change.

    Args:
        package_name: Name of the NPM/Pip/Cargo/Maven package.
                      Partial names work: "django" matches "django-rest".
    """
    method_rows = _run_records(
        """
        MATCH (f:File)-[:IMPORTS]->(p:Package)
        WHERE p.name CONTAINS $package_name
        WITH f
        MATCH (f)-[:CONTAINS*1..2]->(m:Method)
        RETURN DISTINCT m.fqn AS fqn,
                        m.name AS name,
                        m.file AS file,
                        m.language AS language,
                        m.line AS line
        ORDER BY m.file, m.line
        LIMIT 100
        """,
        package_name=package_name,
    )
    if isinstance(method_rows, dict):
        return method_rows

    summary = _run_single(
        """
        MATCH (f:File)-[:IMPORTS]->(p:Package)
        WHERE p.name CONTAINS $package_name
        RETURN count(DISTINCT f) AS affected_files,
               collect(DISTINCT p.name) AS matched_packages
        """,
        package_name=package_name,
    )
    if "error" in summary:
        return summary

    affected_methods = [
        {
            "fqn": row.get("fqn"),
            "name": row.get("name"),
            "file": row.get("file"),
            "language": row.get("language"),
            "line": _as_int(row.get("line")),
        }
        for row in method_rows
    ]
    return {
        "package_query": package_name,
        "matched_packages": list(summary.get("matched_packages", [])),
        "affected_files": int(summary.get("affected_files", 0)),
        "affected_methods_count": len(affected_methods),
        "affected_methods": affected_methods,
    }


@mcp.tool()
def find_interface_violations(scope: str = "") -> dict[str, Any]:
    """
    Find classes that are supposed to implement an interface/abstract
    class but are missing required methods. These are contract violations
    that cause runtime errors.

    Args:
        scope: Optional file path prefix.
    """
    rows = _run_records(
        """
        MATCH (interface:Class {is_interface: true})-[:CONTAINS]->(im:Method)
        WHERE ($scope = "" OR interface.file STARTS WITH $scope)
        WITH interface, im
        WHERE NOT EXISTS {
            MATCH (concrete:Class {is_interface: false})-[:CONTAINS]->(cm:Method)
            WHERE cm.name = im.name
              AND concrete.name <> interface.name
        }
        RETURN interface.fqn AS interface_fqn,
               interface.name AS interface_name,
               im.name AS unimplemented_method,
               im.signature AS required_signature,
               interface.file AS interface_file
        ORDER BY interface.fqn
        LIMIT 50
        """,
        scope=scope,
    )
    if isinstance(rows, dict):
        return rows

    violations = [
        {
            "interface_fqn": row.get("interface_fqn"),
            "interface_name": row.get("interface_name"),
            "unimplemented_method": row.get("unimplemented_method"),
            "required_signature": row.get("required_signature"),
            "interface_file": row.get("interface_file"),
        }
        for row in rows
    ]
    return {
        "scope": scope,
        "total_violations": len(violations),
        "violations": violations,
    }


def _migration_effort(total_touch_points: int) -> str:
    if total_touch_points < 10:
        return "LOW"
    if total_touch_points < 50:
        return "MEDIUM"
    if total_touch_points < 200:
        return "HIGH"
    return "VERY HIGH"


def _result_to_dict(result: Any, keys: list[str]) -> dict[str, Any]:
    if is_dataclass(result):
        return asdict(result)
    return {key: getattr(result, key) for key in keys}


@mcp.tool()
def estimate_migration_cost(
    from_package: str,
    to_package: str = "",
) -> dict[str, Any]:
    """
    Estimate the effort required to migrate away from a package.
    Returns all files, methods, and edges that touch this package
    so you can plan the migration work.

    Args:
        from_package: The package you want to migrate away from.
        to_package: Optional replacement package name (just for labeling).
    """
    summary = _run_single(
        """
        MATCH (f:File)-[:IMPORTS]->(p:Package)
        WHERE p.name CONTAINS $from_package
        WITH collect(DISTINCT f) AS affected_files,
             count(DISTINCT f) AS file_count
        UNWIND affected_files AS f
        MATCH (f)-[:CONTAINS*1..2]->(m:Method)
        RETURN count(DISTINCT m) AS method_count,
               file_count,
               collect(DISTINCT f.path)[..20] AS sample_files
        """,
        from_package=from_package,
    )
    if "error" in summary:
        return summary

    callers = _run_single(
        """
        MATCH (f:File)-[:IMPORTS]->(p:Package)
        WHERE p.name CONTAINS $from_package
        WITH f
        MATCH (f)-[:CONTAINS*1..2]->(m:Method)<-[:CALLS]-(caller:Method)
        RETURN count(DISTINCT caller) AS dependent_callers
        """,
        from_package=from_package,
    )
    if "error" in callers:
        return callers

    affected_files = int(summary.get("file_count", 0))
    affected_methods = int(summary.get("method_count", 0))
    dependent_callers = int(callers.get("dependent_callers", 0))
    total_touch_points = affected_files + affected_methods + dependent_callers
    return {
        "from_package": from_package,
        "to_package": to_package,
        "migration_cost": {
            "affected_files": affected_files,
            "affected_methods": affected_methods,
            "dependent_callers": dependent_callers,
            "total_touch_points": total_touch_points,
            "effort_estimate": _migration_effort(total_touch_points),
        },
        "sample_files": list(summary.get("sample_files", [])),
    }


@mcp.tool()
def safe_write_file(file_path: str, content: str) -> dict[str, Any]:
    """
    Write code to a file - but validate syntax with Tree-sitter first.
    If the code has syntax errors, it is REJECTED and nothing is written.
    If clean, the file is written and the graph is automatically updated.
    This prevents the AI from writing broken code to your codebase.

    Args:
        file_path: Absolute or relative path to write to.
        content: The complete file content to write.
    """
    return _result_to_dict(
        _safe_write_file_impl(file_path, content),
        ["success", "file_path", "message", "syntax_errors", "graph_updated"],
    )


@mcp.tool()
def auto_sync_graph(file_path: str) -> dict[str, Any]:
    """
    Re-parse a single file and patch the graph with only the changes.
    Called automatically after safe_write_file. Can also be called
    manually after editing a file outside the MCP server.

    Args:
        file_path: Path to the file that was modified.
    """
    return _result_to_dict(
        _auto_sync_graph_impl(file_path),
        ["file_path", "nodes_added", "nodes_removed", "nodes_updated", "edges_added", "git_sha"],
    )


@mcp.tool()
def query_graph_raw(cypher: str) -> dict[str, Any]:
    """
    Execute a raw read-only Cypher query against the graph.
    Escape hatch for power users and complex queries not covered
    by other tools. WRITE operations are blocked for safety.

    Args:
        cypher: A read-only Cypher query string.
    """
    write_keywords = {
        "CREATE",
        "MERGE",
        "SET",
        "DELETE",
        "DETACH",
        "REMOVE",
        "DROP",
        "CALL",
        "LOAD",
    }
    upper_cypher = cypher.upper()
    if any(keyword in upper_cypher for keyword in write_keywords):
        return {
            "error": (
                "Write operations are not permitted in query_graph_raw. "
                "Use safe_write_file for modifications."
            )
        }

    rows = _run_records(cypher)
    if isinstance(rows, dict):
        return rows

    results = rows[:100]
    return {
        "query": cypher,
        "row_count": len(results),
        "results": results,
    }


def _pascal_case(value: str) -> str:
    parts = re.split(r"[^A-Za-z0-9]+", value)
    return "".join(part[:1].upper() + part[1:] for part in parts if part) or "Feature"


@mcp.tool()
def scaffold_polyglot_feature(
    feature_name: str,
    stack: str = "fastapi+react",
) -> dict[str, Any]:
    """
    Generate boilerplate for a new full-stack feature based on
    patterns already in the codebase. Queries the graph for
    existing patterns and generates matching boilerplate.

    Args:
        feature_name: Name of the feature e.g. "Payment", "Notification"
        stack: Stack to generate for. Options:
               "fastapi+react" (default), "express+react", "spring+react"
    """
    backend_lang_by_stack = {
        "fastapi+react": "python",
        "express+react": "typescript",
        "spring+react": "java",
    }
    backend_lang = backend_lang_by_stack.get(stack, "python")
    patterns = _run_records(
        """
        MATCH (m:Method)-[:HANDLES]->(e:Endpoint)
        WHERE e.language = $backend_lang
        RETURN e.path AS path, e.http_method AS method,
               m.signature AS signature
        LIMIT 5
        """,
        backend_lang=backend_lang,
    )
    if isinstance(patterns, dict):
        return patterns

    component_name = _pascal_case(feature_name)
    feature_name_lower = feature_name.lower()
    if stack == "express+react":
        backend_content = f"""import express from 'express';

const router = express.Router();

router.get('/{feature_name_lower}s', (_req, res) => {{
  res.json([]);
}});

router.post('/{feature_name_lower}s', (req, res) => {{
  res.json(req.body);
}});

export default router;
"""
        backend_path = f"backend/{feature_name_lower}_router.ts"
        backend_language = "typescript"
    elif stack == "spring+react":
        backend_content = f"""import org.springframework.web.bind.annotation.*;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/{feature_name_lower}s")
public class {component_name}Controller {{
    @GetMapping
    public List<Object> get{component_name}s() {{
        return List.of();
    }}

    @PostMapping
    public Map<String, Object> create{component_name}(@RequestBody Map<String, Object> data) {{
        return data;
    }}
}}
"""
        backend_path = f"backend/{component_name}Controller.java"
        backend_language = "java"
    else:
        backend_content = f'''from fastapi import APIRouter

router = APIRouter()

@router.get("/{feature_name_lower}s")
def get_{feature_name_lower}s():
    return []

@router.post("/{feature_name_lower}s")
def create_{feature_name_lower}(data: dict):
    return data

@router.get("/{feature_name_lower}s/{{id}}")
def get_{feature_name_lower}(id: str):
    return {{"id": id}}

@router.delete("/{feature_name_lower}s/{{id}}")
def delete_{feature_name_lower}(id: str):
    return {{"deleted": id}}
'''
        backend_path = f"backend/{feature_name_lower}_router.py"
        backend_language = "python"

    frontend_content = f"""import React, {{ useEffect, useState }} from 'react';

const {component_name}List: React.FC = () => {{
  const [items, setItems] = useState([]);

  useEffect(() => {{
    fetch('/{feature_name_lower}s')
      .then(r => r.json())
      .then(setItems);
  }}, []);

  return <div>{{items.length}} {component_name}s</div>;
}};

export default {component_name}List;
"""
    return {
        "feature_name": feature_name,
        "stack": stack,
        "files": [
            {
                "suggested_path": backend_path,
                "content": backend_content,
                "language": backend_language,
            },
            {
                "suggested_path": f"frontend/{component_name}List.tsx",
                "content": frontend_content,
                "language": "typescript",
            },
        ],
        "existing_patterns_used": len(patterns),
    }


def _class_name_from_fqn(method_fqn: str) -> str:
    parts = method_fqn.split(".")
    return _pascal_case(parts[-2]) if len(parts) >= 2 else "Subject"


@mcp.tool()
def generate_test_suite(method_fqn: str) -> dict[str, Any]:
    """
    Analyze a method's dependencies from the graph and generate
    a unit test file with mocks for every dependency.

    Args:
        method_fqn: FQN of the method to generate tests for.
    """
    method_info = _run_single(
        """
        MATCH (m:Method {fqn: $fqn})
        RETURN m.name AS name, m.file AS file,
               m.language AS language, m.signature AS signature,
               m.source_code AS source_code
        """,
        fqn=method_fqn,
    )
    if "error" in method_info:
        return method_info
    if not method_info:
        return {"error": f"No method found for FQN '{method_fqn}'"}

    dependencies = _run_records(
        """
        MATCH (m:Method {fqn: $fqn})-[:CALLS]->(dep:Method)
        WHERE dep.resolved = true OR dep.resolved IS NULL
        RETURN dep.fqn AS fqn, dep.name AS name
        LIMIT 20
        """,
        fqn=method_fqn,
    )
    if isinstance(dependencies, dict):
        return dependencies

    method_name = str(method_info.get("name") or method_fqn.split(".")[-1])
    language = str(method_info.get("language") or "unknown")
    file_path = str(method_info.get("file") or "")
    class_name = _class_name_from_fqn(method_fqn)
    dependency_names = [str(dep.get("name") or dep.get("fqn")) for dep in dependencies]
    dep_count = len(dependency_names)

    if language == "typescript":
        file_stem = Path(file_path).stem or method_name
        dep_module = dependency_names[0] if dependency_names else file_stem
        content = f"""// Auto-generated test for {method_fqn}
import {{ {class_name} }} from './{file_stem}';

jest.mock('{dep_module}');

describe('{class_name}', () => {{
  let instance: {class_name};

  beforeEach(() => {{
    instance = new {class_name}();
  }});

  it('should execute {method_name}', () => {{
    const result = instance.{method_name}();
    expect(result).toBeDefined();
  }});
}});
"""
        suggested_path = f"tests/{file_stem}.test.ts"
    else:
        mock_setup = "        self.instance = MagicMock()\n"
        if dependency_names:
            mock_setup += "".join(
                f"        self.{name}_mock = MagicMock()\n" for name in dependency_names
            )
        mock_assertions = "        result = self.instance.{method_name}()\n"
        mock_assertions += "        assert result is not None\n"
        content = f'''import pytest
from unittest.mock import MagicMock, patch

# Auto-generated test for {method_fqn}
# Dependencies detected: {dep_count}

class Test{class_name}:

    def setup_method(self):
        """Set up mocks for all detected dependencies."""
{mock_setup}
    def test_{method_name}_basic(self):
        """Test basic execution of {method_name}."""
        # TODO: Add assertions based on expected behaviour
        result = self.instance.{method_name}()
        assert result is not None

    def test_{method_name}_with_mocked_deps(self):
        """Test with all dependencies mocked."""
{mock_assertions.format(method_name=method_name)}
'''
        suggested_path = f"tests/test_{Path(file_path).stem or method_name}.py"

    return {
        "method_fqn": method_fqn,
        "language": language,
        "dependency_count": dep_count,
        "dependencies_mocked": dependency_names,
        "test_file": {
            "suggested_path": suggested_path,
            "content": content,
        },
    }


@mcp.tool()
def explain_change_history(file_path: str) -> dict[str, Any]:
    """
    Combine git blame data with graph complexity metrics to explain
    why a file or method is complex. Helps new developers understand
    the history behind confusing code.

    Args:
        file_path: Path to the file to analyse.
    """
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", "-10", file_path],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        commits = result.stdout.strip().split("\n") if result.returncode == 0 else []
        commits = [commit for commit in commits if commit]
    except Exception:  # noqa: BLE001
        commits = []

    metrics = _run_single(
        """
        MATCH (f:File)-[:CONTAINS*1..2]->(m:Method)
        WHERE f.path CONTAINS $file_path
        WITH count(m) AS method_count,
             avg(size([(m)-[:CALLS]->() | 1])) AS avg_outgoing_calls
        RETURN method_count, avg_outgoing_calls
        """,
        file_path=file_path,
    )
    if "error" in metrics:
        return metrics

    hotspot_rows = _run_records(
        """
        MATCH (caller:Method)-[:CALLS]->(m:Method)
        WHERE m.file CONTAINS $file_path
        WITH m, count(caller) AS call_count
        RETURN m.name AS method_name, m.fqn AS fqn, call_count
        ORDER BY call_count DESC
        LIMIT 5
        """,
        file_path=file_path,
    )
    if isinstance(hotspot_rows, dict):
        return hotspot_rows

    return {
        "file_path": file_path,
        "git_history": {
            "recent_commits": commits,
            "commit_count": len(commits),
        },
        "complexity_metrics": {
            "method_count": int(metrics.get("method_count", 0)),
            "avg_outgoing_calls": round(_as_float(metrics.get("avg_outgoing_calls")), 3),
        },
        "hotspot_methods": [
            {
                "method_name": row.get("method_name"),
                "fqn": row.get("fqn"),
                "call_count": int(row.get("call_count", 0)),
            }
            for row in hotspot_rows
        ],
    }


def _mermaid_id(value: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9_]", "_", value)
    return sanitized.strip("_") or "node"


@mcp.tool()
def generate_architecture_diagram(
    scope: str = "",
    diagram_type: str = "module",
) -> dict[str, Any]:
    """
    Generate a Mermaid diagram from the graph for a module or service.
    Output can be pasted directly into any Mermaid renderer or GitHub markdown.

    Args:
        scope: File path prefix to scope the diagram.
        diagram_type: "module" for file dependencies,
                      "class" for class hierarchy,
                      "endpoint" for API endpoint map.
    """
    if diagram_type == "module":
        rows = _run_records(
            """
            MATCH (a:File)-[:IMPORTS]->(b:File)
            WHERE ($scope = "" OR a.path STARTS WITH $scope)
            RETURN a.path AS from_path, b.path AS to_path
            LIMIT 30
            """,
            scope=scope,
        )
        if isinstance(rows, dict):
            return rows

        lines = ["flowchart TD"]
        for row in rows:
            from_path = str(row.get("from_path") or "")
            to_path = str(row.get("to_path") or "")
            lines.append(
                f'    {_mermaid_id(from_path)}["{Path(from_path).name}"] '
                f'--> {_mermaid_id(to_path)}["{Path(to_path).name}"]'
            )
        node_count = len({path for row in rows for path in (row.get("from_path"), row.get("to_path"))})
        edge_count = len(rows)
    elif diagram_type == "class":
        rows = _run_records(
            """
            MATCH (c:Class)-[:CONTAINS]->(m:Method)
            WHERE ($scope = "" OR c.file STARTS WITH $scope)
            RETURN c.name AS class_name, collect(m.name)[..5] AS methods
            LIMIT 20
            """,
            scope=scope,
        )
        if isinstance(rows, dict):
            return rows

        lines = ["classDiagram"]
        for row in rows:
            class_name = str(row.get("class_name") or "UnknownClass")
            lines.append(f"    class {class_name} {{")
            for method in row.get("methods", []):
                lines.append(f"        +{method}()")
            lines.append("    }")
        node_count = len(rows)
        edge_count = sum(len(row.get("methods", [])) for row in rows)
    elif diagram_type == "endpoint":
        rows = _run_records(
            """
            MATCH (m:Method)-[:HANDLES]->(e:Endpoint)
            WHERE ($scope = "" OR m.file STARTS WITH $scope)
            RETURN e.http_method AS method, e.path AS path, m.name AS handler
            ORDER BY e.path
            LIMIT 30
            """,
            scope=scope,
        )
        if isinstance(rows, dict):
            return rows

        lines = ["flowchart LR"]
        for row in rows:
            method = str(row.get("method") or "GET")
            path = str(row.get("path") or "/")
            handler = str(row.get("handler") or "handler")
            endpoint_id = _mermaid_id(f"{method}_{path}")
            handler_id = _mermaid_id(handler)
            lines.append(f'    {endpoint_id}["{method} {path}"] --> {handler_id}["{handler}()"]')
        node_count = len(rows) * 2
        edge_count = len(rows)
    else:
        return {"error": f"Invalid diagram_type '{diagram_type}'"}

    return {
        "scope": scope,
        "diagram_type": diagram_type,
        "mermaid": "\n".join(lines),
        "node_count": node_count,
        "edge_count": edge_count,
    }


@mcp.tool()
def summarize_module(module_path: str) -> dict[str, Any]:
    """
    Generate a high-level summary of a module's responsibilities
    from its graph structure. Useful for quickly understanding an
    unfamiliar module without reading all the code.

    Args:
        module_path: File path prefix for the module to summarize.
    """
    file_rows = _run_records(
        """
        MATCH (f:File)
        WHERE f.path CONTAINS $module_path
        RETURN f.path AS path, f.language AS language
        ORDER BY f.path
        LIMIT 20
        """,
        module_path=module_path,
    )
    if isinstance(file_rows, dict):
        return file_rows

    interface_rows = _run_records(
        """
        MATCH (caller:Method)-[:CALLS]->(m:Method)
        WHERE m.file CONTAINS $module_path
          AND NOT caller.file CONTAINS $module_path
        WITH m, count(caller) AS external_callers
        RETURN m.name AS name, m.fqn AS fqn,
               m.signature AS signature, external_callers
        ORDER BY external_callers DESC
        LIMIT 10
        """,
        module_path=module_path,
    )
    if isinstance(interface_rows, dict):
        return interface_rows

    dependency_rows = _run_records(
        """
        MATCH (f:File)-[:IMPORTS]->(dep)
        WHERE f.path CONTAINS $module_path
        RETURN DISTINCT
            labels(dep)[0] AS dep_type,
            coalesce(dep.name, dep.path) AS dep_name
        ORDER BY dep_type, dep_name
        LIMIT 20
        """,
        module_path=module_path,
    )
    if isinstance(dependency_rows, dict):
        return dependency_rows

    files = [
        {
            "path": row.get("path"),
            "language": row.get("language"),
        }
        for row in file_rows
    ]
    return {
        "module_path": module_path,
        "files": files,
        "file_count": len(files),
        "public_interface": [
            {
                "name": row.get("name"),
                "fqn": row.get("fqn"),
                "signature": row.get("signature"),
                "external_callers": int(row.get("external_callers", 0)),
            }
            for row in interface_rows
        ],
        "external_dependencies": [
            {
                "dep_type": row.get("dep_type"),
                "dep_name": row.get("dep_name"),
            }
            for row in dependency_rows
        ],
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
        mcp.settings.host = "0.0.0.0"
        mcp.settings.port = args.port
        mcp.run(transport="sse")


if __name__ == "__main__":
    serve()

