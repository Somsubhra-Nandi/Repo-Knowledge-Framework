"""RouteCall -> Endpoint stitching for full-stack graph traversal."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from neo4j import Driver, GraphDatabase

PATH_PARAM_PATTERN = re.compile(r"\$\{[^}]+\}|\{[^}]+\}|:[a-zA-Z_][a-zA-Z0-9_]*|\[[^\]]+\]")


@dataclass
class StitchResult:
    exact_matches: int
    param_matches: int
    unmatched_calls: int
    total_edges_created: int


def _normalize_path_params(path: str) -> str:
    """
    Replace all path parameter segments with a canonical placeholder.
    """
    return PATH_PARAM_PATTERN.sub("{param}", path)


class RouteStitcher:
    """
    Matches RouteCall nodes to Endpoint nodes in Neo4j and creates ROUTES_TO edges.
    """

    def __init__(self, uri: str, username: str, password: str) -> None:
        self._driver: Driver = GraphDatabase.driver(uri, auth=(username, password))

    def close(self) -> None:
        """Close the Neo4j driver."""
        self._driver.close()

    def _match_endpoints(
        self,
        route_call_path: str,
        http_method: str,
        endpoints: list[dict[str, Any]],
    ) -> list[tuple[dict[str, Any], float]]:
        """
        Return list of (endpoint, confidence) tuples.
        confidence: 1.0 exact, 0.7 parameterized
        """
        method = http_method.upper()
        matches: list[tuple[dict[str, Any], float]] = []

        for endpoint in endpoints:
            endpoint_method = str(endpoint.get("http_method", "")).upper()
            if endpoint_method != method:
                continue
            endpoint_path = str(endpoint.get("path", ""))
            if route_call_path == endpoint_path:
                matches.append((endpoint, 1.0))

        if matches:
            return matches

        normalized_route_path = _normalize_path_params(route_call_path)
        for endpoint in endpoints:
            endpoint_method = str(endpoint.get("http_method", "")).upper()
            if endpoint_method != method:
                continue
            endpoint_path = str(endpoint.get("path", ""))
            if normalized_route_path == _normalize_path_params(endpoint_path):
                matches.append((endpoint, 0.7))
        return matches

    def stitch(self) -> StitchResult:
        """Run RouteCall -> Endpoint stitching and return aggregate stats."""
        with self._driver.session() as session:
            route_calls_records = session.run(
                """
                MATCH (rc:RouteCall)
                RETURN rc.path AS path,
                       rc.http_method AS http_method,
                       rc.source_method_fqn AS source_method_fqn,
                       rc.confidence AS confidence
                """
            )
            route_calls = [dict(record) for record in route_calls_records]

            endpoints_records = session.run(
                """
                MATCH (e:Endpoint)
                RETURN e.path AS path,
                       e.http_method AS http_method,
                       e.handler_fqn AS handler_fqn
                """
            )
            endpoints = [dict(record) for record in endpoints_records]

            exact_matches = 0
            param_matches = 0
            unmatched_calls = 0
            total_edges_created = 0

            for route_call in route_calls:
                rc_path = str(route_call.get("path", ""))
                http_method = str(route_call.get("http_method", "")).upper()
                source_method_fqn = str(route_call.get("source_method_fqn", ""))
                candidates = self._match_endpoints(rc_path, http_method, endpoints)
                if not candidates:
                    unmatched_calls += 1
                    continue

                for endpoint, confidence in candidates:
                    match_type = "exact" if confidence == 1.0 else "parameterized"
                    record = session.run(
                        """
                        MATCH (rc:RouteCall {
                            path: $rc_path,
                            http_method: $http_method,
                            source_method_fqn: $source_method_fqn
                        })
                        MATCH (e:Endpoint {path: $endpoint_path, http_method: $http_method})
                        MERGE (rc)-[r:ROUTES_TO]->(e)
                        ON CREATE SET r._new = true
                        SET r.confidence = $confidence,
                            r.match_type = $match_type
                        WITH r, coalesce(r._new, false) AS created
                        REMOVE r._new
                        RETURN created AS created
                        """,
                        rc_path=rc_path,
                        http_method=http_method,
                        source_method_fqn=source_method_fqn,
                        endpoint_path=str(endpoint.get("path", "")),
                        confidence=confidence,
                        match_type=match_type,
                    ).single()
                    created = bool(record["created"]) if record is not None else False
                    if created:
                        total_edges_created += 1
                        if match_type == "exact":
                            exact_matches += 1
                        else:
                            param_matches += 1

        return StitchResult(
            exact_matches=exact_matches,
            param_matches=param_matches,
            unmatched_calls=unmatched_calls,
            total_edges_created=total_edges_created,
        )

