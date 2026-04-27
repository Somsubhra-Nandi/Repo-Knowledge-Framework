"""Safe file writes with incremental graph synchronization."""

import hashlib
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase
from tree_sitter import Node

from graphrag.graph.writer import Neo4jWriter
from graphrag.parser.factory import get_parser, parse_file

load_dotenv()


@dataclass
class WriteResult:
    success: bool
    file_path: str
    message: str
    syntax_errors: list[str]
    graph_updated: bool


@dataclass
class SyncResult:
    file_path: str
    nodes_added: int
    nodes_removed: int
    nodes_updated: int
    edges_added: int
    git_sha: str


def _walk_error_nodes(node: Node, errors: list[str]) -> None:
    if node.type == "ERROR":
        line = node.start_point[0] + 1
        column = node.start_point[1] + 1
        errors.append(f"ERROR at line {line}, column {column}")
    elif node.is_missing:
        line = node.start_point[0] + 1
        column = node.start_point[1] + 1
        errors.append(f"MISSING {node.type} at line {line}, column {column}")

    for child in node.children:
        _walk_error_nodes(child, errors)


def _validation_temp_dir() -> Path:
    temp_dir = Path("/tmp")
    try:
        temp_dir.mkdir(parents=True, exist_ok=True)
        return temp_dir
    except PermissionError:
        fallback = Path.cwd() / ".graphrag_tmp"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


def validate_syntax(file_path: str, content: str) -> list[str]:
    """Validate content with Tree-sitter and return syntax error descriptions."""
    suffix = Path(file_path).suffix
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
    temp_dir = _validation_temp_dir()
    temp_path = temp_dir / f"graphrag_validate_{content_hash}{suffix}"

    try:
        parser = get_parser(str(temp_path))
    except ValueError:
        return []

    try:
        temp_path.write_text(content, encoding="utf-8")
        source_bytes = temp_path.read_bytes()
        tree = parser.parse(source_bytes)
        errors: list[str] = []
        _walk_error_nodes(tree.root_node, errors)
        return errors
    finally:
        temp_path.unlink(missing_ok=True)


def _get_git_sha() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return result.stdout.strip()[:8] if result.returncode == 0 else "unknown"
    except Exception:  # noqa: BLE001
        return "unknown"


def _neo4j_credentials() -> tuple[str, str, str]:
    return (
        os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        os.getenv("NEO4J_USERNAME", "neo4j"),
        os.getenv("NEO4J_PASSWORD", "neo4j_password"),
    )


def auto_sync_graph(file_path: str) -> SyncResult:
    """Re-parse one file and synchronize its class/method nodes in Neo4j."""
    parsed_file = parse_file(file_path)
    new_fqns = {item.fqn for item in parsed_file.classes} | {item.fqn for item in parsed_file.methods}
    uri, username, password = _neo4j_credentials()
    driver = GraphDatabase.driver(uri, auth=(username, password))

    try:
        with driver.session() as session:
            records = session.run(
                """
                MATCH (n)
                WHERE (n:Method OR n:Class) AND n.file = $file_path
                RETURN n.fqn AS fqn, labels(n)[0] AS label
                """,
                file_path=file_path,
            )
            existing_fqns = {str(record["fqn"]) for record in records if record["fqn"] is not None}

            removed_fqns = existing_fqns - new_fqns
            for fqn in removed_fqns:
                session.run(
                    """
                    MATCH (n)
                    WHERE n.fqn = $fqn
                    DETACH DELETE n
                    """,
                    fqn=fqn,
                )
    finally:
        driver.close()

    writer = Neo4jWriter(uri=uri, username=username, password=password)
    try:
        writer.ingest_file(parsed_file)
    finally:
        writer.close()

    return SyncResult(
        file_path=file_path,
        nodes_added=len(new_fqns - existing_fqns),
        nodes_removed=len(removed_fqns),
        nodes_updated=len(new_fqns & existing_fqns),
        edges_added=sum(len(method.calls) for method in parsed_file.methods),
        git_sha=_get_git_sha(),
    )


def safe_write_file(file_path: str, content: str) -> WriteResult:
    """Validate syntax, write a file, and synchronize the graph."""
    syntax_errors = validate_syntax(file_path, content)
    if syntax_errors:
        return WriteResult(
            success=False,
            file_path=file_path,
            message="Syntax errors found",
            syntax_errors=syntax_errors,
            graph_updated=False,
        )

    target = Path(file_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    sync_result = auto_sync_graph(file_path)

    return WriteResult(
        success=True,
        file_path=file_path,
        message=f"File written and graph synced at {sync_result.git_sha}",
        syntax_errors=[],
        graph_updated=True,
    )
