"""Authenticated REST reads (history, stats, chain, journal events).

The streaming APIs (market data, order entry) run over the NDJSON TCP sockets in
``market_data``/``orders``; the *read-only* analytics endpoints live on the
WS/REST gateways (``…:8443``). ``RestClient`` is a tiny stdlib-only (urllib) GET
helper that carries the bearer token and returns parsed JSON — the SDK stays
dependency-free.

The HTTP fetch is injectable (``opener``) so it can be exercised without a
network in tests.
"""
from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable

from .auth import TokenSource
from .errors import QJError

# opener(url, headers, method, data) -> (status_code, body_bytes)
Opener = Callable[..., "tuple[int, bytes]"]


class RestClient:
    def __init__(self, base_url: str, token_source: TokenSource, *,
                 ca_file: str | None = None, verify: bool = True,
                 opener: Opener | None = None) -> None:
        self._base = base_url.rstrip("/")
        self._ts = token_source
        self._ca_file = ca_file
        self._verify = verify
        self._opener = opener or self._urllib_opener

    def _ssl_ctx(self) -> ssl.SSLContext:
        ctx = ssl.create_default_context(cafile=self._ca_file)
        if not self._verify:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        return ctx

    def _urllib_opener(self, url: str, headers: dict, method: str = "GET",
                       data: bytes | None = None) -> tuple[int, bytes]:
        req = urllib.request.Request(url, headers=headers, data=data, method=method)
        try:
            with urllib.request.urlopen(req, timeout=15, context=self._ssl_ctx()) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()
        except urllib.error.URLError as e:
            raise QJError(f"request to {url} failed: {e.reason}") from None

    def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        query = {k: v for k, v in (params or {}).items() if v is not None}
        url = self._base + path
        if query:
            url += "?" + urllib.parse.urlencode(query)
        headers = {"Authorization": f"Bearer {self._ts.token()}"}
        return self._parse("GET", path, self._opener(url, headers, "GET", None))

    def post(self, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        url = self._base + path
        headers = {"Authorization": f"Bearer {self._ts.token()}",
                   "Content-Type": "application/json"}
        data = json.dumps(body or {}).encode()
        return self._parse("POST", path, self._opener(url, headers, "POST", data))

    def put(self, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        url = self._base + path
        headers = {"Authorization": f"Bearer {self._ts.token()}",
                   "Content-Type": "application/json"}
        data = json.dumps(body or {}).encode()
        return self._parse("PUT", path, self._opener(url, headers, "PUT", data))

    def delete(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        query = {k: v for k, v in (params or {}).items() if v is not None}
        url = self._base + path
        if query:
            url += "?" + urllib.parse.urlencode(query)
        headers = {"Authorization": f"Bearer {self._ts.token()}"}
        return self._parse("DELETE", path, self._opener(url, headers, "DELETE", None))

    @staticmethod
    def _parse(method: str, path: str, resp: tuple[int, bytes]) -> dict[str, Any]:
        status, body = resp
        if status < 200 or status >= 300:
            detail = body.decode("utf-8", "replace")[:300]
            raise QJError(f"{method} {path} failed (HTTP {status}): {detail}")
        try:
            return json.loads(body)
        except ValueError:
            raise QJError(f"{method} {path} returned non-JSON") from None
