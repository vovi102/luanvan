"""Testable HTTP client for the local Fuseki EthOn pilot."""

from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

_SAFE_DATASET_PATTERN = re.compile(r"[A-Za-z0-9_-]+")


def _normalize_base_url(base_url: str) -> str:
    parsed = None
    try:
        parsed = urlsplit(base_url)
        valid = (
            parsed.scheme in {"http", "https"}
            and bool(parsed.netloc)
            and bool(parsed.hostname)
            and parsed.username is None
            and parsed.password is None
            and not parsed.query
            and not parsed.fragment
            and parsed.path in {"", "/"}
        )
    except ValueError:
        valid = False
    if not valid or parsed is None:
        raise ValueError(
            "Fuseki base URL must be an HTTP(S) root URL without userinfo, query, or fragment"
        ) from None
    return f"{parsed.scheme}://{parsed.netloc}"


def _validate_dataset(dataset: str) -> str:
    if _SAFE_DATASET_PATTERN.fullmatch(dataset) is None:
        raise ValueError(
            "Fuseki dataset must contain only letters, digits, underscores, and hyphens"
        )
    return dataset


@dataclass(frozen=True)
class HttpResponse:
    """Represent the HTTP response data needed by the pilot client."""

    status: int
    body: bytes


class HttpTransport(Protocol):
    """Define the injectable HTTP boundary used by the pilot client."""

    def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes,
    ) -> HttpResponse:
        """Send an HTTP request and return its status and body.

        Args:
            method: HTTP method to use.
            url: Destination URL.
            headers: Request headers.
            body: Request body bytes.

        Returns:
            The response status and body.
        """
        ...


class UrllibTransport:
    """Send Fuseki requests with Python's standard-library HTTP client."""

    def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes,
    ) -> HttpResponse:
        """Send an HTTP request and return its status and body.

        Args:
            method: HTTP method to use.
            url: Destination URL.
            headers: Request headers.
            body: Request body bytes.

        Returns:
            The response status and body, including for HTTP error statuses.
        """
        request = Request(url, data=body, headers=headers, method=method)
        try:
            with urlopen(request, timeout=30) as response:  # noqa: S310
                return HttpResponse(response.status, response.read())
        except HTTPError as error:
            return HttpResponse(error.code, error.read())


class FusekiError(RuntimeError):
    """Report a safe, contextual Fuseki pilot operation failure."""


class FusekiPilotClient:
    """Manage the in-memory Fuseki dataset used by the EthOn pilot."""

    def __init__(
        self,
        base_url: str,
        dataset: str,
        username: str,
        password: str,
        transport: HttpTransport | None = None,
    ) -> None:
        """Initialize the client with its endpoint and credentials.

        Args:
            base_url: Fuseki server URL.
            dataset: Dataset name to prepare and query.
            username: Fuseki HTTP Basic username.
            password: Fuseki HTTP Basic password.
            transport: Optional injectable HTTP transport.
        """
        self._base_url = _normalize_base_url(base_url)
        self._dataset = _validate_dataset(dataset)
        token = base64.b64encode(f"{username}:{password}".encode()).decode("ascii")
        self._authorization = f"Basic {token}"
        self._secrets = tuple(secret for secret in (password, token, self._authorization) if secret)
        self._transport = transport or UrllibTransport()

    def __repr__(self) -> str:
        """Return a representation that deliberately omits authentication data."""
        return f"{type(self).__name__}(base_url={self._base_url!r}, dataset={self._dataset!r})"

    def prepare_dataset(self) -> None:
        """Create the pilot dataset if needed and clear all existing data."""
        self._request_form(
            "create dataset",
            f"{self._base_url}/$/datasets",
            {"dbName": self._dataset, "dbType": "mem"},
            {200, 201, 409},
        )
        self._request_form(
            "clear dataset",
            f"{self._base_url}/{self._dataset}/update",
            {"update": "DROP ALL"},
            {200, 204},
        )

    def upload_turtle(self, path: str | Path) -> None:
        """Upload the exact bytes of a local Turtle file to the pilot dataset.

        Args:
            path: Local Turtle file to upload.

        Raises:
            FusekiError: If the file is missing or Fuseki rejects the upload.
        """
        turtle_path = Path(path)
        if not turtle_path.is_file():
            message = self._redact(f"Turtle file does not exist: {turtle_path}")
            raise FusekiError(message)
        self._request(
            "upload Turtle",
            f"{self._base_url}/{self._dataset}/data",
            {"Content-Type": "text/turtle"},
            turtle_path.read_bytes(),
            {200, 201, 204},
        )

    def query(self, sparql: str) -> dict[str, Any]:
        """Run a SPARQL query and return its decoded JSON result document.

        Args:
            sparql: Exact SPARQL query string to execute.

        Returns:
            The SPARQL JSON result document.

        Raises:
            FusekiError: If Fuseki rejects the query or returns malformed JSON.
        """
        endpoint = f"{self._base_url}/{self._dataset}/query"
        response = self._request_form(
            "query dataset",
            endpoint,
            {"query": sparql},
            {200},
            accept="application/sparql-results+json",
        )
        parse_error_message: str | None = None
        try:
            result = json.loads(response.body)
        except (UnicodeDecodeError, json.JSONDecodeError):
            parse_error_message = self._redact(f"parse query response failed for {endpoint}")
        if parse_error_message is not None:
            raise FusekiError(parse_error_message) from None
        if not isinstance(result, dict):
            message = self._redact(f"parse query response failed for {endpoint}: expected object")
            raise FusekiError(message)
        return result

    def _request_form(
        self,
        operation: str,
        endpoint: str,
        fields: dict[str, str],
        expected_statuses: set[int],
        *,
        accept: str | None = None,
    ) -> HttpResponse:
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        if accept is not None:
            headers["Accept"] = accept
        return self._request(
            operation,
            endpoint,
            headers,
            urlencode(fields).encode("ascii"),
            expected_statuses,
        )

    def _request(
        self,
        operation: str,
        endpoint: str,
        headers: dict[str, str],
        body: bytes,
        expected_statuses: set[int],
    ) -> HttpResponse:
        request_headers = {**headers, "Authorization": self._authorization}
        network_error_message: str | None = None
        try:
            response = self._transport.request("POST", endpoint, request_headers, body)
        except URLError as error:
            reason = self._redact(str(error.reason))
            safe_endpoint = self._redact(endpoint)
            network_error_message = f"{operation} failed for {safe_endpoint}: {reason}"
        if network_error_message is not None:
            raise FusekiError(network_error_message) from None
        if response.status not in expected_statuses:
            # Redact before truncating so credential expansion cannot exceed the final bound.
            response_text = self._redact(response.body.decode("utf-8", errors="replace"))[:500]
            safe_endpoint = self._redact(endpoint)
            message = (
                f"{operation} failed for {safe_endpoint}: HTTP {response.status}; "
                f"response: {response_text}"
            )
            raise FusekiError(message)
        return response

    def _redact(self, message: str) -> str:
        for secret in self._secrets:
            message = message.replace(secret, "[REDACTED]")
        return message
