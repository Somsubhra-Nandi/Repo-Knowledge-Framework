import os
from collections.abc import Generator

import pytest
from dotenv import load_dotenv
from neo4j import Driver, GraphDatabase

from graphrag.graph.writer import Neo4jWriter
from graphrag.parser.factory import parse_file

load_dotenv()

FASTAPI_FILE = "tests/fixtures/fastapi_app.py"
JAVA_FILE = "tests/fixtures/UserController.java"


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
        pytest.skip(f"Neo4j is not reachable for endpoint ingestion test: {exc}")

    with driver.session() as session:
        session.run(
            """
            MATCH (n)
            WHERE (n.file IS NOT NULL AND (n.file CONTAINS "fastapi_app" OR n.file CONTAINS "UserController"))
               OR (n.path IS NOT NULL AND (n.path CONTAINS "/health" OR n.path CONTAINS "/users"))
            DETACH DELETE n
            """
        )
    yield driver
    with driver.session() as session:
        session.run(
            """
            MATCH (n)
            WHERE (n.file IS NOT NULL AND (n.file CONTAINS "fastapi_app" OR n.file CONTAINS "UserController"))
               OR (n.path IS NOT NULL AND (n.path CONTAINS "/health" OR n.path CONTAINS "/users"))
            DETACH DELETE n
            """
        )
    driver.close()


def _build_writer() -> Neo4jWriter:
    return Neo4jWriter(
        uri=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        username=os.getenv("NEO4J_USERNAME", "neo4j"),
        password=os.getenv("NEO4J_PASSWORD", "neo4j_password"),
    )


def test_endpoints_written_to_neo4j(neo4j_driver: Driver) -> None:
    writer = _build_writer()
    try:
        writer.ingest_file(parse_file(FASTAPI_FILE))
    finally:
        writer.close()

    with neo4j_driver.session() as session:
        health = session.run(
            "MATCH (e:Endpoint {path: '/health', http_method: 'GET'}) RETURN count(e) AS count"
        ).single()
        users = session.run(
            "MATCH (e:Endpoint {path: '/users', http_method: 'POST'}) RETURN count(e) AS count"
        ).single()
        handles = session.run(
            "MATCH (:Method)-[:HANDLES]->(:Endpoint) RETURN count(*) AS count"
        ).single()

    assert health is not None and int(health["count"]) == 1
    assert users is not None and int(users["count"]) == 1
    assert handles is not None and int(handles["count"]) >= 1


def test_endpoint_handler_fqn_linked(neo4j_driver: Driver) -> None:
    writer = _build_writer()
    try:
        writer.ingest_file(parse_file(FASTAPI_FILE))
    finally:
        writer.close()

    with neo4j_driver.session() as session:
        record = session.run(
            """
            MATCH (m:Method {name: "health_check"})-[:HANDLES]->(e:Endpoint)
            RETURN e.path AS path
            LIMIT 1
            """
        ).single()

    assert record is not None
    assert record["path"] == "/health"


def test_endpoint_merge_is_idempotent(neo4j_driver: Driver) -> None:
    writer = _build_writer()
    try:
        parsed = parse_file(FASTAPI_FILE)
        writer.ingest_file(parsed)
        with neo4j_driver.session() as session:
            first_count_record = session.run("MATCH (e:Endpoint) RETURN count(e) AS count").single()
        writer.ingest_file(parsed)
        with neo4j_driver.session() as session:
            second_count_record = session.run("MATCH (e:Endpoint) RETURN count(e) AS count").single()
    finally:
        writer.close()

    assert first_count_record is not None
    assert second_count_record is not None
    assert int(first_count_record["count"]) == int(second_count_record["count"])


def test_java_endpoints_written_to_neo4j(neo4j_driver: Driver) -> None:
    writer = _build_writer()
    try:
        writer.ingest_file(parse_file(JAVA_FILE))
    finally:
        writer.close()

    with neo4j_driver.session() as session:
        record = session.run(
            """
            MATCH (e:Endpoint)
            WHERE e.file CONTAINS "UserController"
            RETURN count(e) AS count
            """
        ).single()

    assert record is not None
    assert int(record["count"]) >= 2
