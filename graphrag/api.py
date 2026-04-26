import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, status
from fastapi.responses import JSONResponse
from neo4j import GraphDatabase

from graphrag.graph.connection import verify_neo4j_connection
from graphrag.graph.queries import create_indexes

load_dotenv()


@asynccontextmanager
async def lifespan(_: FastAPI):
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    username = os.getenv("NEO4J_USERNAME", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "neo4j_password")
    driver = GraphDatabase.driver(uri, auth=(username, password))
    try:
        create_indexes(driver)
        yield
    finally:
        driver.close()


app = FastAPI(title="graphrag-mcp", lifespan=lifespan)


@app.get("/health")
def health() -> JSONResponse:
    ok, detail = verify_neo4j_connection()
    if ok:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"status": "ok", "neo4j": "connected"},
        )
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"status": "degraded", "neo4j": "unreachable", "detail": detail},
    )
