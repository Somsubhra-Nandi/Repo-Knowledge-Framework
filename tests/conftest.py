import os
from collections.abc import Generator

import pytest
from dotenv import load_dotenv
from neo4j import Driver

load_dotenv()


def _is_neo4j_reachable() -> bool:
    try:
        from neo4j import GraphDatabase

        driver = GraphDatabase.driver(
            os.getenv("NEO4J_URI", "bolt://localhost:7687"),
            auth=(
                os.getenv("NEO4J_USERNAME", "neo4j"),
                os.getenv("NEO4J_PASSWORD", "neo4j_password"),
            ),
        )
        driver.verify_connectivity()
        driver.close()
        return True
    except Exception:  # noqa: BLE001
        return False


@pytest.fixture(scope="session")
def neo4j_driver() -> Generator[Driver, None, None]:
    if not _is_neo4j_reachable():
        pytest.skip("Neo4j not reachable - skipping integration test")

    from neo4j import GraphDatabase

    driver = GraphDatabase.driver(
        os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        auth=(
            os.getenv("NEO4J_USERNAME", "neo4j"),
            os.getenv("NEO4J_PASSWORD", "neo4j_password"),
        ),
    )
    yield driver
    driver.close()
