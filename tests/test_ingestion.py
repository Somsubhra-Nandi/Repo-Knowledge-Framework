import os

import pytest
from dotenv import load_dotenv
from neo4j import GraphDatabase

from graphrag.graph.writer import Neo4jWriter
from graphrag.parser.factory import parse_file

load_dotenv()

TEST_FILE_PATH = "tests/fixtures/sample.py"
TEST_FOLDER_PATH = "tests/fixtures"
ALPHA_CLASS_FQN = "tests.fixtures.sample.Alpha"
ALPHA_METHOD_FQN = "tests.fixtures.sample.Alpha.method_one"
TOP_LEVEL_METHOD_FQN = "tests.fixtures.sample.top_level_one"


@pytest.fixture
def neo4j_driver():
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    username = os.getenv("NEO4J_USERNAME", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "neo4j_password")
    driver = GraphDatabase.driver(uri, auth=(username, password))
    try:
        driver.verify_connectivity()
    except Exception as exc:  # noqa: BLE001
        driver.close()
        pytest.skip(f"Neo4j is not reachable for ingestion test: {exc}")

    with driver.session() as session:
        session.run(
            """
            MATCH (n)
            WHERE n.file = $file_path
              OR n.path = $file_path
              OR n.path = $folder_path
              OR n.fqn STARTS WITH 'tests.fixtures.sample'
            DETACH DELETE n
            """,
            file_path=TEST_FILE_PATH,
            folder_path=TEST_FOLDER_PATH,
        )
    yield driver
    with driver.session() as session:
        session.run(
            """
            MATCH (n)
            WHERE n.file = $file_path
              OR n.path = $file_path
              OR n.path = $folder_path
              OR n.fqn STARTS WITH 'tests.fixtures.sample'
            DETACH DELETE n
            """,
            file_path=TEST_FILE_PATH,
            folder_path=TEST_FOLDER_PATH,
        )
    driver.close()


def _count_nodes(driver) -> int:
    with driver.session() as session:
        record = session.run("MATCH (n) RETURN count(n) AS count").single()
    return int(record["count"]) if record is not None else 0


def test_ingest_file_writes_full_hierarchy_and_is_idempotent(neo4j_driver) -> None:
    parsed_file = parse_file(TEST_FILE_PATH)

    writer = Neo4jWriter(
        uri=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        username=os.getenv("NEO4J_USERNAME", "neo4j"),
        password=os.getenv("NEO4J_PASSWORD", "neo4j_password"),
    )
    try:
        writer.ingest_file(parsed_file)
        first_count = _count_nodes(neo4j_driver)

        with neo4j_driver.session() as session:
            folder_exists = session.run(
                "MATCH (:Folder {name: 'fixtures'}) RETURN count(*) AS count"
            ).single()
            assert folder_exists is not None and int(folder_exists["count"]) >= 1

            file_exists = session.run(
                "MATCH (:File {path: $path}) RETURN count(*) AS count",
                path=TEST_FILE_PATH,
            ).single()
            assert file_exists is not None and int(file_exists["count"]) == 1

            folder_contains_file = session.run(
                """
                MATCH (:Folder {path: $folder_path})-[:CONTAINS]->(:File {path: $file_path})
                RETURN count(*) AS count
                """,
                folder_path=TEST_FOLDER_PATH,
                file_path=TEST_FILE_PATH,
            ).single()
            assert folder_contains_file is not None and int(folder_contains_file["count"]) == 1

            class_exists = session.run(
                "MATCH (:Class {fqn: $fqn}) RETURN count(*) AS count",
                fqn=ALPHA_CLASS_FQN,
            ).single()
            assert class_exists is not None and int(class_exists["count"]) == 1

            file_contains_class = session.run(
                """
                MATCH (:File {path: $file_path})-[:CONTAINS]->(:Class {fqn: $fqn})
                RETURN count(*) AS count
                """,
                file_path=TEST_FILE_PATH,
                fqn=ALPHA_CLASS_FQN,
            ).single()
            assert file_contains_class is not None and int(file_contains_class["count"]) == 1

            method_exists = session.run(
                "MATCH (:Method {fqn: $fqn}) RETURN count(*) AS count",
                fqn=ALPHA_METHOD_FQN,
            ).single()
            assert method_exists is not None and int(method_exists["count"]) == 1

            class_contains_method = session.run(
                """
                MATCH (:Class {fqn: $class_fqn})-[:CONTAINS]->(:Method {fqn: $method_fqn})
                RETURN count(*) AS count
                """,
                class_fqn=ALPHA_CLASS_FQN,
                method_fqn=ALPHA_METHOD_FQN,
            ).single()
            assert class_contains_method is not None and int(class_contains_method["count"]) == 1

            top_level_method_exists = session.run(
                "MATCH (:Method {fqn: $fqn}) RETURN count(*) AS count",
                fqn=TOP_LEVEL_METHOD_FQN,
            ).single()
            assert top_level_method_exists is not None and int(top_level_method_exists["count"]) == 1

            file_contains_top_level = session.run(
                """
                MATCH (:File {path: $file_path})-[:CONTAINS]->(:Method {fqn: $method_fqn})
                RETURN count(*) AS count
                """,
                file_path=TEST_FILE_PATH,
                method_fqn=TOP_LEVEL_METHOD_FQN,
            ).single()
            assert file_contains_top_level is not None and int(file_contains_top_level["count"]) == 1

            method_metadata = session.run(
                """
                MATCH (m:Method {fqn: $fqn})
                RETURN m.source_code AS source_code, m.signature AS signature, m.line AS line
                """,
                fqn=ALPHA_METHOD_FQN,
            ).single()
            assert method_metadata is not None
            assert method_metadata["source_code"] != ""
            assert method_metadata["signature"] != ""
            assert int(method_metadata["line"]) == 6

            package_exists = session.run(
                """
                MATCH (p:Package)
                WHERE p.name IN ['os', 'pathlib']
                RETURN count(*) AS count
                """
            ).single()
            assert package_exists is not None and int(package_exists["count"]) >= 1

            imports_edge = session.run(
                """
                MATCH (:File {path: $file_path})-[:IMPORTS]->(:Package)
                RETURN count(*) AS count
                """,
                file_path=TEST_FILE_PATH,
            ).single()
            assert imports_edge is not None and int(imports_edge["count"]) >= 1

        writer.ingest_file(parsed_file)
        second_count = _count_nodes(neo4j_driver)
        assert first_count == second_count
    finally:
        writer.close()
