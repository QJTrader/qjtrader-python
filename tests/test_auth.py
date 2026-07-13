"""Token caching/refresh logic (no network — urlopen is monkeypatched)."""
import io
import json

import qjtrader.auth as auth_mod
from qjtrader.auth import TokenSource
from qjtrader.errors import TokenError


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def test_token_is_cached_until_near_expiry(monkeypatch):
    calls = {"n": 0}

    def fake_urlopen(req, timeout=15):
        calls["n"] += 1
        return _Resp(json.dumps({"access_token": f"tok{calls['n']}", "expires_in": 3600}).encode())

    monkeypatch.setattr(auth_mod.urllib.request, "urlopen", fake_urlopen)
    ts = TokenSource("https://x/token", "cid", "sec", "qj-data-feed/orders")

    assert ts.token() == "tok1"
    assert ts.token() == "tok1"  # cached, not re-fetched
    assert calls["n"] == 1


def test_token_refreshes_after_expiry(monkeypatch):
    calls = {"n": 0}

    def fake_urlopen(req, timeout=15):
        calls["n"] += 1
        return _Resp(json.dumps({"access_token": f"tok{calls['n']}", "expires_in": 1}).encode())

    monkeypatch.setattr(auth_mod.urllib.request, "urlopen", fake_urlopen)
    ts = TokenSource("https://x/token", "cid", "sec", "s")
    first = ts.token()
    # expires_in=1 is inside the 60s refresh skew, so the next call re-fetches.
    assert ts.token() != first
    assert calls["n"] == 2


def test_http_error_becomes_tokenerror(monkeypatch):
    import urllib.error

    def boom(req, timeout=15):
        raise urllib.error.HTTPError("https://x", 401, "Unauthorized", {}, io.BytesIO(b"bad creds"))

    monkeypatch.setattr(auth_mod.urllib.request, "urlopen", boom)
    ts = TokenSource("https://x/token", "cid", "sec", "s")
    try:
        ts.token()
        assert False, "expected TokenError"
    except TokenError as e:
        assert "401" in str(e)


def test_sends_client_credentials_grant(monkeypatch):
    captured = {}

    def fake_urlopen(req, timeout=15):
        captured["body"] = req.data.decode()
        captured["auth"] = req.headers.get("Authorization")
        return _Resp(json.dumps({"access_token": "t", "expires_in": 3600}).encode())

    monkeypatch.setattr(auth_mod.urllib.request, "urlopen", fake_urlopen)
    TokenSource("https://x/token", "cid", "sec", "qj-data-feed/orders").token()
    assert "grant_type=client_credentials" in captured["body"]
    assert "scope=qj-data-feed%2Forders" in captured["body"]
    assert captured["auth"].startswith("Basic ")
