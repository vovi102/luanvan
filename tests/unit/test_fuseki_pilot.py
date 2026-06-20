"""Unit tests for the testable Fuseki EthOn pilot client."""

from __future__ import annotations

import base64
from collections import deque
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

import pytest

from nl2sparql.kg.ontology.fuseki_pilot import (
    FusekiError,
    FusekiPilotClient,
    HttpResponse,
)


class FakeTransport:
    """Record HTTP requests and return queued responses."""

    def __init__(self, *responses: HttpResponse) -> None:
        self.responses = deque(responses)
        self.requests: list[dict[str, Any]] = []

    def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes,
    ) -> HttpResponse:
        """Record one request and return the next response."""
        self.requests.append({"method": method, "url": url, "headers": headers, "body": body})
        return self.responses.popleft()


def make_client(
    transport: FakeTransport,
    *,
    base_url: str = "http://fuseki:3030",
) -> FusekiPilotClient:
    """Create a client with fixed, non-production credentials."""
    return FusekiPilotClient(
        base_url,
        "ethon-pilot",
        "admin",
        "test-password",
        transport=transport,
    )


def test_prepare_existing_dataset_accepts_conflict_then_clears() -> None:
    transport = FakeTransport(HttpResponse(409, b"exists"), HttpResponse(204, b""))
    client = make_client(transport)

    client.prepare_dataset()

    create, clear = transport.requests
    assert (create["method"], create["url"]) == (
        "POST",
        "http://fuseki:3030/$/datasets",
    )
    assert parse_qs(create["body"].decode()) == {
        "dbName": ["ethon-pilot"],
        "dbType": ["mem"],
    }
    assert create["headers"]["Content-Type"] == "application/x-www-form-urlencoded"
    expected_auth = base64.b64encode(b"admin:test-password").decode("ascii")
    assert create["headers"]["Authorization"] == f"Basic {expected_auth}"
    assert (clear["method"], clear["url"]) == (
        "POST",
        "http://fuseki:3030/ethon-pilot/update",
    )
    assert parse_qs(clear["body"].decode()) == {"update": ["DROP ALL"]}
    assert "test-password" not in create["url"]
    assert "test-password" not in create["body"].decode()


def test_prepare_new_dataset_accepts_created_then_clears() -> None:
    transport = FakeTransport(HttpResponse(201, b"created"), HttpResponse(200, b"ok"))

    make_client(transport).prepare_dataset()

    assert [request["url"] for request in transport.requests] == [
        "http://fuseki:3030/$/datasets",
        "http://fuseki:3030/ethon-pilot/update",
    ]


def test_upload_turtle_sends_exact_bytes(tmp_path: Path) -> None:
    turtle = b"@prefix ex: <https://example.test/> .\nex:s ex:p ex:o .\n"
    path = tmp_path / "pilot.ttl"
    path.write_bytes(turtle)
    transport = FakeTransport(HttpResponse(204, b""))

    make_client(transport).upload_turtle(path)

    request = transport.requests[0]
    assert (request["method"], request["url"], request["body"]) == (
        "POST",
        "http://fuseki:3030/ethon-pilot/data",
        turtle,
    )
    assert request["headers"]["Content-Type"] == "text/turtle"


def test_query_posts_encoded_sparql_and_returns_json_bindings() -> None:
    sparql = "SELECT ?s WHERE { ?s ?p ?o . FILTER(?s = <https://example.test/a>) }"
    payload = b'{"results":{"bindings":[{"s":{"type":"uri","value":"urn:s"}}]}}'
    transport = FakeTransport(HttpResponse(200, payload))

    result = make_client(transport).query(sparql)

    request = transport.requests[0]
    assert (request["method"], request["url"]) == (
        "POST",
        "http://fuseki:3030/ethon-pilot/query",
    )
    assert parse_qs(request["body"].decode()) == {"query": [sparql]}
    assert request["headers"]["Accept"] == "application/sparql-results+json"
    assert result["results"]["bindings"][0]["s"]["value"] == "urn:s"


@pytest.mark.parametrize(
    ("responses", "operation"),
    [
        ((HttpResponse(500, b"create failed"),), "create dataset"),
        (
            (HttpResponse(201, b"created"), HttpResponse(500, b"clear failed")),
            "clear dataset",
        ),
        ((HttpResponse(415, b"upload failed"),), "upload Turtle"),
        ((HttpResponse(503, b"query failed"),), "query dataset"),
    ],
)
def test_unexpected_status_raises_safe_descriptive_error(
    tmp_path: Path,
    responses: tuple[HttpResponse, ...],
    operation: str,
) -> None:
    transport = FakeTransport(*responses)
    client = make_client(transport)
    turtle_path = tmp_path / "pilot.ttl"
    turtle_path.write_text("@prefix ex: <urn:example:> .")

    with pytest.raises(FusekiError) as caught:
        if operation in {"create dataset", "clear dataset"}:
            client.prepare_dataset()
        elif operation == "upload Turtle":
            client.upload_turtle(turtle_path)
        else:
            client.query("SELECT * WHERE { ?s ?p ?o }")

    message = str(caught.value)
    assert operation in message
    assert str(responses[-1].status) in message
    assert responses[-1].body.decode() in message
    assert "test-password" not in message
    auth_token = base64.b64encode(b"admin:test-password").decode("ascii")
    assert auth_token not in message


def test_upload_missing_path_raises_descriptive_error(tmp_path: Path) -> None:
    missing = tmp_path / "missing.ttl"

    with pytest.raises(FusekiError, match=r"Turtle file does not exist.*missing\.ttl"):
        make_client(FakeTransport()).upload_turtle(missing)


def test_malformed_query_json_raises_safe_error() -> None:
    transport = FakeTransport(HttpResponse(200, b"not-json test-password"))

    with pytest.raises(FusekiError) as caught:
        make_client(transport).query("SELECT * WHERE { ?s ?p ?o }")

    message = str(caught.value)
    assert "parse query response" in message
    assert "http://fuseki:3030/ethon-pilot/query" in message
    assert "test-password" not in message


def test_trailing_base_url_slash_is_normalized() -> None:
    transport = FakeTransport(HttpResponse(200, b'{"results":{"bindings":[]}}'))

    make_client(transport, base_url="http://fuseki:3030/").query("ASK {}")

    assert transport.requests[0]["url"] == "http://fuseki:3030/ethon-pilot/query"
    assert "test-password" not in repr(make_client(FakeTransport()))
