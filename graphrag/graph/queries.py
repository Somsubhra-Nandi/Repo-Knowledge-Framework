"""Neo4j query helpers."""

from neo4j import Driver


def create_indexes(driver: Driver) -> None:
    """Create all required indexes and constraints if absent."""
    statements = [
        "CREATE INDEX IF NOT EXISTS FOR (f:File) ON (f.path)",
        "CREATE INDEX IF NOT EXISTS FOR (c:Class) ON (c.fqn)",
        "CREATE INDEX IF NOT EXISTS FOR (m:Method) ON (m.fqn)",
        "CREATE INDEX IF NOT EXISTS FOR (f:Folder) ON (f.path)",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (m:Method) REQUIRE m.fqn IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (c:Class) REQUIRE c.fqn IS UNIQUE",
    ]
    with driver.session() as session:
        for statement in statements:
            session.run(statement)

