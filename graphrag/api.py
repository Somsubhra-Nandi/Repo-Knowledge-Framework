from fastapi import FastAPI, status
from fastapi.responses import JSONResponse

from graphrag.graph.connection import verify_neo4j_connection

app = FastAPI(title="graphrag-mcp")


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
