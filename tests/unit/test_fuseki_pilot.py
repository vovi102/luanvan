"""Unit tests for the testable Fuseki EthOn pilot client."""

from __future__ import annotations

import base64
import traceback
from collections import deque
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.parse import parse_qs

import pytest

from nl2sparql.kg.ontology.fuseki_pilot import (
    FusekiError,
    FusekiPilotClient,
    HttpResponse,
)


class FakeTransport:
    """Record HTTP requests and return queued responses."""

    def __init__(self, *responses: HttpResponse | BaseException) -> None:
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
        response = self.responses.popleft()
        if isinstance(response, BaseException):
            raise response
        return response


PASSWORD = "test-password"
AUTH_TOKEN = base64.b64encode(f"admin:{PASSWORD}".encode()).decode("ascii")


def assert_exception_has_no_secrets(error: BaseException) -> None:
    """Assert an exception and its retained chain cannot disclose credentials."""
    formatted = "".join(traceback.format_exception(error))
    assert PASSWORD not in formatted
    assert AUTH_TOKEN not in formatted

    seen: set[int] = set()
    pending: list[BaseException] = [error]
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        text = f"{current!s} {current!r}"
        assert PASSWORD not in text
        assert AUTH_TOKEN not in text
        pending.extend(
            chained for chained in (current.__cause__, current.__context__) if chained is not None
        )


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
        PASSWORD,
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
    assert create["body"] == b"dbName=ethon-pilot&dbType=mem"
    assert create["headers"]["Content-Type"] == "application/x-www-form-urlencoded"
    assert create["headers"]["Authorization"] == f"Basic {AUTH_TOKEN}"
    assert (clear["method"], clear["url"]) == (
        "POST",
        "http://fuseki:3030/ethon-pilot/update",
    )
    assert parse_qs(clear["body"].decode()) == {"update": ["DROP ALL"]}
    assert clear["body"] == b"update=DROP+ALL"
    assert PASSWORD not in create["url"]
    assert PASSWORD not in create["body"].decode()


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
    assert request["body"] == (
        b"query=SELECT+%3Fs+WHERE+%7B+%3Fs+%3Fp+%3Fo+.+"
        b"FILTER%28%3Fs+%3D+%3Chttps%3A%2F%2Fexample.test%2Fa%3E%29+%7D"
    )
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
    assert_exception_has_no_secrets(caught.value)


def test_upload_missing_path_raises_descriptive_error(tmp_path: Path) -> None:
    missing = tmp_path / "missing.ttl"

    with pytest.raises(FusekiError, match=r"Turtle file does not exist.*missing\.ttl"):
        make_client(FakeTransport()).upload_turtle(missing)


def test_malformed_query_json_raises_safe_error() -> None:
    payload = f"not-json {PASSWORD} {AUTH_TOKEN}".encode()
    transport = FakeTransport(HttpResponse(200, payload))

    with pytest.raises(FusekiError) as caught:
        make_client(transport).query("SELECT * WHERE { ?s ?p ?o }")

    message = str(caught.value)
    assert "parse query response" in message
    assert "http://fuseki:3030/ethon-pilot/query" in message
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None
    assert_exception_has_no_secrets(caught.value)


def test_network_error_does_not_retain_credentials_in_exception_chain() -> None:
    reason = f"connection failed with {PASSWORD} and Basic {AUTH_TOKEN}"
    transport = FakeTransport(URLError(reason))

    with pytest.raises(FusekiError) as caught:
        make_client(transport).query("ASK {}")

    assert "connection failed" in str(caught.value)
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None
    assert_exception_has_no_secrets(caught.value)


def test_status_error_redacts_then_limits_response_excerpt() -> None:
    short_password = "!"
    response_body = (short_password * 600).encode()
    transport = FakeTransport(HttpResponse(500, response_body))
    client = FusekiPilotClient(
        "http://fuseki:3030",
        "ethon-pilot",
        "admin",
        short_password,
        transport=transport,
    )

    with pytest.raises(FusekiError) as caught:
        client.query("ASK {}")

    excerpt = str(caught.value).partition("response: ")[2]
    assert "[REDACTED]" in excerpt
    assert len(excerpt) <= 500
    assert short_password not in excerpt


def test_status_error_redacts_overlapping_basic_auth_secrets() -> None:
    password = "a"
    token = base64.b64encode(f"admin:{password}".encode()).decode("ascii")
    authorization = f"Basic {token}"
    response_body = (
        f"credential={password}; token={token}; authorization={authorization}"
    ).encode()
    transport = FakeTransport(HttpResponse(500, response_body))
    client = FusekiPilotClient(
        "http://fuseki:3030",
        "ethon-pilot",
        "admin",
        password,
        transport=transport,
    )

    with pytest.raises(FusekiError) as caught:
        client.query("ASK {}")

    forbidden = (
        "credential=a",
        token,
        authorization,
        "YWRt",
        "W46YQ==",
        "B[REDACTED]sic",
    )
    formatted = "".join(traceback.format_exception(caught.value))
    assert all(secret not in formatted for secret in forbidden)

    pending = [caught.value]
    while pending:
        error = pending.pop()
        rendered = f"{error!s} {error!r}"
        assert all(secret not in rendered for secret in forbidden)
        pending.extend(
            chained for chained in (error.__cause__, error.__context__) if chained is not None
        )


def test_trailing_base_url_slash_is_normalized() -> None:
    transport = FakeTransport(HttpResponse(200, b'{"results":{"bindings":[]}}'))

    make_client(transport, base_url="http://fuseki:3030/").query("ASK {}")

    assert transport.requests[0]["url"] == "http://fuseki:3030/ethon-pilot/query"


def test_repr_omits_all_authentication_data() -> None:
    representation = repr(make_client(FakeTransport()))

    assert "http://fuseki:3030" in representation
    assert "ethon-pilot" in representation
    assert "admin" not in representation
    assert PASSWORD not in representation
    assert AUTH_TOKEN not in representation


@pytest.mark.parametrize(
    "base_url",
    [
        "ftp://fuseki:3030",
        "fuseki:3030",
        "http:///missing-host",
        "http://admin:url-secret@fuseki:3030",
        "http://fuseki:3030?token=url-secret",
        "http://fuseki:3030#url-secret",
        "http://fuseki:3030/fuseki",
    ],
)
def test_invalid_base_url_is_rejected_without_contacting_transport(base_url: str) -> None:
    transport = FakeTransport()

    with pytest.raises(ValueError, match="base URL"):
        make_client(transport, base_url=base_url)

    assert transport.requests == []


@pytest.mark.parametrize(
    ("base_url", "expected_base_url"),
    [
        ("http://fuseki:3030", "http://fuseki:3030"),
        ("http://fuseki:3030/", "http://fuseki:3030"),
        ("https://fuseki.example/", "https://fuseki.example"),
    ],
)
def test_http_and_https_root_urls_are_accepted_and_normalized(
    base_url: str,
    expected_base_url: str,
) -> None:
    transport = FakeTransport(HttpResponse(200, b'{"results":{"bindings":[]}}'))

    client = make_client(transport, base_url=base_url)
    client.query("ASK {}")

    assert transport.requests[0]["url"] == f"{expected_base_url}/ethon-pilot/query"
    assert expected_base_url in repr(client)


def test_userinfo_url_rejection_does_not_leak_credentials() -> None:
    url_username = "url-admin"
    url_password = "url-secret"
    credential_url = f"http://{url_username}:{url_password}@fuseki:3030"

    with pytest.raises(ValueError) as caught:
        make_client(FakeTransport(), base_url=credential_url)

    formatted = "".join(traceback.format_exception(caught.value))
    for secret in (url_username, url_password, credential_url):
        assert secret not in str(caught.value)
        assert secret not in formatted


@pytest.mark.parametrize(
    "dataset",
    ["", "/", "a/b", "a?b", "a#b", "with space", "ethon%2Fpilot", ".", ".."],
)
def test_unsafe_dataset_is_rejected_without_affecting_routing(dataset: str) -> None:
    transport = FakeTransport()

    with pytest.raises(ValueError, match="dataset"):
        FusekiPilotClient(
            "http://fuseki:3030",
            dataset,
            "admin",
            PASSWORD,
            transport=transport,
        )

    assert transport.requests == []


@pytest.mark.parametrize("dataset", ["ethon-pilot", "EthOn_2026", "pilot123"])
def test_safe_dataset_is_used_as_one_path_segment(dataset: str) -> None:
    transport = FakeTransport(HttpResponse(200, b'{"results":{"bindings":[]}}'))
    client = FusekiPilotClient(
        "http://fuseki:3030",
        dataset,
        "admin",
        PASSWORD,
        transport=transport,
    )

    client.query("ASK {}")

    assert transport.requests[0]["url"] == f"http://fuseki:3030/{dataset}/query"
