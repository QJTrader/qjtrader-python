"""NDJSON framing + message iteration + Client config (no network)."""
import os

import pytest

import qjtrader
from qjtrader._stream import _CLOSED, _Stream
from qjtrader.errors import ConnectionClosed, QJError


class _FakeSock:
    """Feeds pre-canned bytes to _Stream._read_line via recv(); select() always ready."""

    def __init__(self, chunks):
        self._chunks = list(chunks)

    def recv(self, _n):
        return self._chunks.pop(0) if self._chunks else b""

    def close(self):
        pass


def _stream_with(chunks):
    s = _Stream.__new__(_Stream)  # bypass __init__/network
    s._sock = _FakeSock(chunks)
    s._buf = bytearray()
    return s


def test_lines_are_split_on_newline(monkeypatch):
    import qjtrader._stream as sm
    monkeypatch.setattr(sm.select, "select", lambda *a, **k: ([s._sock], [], []))
    s = _stream_with([b'{"a":1}\n{"b":', b'2}\n'])
    import time
    d = time.monotonic() + 5
    assert s._read_line(d) == b'{"a":1}'
    assert s._read_line(d) == b'{"b":2}'
    assert s._read_line(d) is _CLOSED  # recv() -> b"" == closed


def test_messages_skips_heartbeats_and_raises_on_close(monkeypatch):
    import qjtrader._stream as sm
    monkeypatch.setattr(sm.select, "select", lambda *a, **k: ([1], [], []))
    s = _stream_with([b'{"type":"heartbeat"}\n{"type":"quote","symbol":"CA:RY"}\n'])
    got = []
    with pytest.raises(ConnectionClosed):
        for msg in s.messages(timeout=5):
            got.append(msg)
    assert got == [{"type": "quote", "symbol": "CA:RY"}]  # heartbeat filtered out


def test_client_requires_credentials(monkeypatch):
    monkeypatch.delenv("QJ_CLIENT_ID", raising=False)
    monkeypatch.delenv("QJ_CLIENT_SECRET", raising=False)
    with pytest.raises(QJError):
        qjtrader.Client()


def test_client_reads_env_and_defaults(monkeypatch):
    monkeypatch.setenv("QJ_CLIENT_ID", "cid")
    monkeypatch.setenv("QJ_CLIENT_SECRET", "sec")
    monkeypatch.delenv("QJ_DATA_HOST", raising=False)
    monkeypatch.delenv("QJ_ORDERS_HOST", raising=False)
    c = qjtrader.Client()
    assert c._data_host == "data-feed.qjtrader.ai"
    assert c._orders_host == "orders.qjtrader.ai"
    assert c.token.__self__ is c  # bound method exists
