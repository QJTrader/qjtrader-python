"""Shared NDJSON-over-TLS stream: connect, authenticate, read messages.

Both APIs speak the same wire contract — one JSON object per line, UTF-8,
newline-terminated, over TLS; the first line the client sends is
``{"action": "auth", "token": <jwt>}`` and the server replies
``{"type": "auth_success", ...}``. This class carries that for both.
"""
from __future__ import annotations

import json
import select
import socket
import ssl
import time
from typing import Any, Iterator

from .auth import TokenSource
from .errors import AuthError, ConnectionClosed

_CLOSED = object()


class _Stream:
    """A single TLS connection carrying newline-delimited JSON."""

    def __init__(self, token_source: TokenSource, host: str, port: int, *,
                 ca_file: str | None = None, verify: bool = True,
                 timeout: float = 15.0) -> None:
        self._ts = token_source
        self._host = host
        self._port = port
        self._ca_file = ca_file
        self._verify = verify
        self._timeout = timeout
        self._sock: ssl.SSLSocket | None = None
        self._buf = bytearray()
        #: The authenticated principal (client_id), set after connect().
        self.user: str | None = None
        #: Full server authentication/session acknowledgement.
        self.auth_info: dict[str, Any] = {}
        #: Authoritative server-resolved environment for this API plane.
        self.environment: str | None = None
        #: Opaque marker for the authority row version, when supplied.
        self.authority_version: str | None = None

    # -- lifecycle ---------------------------------------------------------
    def connect(self) -> "_Stream":
        """Open the TLS connection and complete the auth handshake."""
        if self._verify:
            ctx = ssl.create_default_context(cafile=self._ca_file)
        else:  # pilot/dev only — never in production
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        raw = socket.create_connection((self._host, self._port), timeout=self._timeout)
        self._sock = ctx.wrap_socket(raw, server_hostname=self._host)
        try:
            self._authenticate()
        except BaseException:
            self.close()
            raise
        return self

    def _authenticate(self) -> dict[str, Any]:
        self.send({"action": "auth", "token": self._ts.token()})
        line = self._read_line(time.monotonic() + self._timeout)
        if line is None or line is _CLOSED:
            raise AuthError("no auth response (timeout or connection closed)")
        ack = json.loads(line)
        if ack.get("type") != "auth_success":
            raise AuthError(f"auth rejected: {ack.get('message') or ack}")
        self.auth_info = dict(ack)
        self.user = ack.get("user")
        self.environment = ack.get("environment") or ack.get("env")
        self.authority_version = ack.get("authority_version")
        return ack

    def close(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    def __enter__(self) -> "_Stream":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- io ----------------------------------------------------------------
    def send(self, obj: dict[str, Any]) -> None:
        """Send one JSON message."""
        assert self._sock is not None, "not connected"
        self._sock.sendall(json.dumps(obj).encode() + b"\n")

    def _read_line(self, deadline: float) -> bytes | None | object:
        """One line, or None on this-slice timeout, or _CLOSED on close."""
        while True:
            nl = self._buf.find(b"\n")
            if nl >= 0:
                line = bytes(self._buf[:nl])
                del self._buf[: nl + 1]
                return line
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            r, _, _ = select.select([self._sock], [], [], min(remaining, 1.0))
            if not r:
                continue
            try:
                chunk = self._sock.recv(1 << 16)  # type: ignore[union-attr]
            except ssl.SSLWantReadError:
                continue
            if not chunk:
                return _CLOSED
            self._buf.extend(chunk)

    def messages(self, timeout: float | None = None,
                 include_heartbeats: bool = False) -> Iterator[dict[str, Any]]:
        """Yield decoded messages until `timeout` seconds elapse (or forever if
        None). Raises :class:`ConnectionClosed` if the server closes the stream."""
        deadline = time.monotonic() + timeout if timeout is not None else float("inf")
        while time.monotonic() < deadline:
            line = self._read_line(deadline)
            if line is None:
                continue
            if line is _CLOSED:
                raise ConnectionClosed("server closed the connection")
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if msg.get("type") == "heartbeat" and not include_heartbeats:
                continue
            yield msg
