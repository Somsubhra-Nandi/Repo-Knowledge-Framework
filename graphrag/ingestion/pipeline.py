"""Bulk ingestion pipeline orchestration."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
import sys
import threading
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
        repo_id: str = "default",
        quiet: bool = False,
    ) -> None:
        self._uri = neo4j_uri
        self._username = neo4j_username
        self._password = neo4j_password
        self._workers = workers
        self._repo_id = repo_id
        self._quiet = quiet

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
            stored_checksum = get_stored_checksum(
                self._uri,
                self._username,
                self._password,
                file_path,
                self._repo_id,
            )
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
            parse_counter = 0
            parse_lock = threading.Lock()
            interactive = sys.stdout.isatty()

            def _parse_with_timing(path: str) -> tuple[ParsedFile, float]:
                started = perf_counter()
                parsed = parse_file(path, self._repo_id)
                return parsed, perf_counter() - started

            with ThreadPoolExecutor(max_workers=self._workers) as executor:
                futures = {
                    executor.submit(_parse_with_timing, file_path): file_path for file_path in to_parse
                }
                for future in as_completed(futures):
                    file_path = futures[future]
                    relative_path = Path(file_path).resolve().relative_to(Path(repo_root).resolve()).as_posix()
                    try:
                        parsed, elapsed = future.result()
                        parsed_files.append(parsed)
                        with parse_lock:
                            parse_counter += 1
                            current = parse_counter
                        if not self._quiet:
                            message = (
                                f"[graphrag] Parsed  ({current}/{len(to_parse)}) "
                                f"{relative_path}  [{elapsed:.3f}s]"
                            )
                            end_value = "\r" if interactive else "\n"
                            print(message, end=end_value, flush=True)
                    except Exception as exc:  # noqa: BLE001
                        errors.append(f"{file_path}: {exc}")
                        with parse_lock:
                            parse_counter += 1
                            current = parse_counter
                        if not self._quiet:
                            print(
                                f"[graphrag] FAILED  ({current}/{len(to_parse)}) {relative_path}  {exc}",
                                flush=True,
                            )
            if interactive and not self._quiet:
                print()

        repo_index = RepoIndex()
        for parsed in parsed_files:
            repo_index.register_file(parsed)

        print("[graphrag] Ingesting into Neo4j...")
        writer = Neo4jWriter(
            uri=self._uri,
            username=self._username,
            password=self._password,
            repo_index=repo_index,
            repo_id=self._repo_id,
        )

        ingested = 0
        try:
            for index, parsed in enumerate(parsed_files, start=1):
                try:
                    ingest_started = perf_counter()
                    writer.ingest_file(parsed)
                    ingested += 1
                    if not self._quiet:
                        relative_path = Path(parsed.path).resolve().relative_to(Path(repo_root).resolve()).as_posix()
                        elapsed = perf_counter() - ingest_started
                        print(
                            f"[graphrag] Ingested ({index}/{len(parsed_files)}) {relative_path} "
                            f"-> {len(parsed.classes)} classes, {len(parsed.methods)} methods "
                            f"[{elapsed:.3f}s]"
                        )
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"{parsed.path}: {exc}")
        finally:
            writer.close()

        print("[graphrag] Stitching frontend calls to backend endpoints...")
        stitcher = RouteStitcher(
            uri=self._uri,
            username=self._username,
            password=self._password,
            repo_id=self._repo_id,
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
    repo_id: str,
) -> str | None:
    """Return stored checksum for a file path, or None if not yet ingested."""
    driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_username, neo4j_password))
    try:
        with driver.session() as session:
            record = session.run(
                "MATCH (f:File {path: $path, repo_id: $repo_id}) RETURN f.checksum AS checksum",
                path=file_path,
                repo_id=repo_id,
            ).single()
            if record is None:
                return None
            checksum = record.get("checksum")
            return checksum if isinstance(checksum, str) else None
    finally:
        driver.close()
