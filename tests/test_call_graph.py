import os
from collections.abc import Generator

import pytest
from dotenv import load_dotenv
from neo4j import Driver, GraphDatabase

from graphrag.graph.repo_index import RepoIndex
from graphrag.graph.writer import Neo4jWriter
from graphrag.parser.factory import parse_file

load_dotenv()

SAMPLE_FILE = "tests/fixtures/sample.py"
SERVICE_FILE = "tests/fixtures/service.py"


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
        pytest.skip(f"Neo4j is not reachable for call graph test: {exc}")

    with driver.session() as session:
        session.run(
            """
            MATCH (n)
            WHERE n.file IN $files
              OR n.path IN $paths
              OR n.fqn STARTS WITH 'tests.fixtures.sample'
              OR n.fqn STARTS WITH 'tests.fixtures.service'
              OR n.name IN ['os', 'pathlib']
            DETACH DELETE n
            """,
            files=[SAMPLE_FILE, SERVICE_FILE],
            paths=["tests/fixtures", SAMPLE_FILE, SERVICE_FILE],
        )
    yield driver
    with driver.session() as session:
        session.run(
            """
            MATCH (n)
            WHERE n.file IN $files
              OR n.path IN $paths
              OR n.fqn STARTS WITH 'tests.fixtures.sample'
              OR n.fqn STARTS WITH 'tests.fixtures.service'
              OR n.name IN ['os', 'pathlib']
            DETACH DELETE n
            """,
            files=[SAMPLE_FILE, SERVICE_FILE],
            paths=["tests/fixtures", SAMPLE_FILE, SERVICE_FILE],
        )
    driver.close()


@pytest.fixture
def writer() -> Generator[Neo4jWriter, None, None]:
    writer_instance = Neo4jWriter(
        uri=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        username=os.getenv("NEO4J_USERNAME", "neo4j"),
        password=os.getenv("NEO4J_PASSWORD", "neo4j_password"),
        repo_index=RepoIndex(),
    )
    yield writer_instance
    writer_instance.close()


def _count_call_edges(driver: Driver) -> int:
    with driver.session() as session:
        record = session.run("MATCH (:Method)-[r:CALLS]->(:Method) RETURN count(r) AS count").single()
    return int(record["count"]) if record is not None else 0


def test_within_file_call_resolution(neo4j_driver: Driver, writer: Neo4jWriter) -> None:
    writer.ingest_file(parse_file(SAMPLE_FILE))
    with neo4j_driver.session() as session:
        record = session.run(
            """
            MATCH (:Method {fqn: $caller})-[r:CALLS]->(:Method {fqn: $callee})
            RETURN r.confidence AS confidence, r.resolved AS resolved
            """,
            caller="tests.fixtures.sample.Alpha.method_two",
            callee="tests.fixtures.sample.Alpha.method_one",
        ).single()
    assert record is not None
    assert float(record["confidence"]) >= 0.9
    assert bool(record["resolved"]) is True


def test_top_level_function_call_resolution(neo4j_driver: Driver, writer: Neo4jWriter) -> None:
    writer.ingest_file(parse_file(SAMPLE_FILE))
    with neo4j_driver.session() as session:
        record = session.run(
            """
            MATCH (:Method {fqn: $caller})-[r:CALLS]->(:Method {fqn: $callee})
            RETURN r.confidence AS confidence, r.resolved AS resolved
            """,
            caller="tests.fixtures.sample.Alpha.method_one",
            callee="tests.fixtures.sample.top_level_one",
        ).single()
    assert record is not None
    assert float(record["confidence"]) >= 0.9
    assert bool(record["resolved"]) is True


def test_self_dot_call_resolution(neo4j_driver: Driver, writer: Neo4jWriter) -> None:
    writer.ingest_file(parse_file(SAMPLE_FILE))
    with neo4j_driver.session() as session:
        record = session.run(
            """
            MATCH (:Method {fqn: $caller})-[r:CALLS]->(:Method {fqn: $callee})
            RETURN r.confidence AS confidence, r.resolved AS resolved
            """,
            caller="tests.fixtures.sample.Beta.stop",
            callee="tests.fixtures.sample.Beta.run",
        ).single()
    assert record is not None
    assert float(record["confidence"]) >= 0.9
    assert bool(record["resolved"]) is True


def test_cross_file_call_resolution(neo4j_driver: Driver, writer: Neo4jWriter) -> None:
    writer.ingest_file(parse_file(SAMPLE_FILE))
    writer.ingest_file(parse_file(SERVICE_FILE))
    with neo4j_driver.session() as session:
        record = session.run(
            """
            MATCH (:Method {fqn: $caller})-[r:CALLS]->(:Method {fqn: $callee})
            RETURN r.confidence AS confidence, r.resolved AS resolved
            """,
            caller="tests.fixtures.service.Service.process",
            callee="tests.fixtures.sample.top_level_one",
        ).single()
    assert record is not None
    assert bool(record["resolved"]) is True
    assert float(record["confidence"]) >= 0.7


def test_external_library_call_not_unresolved(neo4j_driver: Driver, writer: Neo4jWriter) -> None:
    writer.ingest_file(parse_file(SAMPLE_FILE))
    with neo4j_driver.session() as session:
        record = session.run(
            """
            MATCH (:Method {fqn: $caller})-[r:CALLS]->(:Method {fqn: $callee})
            RETURN r.resolved AS resolved, r.confidence AS confidence
            """,
            caller="tests.fixtures.sample.Beta.run",
            callee="os.path.basename",
        ).single()
        unresolved = session.run(
            "MATCH (m:Method) WHERE m.fqn STARTS WITH 'unresolved.os' RETURN count(m) AS count"
        ).single()
    assert record is not None
    assert bool(record["resolved"]) is True
    assert float(record["confidence"]) == 0.7
    assert unresolved is not None and int(unresolved["count"]) == 0


def test_call_edges_are_idempotent(neo4j_driver: Driver, writer: Neo4jWriter) -> None:
    parsed = parse_file(SAMPLE_FILE)
    writer.ingest_file(parsed)
    first_edges = _count_call_edges(neo4j_driver)
    writer.ingest_file(parsed)
    second_edges = _count_call_edges(neo4j_driver)
    assert first_edges == second_edges
