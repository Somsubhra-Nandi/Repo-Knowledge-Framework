"""Command line interface for graphrag."""

from __future__ import annotations

import argparse
import os

from dotenv import load_dotenv
from neo4j import Driver, GraphDatabase

from graphrag.ingestion.pipeline import IngestionPipeline


def _env(name: str, default: str) -> str:
    return os.getenv(name, default)


def _build_driver() -> Driver:
    uri = _env("NEO4J_URI", "bolt://localhost:7687")
    username = _env("NEO4J_USERNAME", "neo4j")
    password = _env("NEO4J_PASSWORD", "neo4j_password")
    return GraphDatabase.driver(uri, auth=(username, password))


def _run_ingest(args: argparse.Namespace) -> int:
    pipeline = IngestionPipeline(
        neo4j_uri=_env("NEO4J_URI", "bolt://localhost:7687"),
        neo4j_username=_env("NEO4J_USERNAME", "neo4j"),
        neo4j_password=_env("NEO4J_PASSWORD", "neo4j_password"),
        workers=args.workers,
        repo_id=args.repo_id,
        quiet=args.quiet,
    )
    result = pipeline.run(args.repo_path)
    print("[graphrag] Ingestion result:")
    print(f"  Total files: {result.total_files}")
    print(f"  Parsed:      {result.parsed}")
    print(f"  Skipped:     {result.skipped}")
    print(f"  Failed:      {result.failed}")
    print(f"  Duration:    {result.duration_seconds:.2f}s")
    if result.errors:
        print("[graphrag] Errors:")
        for error in result.errors:
            print(f"  - {error}")
    return 1 if result.failed > 0 else 0


def _run_status(repo_id: str) -> int:
    driver = _build_driver()
    try:
        with driver.session() as session:
            if repo_id:
                files = session.run(
                    "MATCH (n:File {repo_id: $repo_id}) RETURN count(n) AS count",
                    repo_id=repo_id,
                ).single()
                classes = session.run(
                    "MATCH (n:Class {repo_id: $repo_id}) RETURN count(n) AS count",
                    repo_id=repo_id,
                ).single()
                methods = session.run(
                    "MATCH (n:Method {repo_id: $repo_id}) RETURN count(n) AS count",
                    repo_id=repo_id,
                ).single()
                calls = session.run(
                    "MATCH (a {repo_id: $repo_id})-[r:CALLS]->(b {repo_id: $repo_id}) RETURN count(r) AS count",
                    repo_id=repo_id,
                ).single()
                imports = session.run(
                    "MATCH (a {repo_id: $repo_id})-[r:IMPORTS]->(b {repo_id: $repo_id}) RETURN count(r) AS count",
                    repo_id=repo_id,
                ).single()
            else:
                files = session.run("MATCH (n:File) RETURN count(n) AS count").single()
                classes = session.run("MATCH (n:Class) RETURN count(n) AS count").single()
                methods = session.run("MATCH (n:Method) RETURN count(n) AS count").single()
                calls = session.run("MATCH ()-[r:CALLS]->() RETURN count(r) AS count").single()
                imports = session.run("MATCH ()-[r:IMPORTS]->() RETURN count(r) AS count").single()

        print("[graphrag] Graph status:")
        print(f"  Files:   {int(files['count']) if files else 0}")
        print(f"  Classes: {int(classes['count']) if classes else 0}")
        print(f"  Methods: {int(methods['count']) if methods else 0}")
        print(f"  Edges (CALLS):   {int(calls['count']) if calls else 0}")
        print(f"  Edges (IMPORTS): {int(imports['count']) if imports else 0}")
        return 0
    finally:
        driver.close()


def _run_reset(repo_id: str) -> int:
    target = f"repo '{repo_id}'" if repo_id else "ALL nodes"
    confirmation = input(f"This will delete {target} in Neo4j. Type 'yes' to confirm: ")
    if confirmation.strip() != "yes":
        print("[graphrag] Reset cancelled.")
        return 0

    driver = _build_driver()
    try:
        with driver.session() as session:
            if repo_id:
                session.run("MATCH (n {repo_id: $repo_id}) DETACH DELETE n", repo_id=repo_id)
            else:
                session.run("MATCH (n) DETACH DELETE n")
        print("[graphrag] Neo4j graph reset complete.")
        return 0
    finally:
        driver.close()


def main() -> None:
    """Entry point for the graphrag CLI."""
    load_dotenv()

    parser = argparse.ArgumentParser(prog="graphrag", description="Polyglot GraphRAG CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest_parser = subparsers.add_parser("ingest", help="Ingest a repository into Neo4j")
    ingest_parser.add_argument("repo_path", help="Path to repository root")
    ingest_parser.add_argument("--workers", type=int, default=4, help="Parse worker count")
    ingest_parser.add_argument("--repo-id", default=_env("REPO_ID", "default"), help="Repository namespace id")
    ingest_parser.add_argument("--quiet", action="store_true", help="Suppress per-file progress output")

    status_parser = subparsers.add_parser("status", help="Show graph statistics")
    status_parser.add_argument("--repo-id", default="", help="Repository namespace id filter")

    reset_parser = subparsers.add_parser("reset", help="Delete graph data")
    reset_parser.add_argument("--repo-id", default="", help="Repository namespace id filter")

    args = parser.parse_args()
    if args.command == "ingest":
        raise SystemExit(_run_ingest(args))
    if args.command == "status":
        raise SystemExit(_run_status(args.repo_id))
    if args.command == "reset":
        raise SystemExit(_run_reset(args.repo_id))
    raise SystemExit(2)


if __name__ == "__main__":
    main()
