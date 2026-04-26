import os
from pathlib import Path
from typing import Generator

import pytest
from dotenv import load_dotenv
from neo4j import Driver, GraphDatabase

from graphrag.ingestion.pipeline import IngestionPipeline
from graphrag.ingestion.walker import RepoWalker

load_dotenv()

MINI_REPO_PATH = "tests/fixtures/mini_repo"


@pytest.fixture
def neo4j_driver() -> Generator[Driver, None, None]:
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    username = os.getenv("NEO4J_USERNAME", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "neo4j_password")
    driver = GraphDatabase.driver(uri, auth=(username, password))
    try:
        driver.verify_connectivity()
    except Exception as exc:  # noqa: BLE001
        driver.close()
        pytest.skip(f"Neo4j is not reachable for ingestion pipeline test: {exc}")

    with driver.session() as session:
        session.run(
            """
            MATCH (n)
            WHERE (n.path IS NOT NULL AND n.path CONTAINS "mini_repo")
               OR (n.file IS NOT NULL AND n.file CONTAINS "mini_repo")
            DETACH DELETE n
            """
        )
    yield driver
    with driver.session() as session:
        session.run(
            """
            MATCH (n)
            WHERE (n.path IS NOT NULL AND n.path CONTAINS "mini_repo")
               OR (n.file IS NOT NULL AND n.file CONTAINS "mini_repo")
            DETACH DELETE n
            """
        )
    driver.close()


def _build_pipeline() -> IngestionPipeline:
    return IngestionPipeline(
        neo4j_uri=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        neo4j_username=os.getenv("NEO4J_USERNAME", "neo4j"),
        neo4j_password=os.getenv("NEO4J_PASSWORD", "neo4j_password"),
        workers=4,
    )


def test_walker_discovers_correct_files() -> None:
    """Walker finds main.py, utils.py, app.ts but not ignored_file.py or cache.py."""
    walker = RepoWalker(MINI_REPO_PATH)
    discovered = walker.discover()
    paths = {Path(p).name for p in discovered}
    assert "main.py" in paths
    assert "utils.py" in paths
    assert "app.ts" in paths
    assert "ignored_file.py" not in paths
    assert "cache.py" not in paths


def test_walker_returns_sorted_paths() -> None:
    """Walker output is deterministically sorted."""
    walker = RepoWalker(MINI_REPO_PATH)
    discovered = walker.discover()
    assert discovered == sorted(discovered)


def test_walker_skips_default_dirs() -> None:
    """Walker skips default noisy directories."""
    walker = RepoWalker(MINI_REPO_PATH)
    discovered = walker.discover()
    assert not any("__pycache__" in p for p in discovered)
    assert not any("node_modules" in p for p in discovered)


def test_pipeline_ingests_mini_repo(neo4j_driver: Driver) -> None:
    """Full pipeline run on mini_repo produces expected nodes."""
    result = _build_pipeline().run(MINI_REPO_PATH)
    assert result.failed == 0

    with neo4j_driver.session() as session:
        main_file = session.run(
            """
            MATCH (f:File)
            WHERE f.path CONTAINS "mini_repo" AND f.path ENDS WITH "/main.py"
            RETURN count(f) AS count
            """
        ).single()
        utils_file = session.run(
            """
            MATCH (f:File)
            WHERE f.path CONTAINS "mini_repo" AND f.path ENDS WITH "/utils.py"
            RETURN count(f) AS count
            """
        ).single()
        app_file = session.run(
            """
            MATCH (f:File)
            WHERE f.path CONTAINS "mini_repo" AND f.path ENDS WITH "/app.ts"
            RETURN count(f) AS count
            """
        ).single()
        ignored_file = session.run(
            """
            MATCH (f:File)
            WHERE f.path CONTAINS "mini_repo" AND f.path ENDS WITH "/ignored_file.py"
            RETURN count(f) AS count
            """
        ).single()
        add_numbers = session.run(
            """
            MATCH (m:Method {name: "add_numbers"})
            WHERE m.file CONTAINS "mini_repo"
            RETURN count(m) AS count
            """
        ).single()
        app_component = session.run(
            """
            MATCH (c:Class {name: "AppComponent"})
            WHERE c.file CONTAINS "mini_repo"
            RETURN count(c) AS count
            """
        ).single()

    assert main_file is not None and int(main_file["count"]) == 1
    assert utils_file is not None and int(utils_file["count"]) == 1
    assert app_file is not None and int(app_file["count"]) == 1
    assert ignored_file is not None and int(ignored_file["count"]) == 0
    assert add_numbers is not None and int(add_numbers["count"]) == 1
    assert app_component is not None and int(app_component["count"]) == 1


def test_pipeline_two_pass_resolves_cross_file_calls(neo4j_driver: Driver) -> None:
    """main.py run -> add_numbers call resolves after two-pass registration."""
    result = _build_pipeline().run(MINI_REPO_PATH)
    assert result.failed == 0

    with neo4j_driver.session() as session:
        call_edge = session.run(
            """
            MATCH (:Method {name: "run"})-[r:CALLS]->(:Method {name: "add_numbers"})
            RETURN r.resolved AS resolved
            LIMIT 1
            """
        ).single()

    assert call_edge is not None
    assert bool(call_edge["resolved"]) is True


def test_pipeline_checksum_skips_unchanged_files(neo4j_driver: Driver) -> None:
    """Second run should skip all unchanged parseable files."""
    first = _build_pipeline().run(MINI_REPO_PATH)
    assert first.failed == 0
    second = _build_pipeline().run(MINI_REPO_PATH)
    assert second.skipped == second.total_files
    assert second.parsed == 0


def test_ingestion_result_has_no_failures(neo4j_driver: Driver) -> None:
    """Pipeline completes with no errors on mini_repo."""
    result = _build_pipeline().run(MINI_REPO_PATH)
    assert result.failed == 0
    assert result.errors == []
