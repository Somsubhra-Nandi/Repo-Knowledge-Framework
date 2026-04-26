"""Bulk ingestion pipeline orchestration."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

from neo4j import GraphDatabase

from graphrag.graph.repo_index import RepoIndex
from graphrag.graph.stitch import RouteStitcher
from graphrag.graph.writer import Neo4jWriter
from graphrag.ingestion.walker import RepoWalker
from graphrag.parser.factory import ParsedFile, parse_file


@dataclass
class IngestionResult:
    total_files: int
    parsed: int
    skipped: int
    failed: int
    errors: list[str]
    duration_seconds: float
    routes_stitched: int = 0


class IngestionPipeline:
    """
    Orchestrates parse -> resolve -> ingest for a repository.
    Uses two-pass indexing for cross-file call resolution.
    """

    def __init__(
        self,
        neo4j_uri: str,
        neo4j_username: str,
        neo4j_password: str,
        workers: int = 4,
    ) -> None:
        self._uri = neo4j_uri
        self._username = neo4j_username
        self._password = neo4j_password
        self._workers = workers

    def run(self, repo_root: str) -> IngestionResult:
        """
        Run ingestion for a repository root and return execution stats.
        """
        started_at = perf_counter()
        errors: list[str] = []

        print(f"[graphrag] Discovering files in {repo_root}...")
        discovered_files = RepoWalker(repo_root).discover()

        to_parse: list[str] = []
        skipped = 0
        for file_path in discovered_files:
            checksum = self._compute_file_checksum(file_path)
            stored_checksum = get_stored_checksum(self._uri, self._username, self._password, file_path)
            if stored_checksum is not None and stored_checksum == checksum:
                skipped += 1
                continue
            to_parse.append(file_path)

        print(
            f"[graphrag] Found {len(discovered_files)} files "
            f"({len(to_parse)} to parse, {skipped} skipped - unchanged)"
        )
        print(f"[graphrag] Parsing files... ({self._workers} workers)")

        parsed_files: list[ParsedFile] = []
        if to_parse:
            with ThreadPoolExecutor(max_workers=self._workers) as executor:
                futures = {executor.submit(parse_file, file_path): file_path for file_path in to_parse}
                for future in as_completed(futures):
                    file_path = futures[future]
                    try:
                        parsed_files.append(future.result())
                    except Exception as exc:  # noqa: BLE001
                        errors.append(f"{file_path}: {exc}")

        repo_index = RepoIndex()
        for parsed in parsed_files:
            repo_index.register_file(parsed)

        print("[graphrag] Ingesting into Neo4j...")
        writer = Neo4jWriter(
            uri=self._uri,
            username=self._username,
            password=self._password,
            repo_index=repo_index,
        )

        ingested = 0
        try:
            for parsed in parsed_files:
                try:
                    writer.ingest_file(parsed)
                    ingested += 1
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"{parsed.path}: {exc}")
        finally:
            writer.close()

        print("[graphrag] Stitching frontend calls to backend endpoints...")
        stitcher = RouteStitcher(
            uri=self._uri,
            username=self._username,
            password=self._password,
        )
        routes_stitched = 0
        try:
            stitch_result = stitcher.stitch()
            routes_stitched = stitch_result.total_edges_created
            print(
                f"[graphrag] Stitch complete. "
                f"{stitch_result.exact_matches} exact, "
                f"{stitch_result.param_matches} parameterized, "
                f"{stitch_result.unmatched_calls} unmatched"
            )
        finally:
            stitcher.close()

        duration_seconds = perf_counter() - started_at
        failed = len(errors)
        print(
            f"[graphrag] Done. {ingested} parsed, {skipped} skipped, "
            f"{failed} failed in {duration_seconds:.1f}s"
        )
        return IngestionResult(
            total_files=len(discovered_files),
            parsed=ingested,
            skipped=skipped,
            failed=failed,
            errors=errors,
            duration_seconds=duration_seconds,
            routes_stitched=routes_stitched,
        )

    def _compute_file_checksum(self, file_path: str) -> str:
        """Return sha256 checksum for a file."""
        import hashlib

        digest = hashlib.sha256()
        digest.update(Path(file_path).read_bytes())
        return digest.hexdigest()


def get_stored_checksum(
    neo4j_uri: str,
    neo4j_username: str,
    neo4j_password: str,
    file_path: str,
) -> str | None:
    """Return stored checksum for a file path, or None if not yet ingested."""
    driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_username, neo4j_password))
    try:
        with driver.session() as session:
            record = session.run(
                "MATCH (f:File {path: $path}) RETURN f.checksum AS checksum",
                path=file_path,
            ).single()
            if record is None:
                return None
            checksum = record.get("checksum")
            return checksum if isinstance(checksum, str) else None
    finally:
        driver.close()
