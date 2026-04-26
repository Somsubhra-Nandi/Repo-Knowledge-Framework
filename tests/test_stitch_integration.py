import os
from collections.abc import Generator

import pytest
from dotenv import load_dotenv
from neo4j import Driver, GraphDatabase

from graphrag.graph.stitch import RouteStitcher, StitchResult
from graphrag.graph.writer import Neo4jWriter
from graphrag.parser.factory import parse_file

load_dotenv()

BACKEND_MAIN = "tests/fixtures/fullstack_app/backend/main.py"
BACKEND_USERS = "tests/fixtures/fullstack_app/backend/users.py"
FRONTEND_COMPONENT = "tests/fixtures/fullstack_app/frontend/UserComponent.tsx"
FRONTEND_API = "tests/fixtures/fullstack_app/frontend/api.ts"


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
        pytest.skip(f"Neo4j is not reachable for stitch integration test: {exc}")

    with driver.session() as session:
        session.run(
            """
            MATCH (n)
            WHERE (n.file IS NOT NULL AND n.file CONTAINS "fullstack_app")
               OR (n.source_file IS NOT NULL AND n.source_file CONTAINS "fullstack_app")
               OR (n.path IS NOT NULL AND n.path CONTAINS "/api/users")
            DETACH DELETE n
            """
        )
    yield driver
    with driver.session() as session:
        session.run(
            """
            MATCH (n)
            WHERE (n.file IS NOT NULL AND n.file CONTAINS "fullstack_app")
               OR (n.source_file IS NOT NULL AND n.source_file CONTAINS "fullstack_app")
               OR (n.path IS NOT NULL AND n.path CONTAINS "/api/users")
            DETACH DELETE n
            """
        )
    driver.close()


def _new_writer() -> Neo4jWriter:
    return Neo4jWriter(
        uri=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        username=os.getenv("NEO4J_USERNAME", "neo4j"),
        password=os.getenv("NEO4J_PASSWORD", "neo4j_password"),
    )


def _run_stitch() -> StitchResult:
    stitcher = RouteStitcher(
        uri=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        username=os.getenv("NEO4J_USERNAME", "neo4j"),
        password=os.getenv("NEO4J_PASSWORD", "neo4j_password"),
    )
    try:
        return stitcher.stitch()
    finally:
        stitcher.close()


def test_exact_match_creates_routes_to_edge(neo4j_driver: Driver) -> None:
    writer = _new_writer()
    try:
        writer.ingest_file(parse_file(BACKEND_MAIN))
        writer.ingest_file(parse_file(FRONTEND_API))
    finally:
        writer.close()

    _run_stitch()
    with neo4j_driver.session() as session:
        record = session.run(
            """
            MATCH (rc:RouteCall {path:"/api/users", http_method:"GET"})
                  -[r:ROUTES_TO]->
                  (e:Endpoint {path:"/api/users", http_method:"GET"})
            RETURN r.match_type AS match_type, r.confidence AS confidence
            LIMIT 1
            """
        ).single()
    assert record is not None
    assert record["match_type"] == "exact"
    assert float(record["confidence"]) == 1.0


def test_parameterized_match_creates_routes_to_edge(neo4j_driver: Driver) -> None:
    writer = _new_writer()
    try:
        writer.ingest_file(parse_file(BACKEND_MAIN))
        writer.ingest_file(parse_file(FRONTEND_API))
    finally:
        writer.close()

    _run_stitch()
    with neo4j_driver.session() as session:
        record = session.run(
            """
            MATCH (rc:RouteCall)-[r:ROUTES_TO]->(e:Endpoint)
            WHERE e.path = "/api/users/{user_id}"
            RETURN r.match_type AS match_type, r.confidence AS confidence
            LIMIT 1
            """
        ).single()
    assert record is not None
    assert record["match_type"] == "parameterized"
    assert float(record["confidence"]) == 0.7


def test_full_chain_traversable(neo4j_driver: Driver) -> None:
    writer = _new_writer()
    try:
        writer.ingest_file(parse_file(BACKEND_MAIN))
        writer.ingest_file(parse_file(BACKEND_USERS))
        writer.ingest_file(parse_file(FRONTEND_COMPONENT))
        writer.ingest_file(parse_file(FRONTEND_API))
    finally:
        writer.close()

    _run_stitch()
    with neo4j_driver.session() as session:
        record = session.run(
            """
            MATCH path = (m:Method {name:"loadUsers"})
                         -[:MAKES_CALL]->(:RouteCall)
                         -[:ROUTES_TO]->(:Endpoint)
                         <-[:HANDLES]-(handler:Method)
            RETURN handler.name AS handler_name
            LIMIT 1
            """
        ).single()
    assert record is not None
    assert record["handler_name"] == "get_users"


def test_stitch_result_counts_are_correct(neo4j_driver: Driver) -> None:
    writer = _new_writer()
    try:
        writer.ingest_file(parse_file(BACKEND_MAIN))
        writer.ingest_file(parse_file(FRONTEND_API))
    finally:
        writer.close()

    stitch_result = _run_stitch()
    assert stitch_result.exact_matches >= 2
    assert stitch_result.total_edges_created >= 2


def test_stitch_is_idempotent(neo4j_driver: Driver) -> None:
    writer = _new_writer()
    try:
        writer.ingest_file(parse_file(BACKEND_MAIN))
        writer.ingest_file(parse_file(FRONTEND_API))
    finally:
        writer.close()

    _run_stitch()
    with neo4j_driver.session() as session:
        first_count = session.run("MATCH ()-[r:ROUTES_TO]->() RETURN count(r) AS count").single()
    _run_stitch()
    with neo4j_driver.session() as session:
        second_count = session.run("MATCH ()-[r:ROUTES_TO]->() RETURN count(r) AS count").single()

    assert first_count is not None
    assert second_count is not None
    assert int(first_count["count"]) == int(second_count["count"])


def test_no_cross_method_matches(neo4j_driver: Driver) -> None:
    writer = _new_writer()
    try:
        writer.ingest_file(parse_file(BACKEND_MAIN))
        writer.ingest_file(parse_file(FRONTEND_COMPONENT))
    finally:
        writer.close()

    _run_stitch()
    with neo4j_driver.session() as session:
        cross_method = session.run(
            """
            MATCH (rc:RouteCall)-[:ROUTES_TO]->(e:Endpoint)
            WHERE rc.http_method = "POST" AND e.http_method = "GET"
            RETURN count(*) AS count
            """
        ).single()
    assert cross_method is not None
    assert int(cross_method["count"]) == 0
