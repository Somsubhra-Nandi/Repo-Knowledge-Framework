"""Neo4j query helpers."""

from neo4j import Driver


def create_indexes(driver: Driver) -> None:
    """Create all required indexes and constraints if absent."""
    statements = [
        "CREATE INDEX IF NOT EXISTS FOR (f:File) ON (f.path)",
        "CREATE INDEX IF NOT EXISTS FOR (f:Folder) ON (f.path)",
        "CREATE INDEX IF NOT EXISTS FOR (e:Endpoint) ON (e.path)",
        "CREATE INDEX IF NOT EXISTS FOR (rc:RouteCall) ON (rc.path)",
        "CREATE INDEX IF NOT EXISTS FOR (n:Method) ON (n.repo_id)",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (m:Method) REQUIRE (m.fqn, m.repo_id) IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (c:Class) REQUIRE (c.fqn, c.repo_id) IS UNIQUE",
    ]
    with driver.session() as session:
        for statement in statements:
            session.run(statement)
