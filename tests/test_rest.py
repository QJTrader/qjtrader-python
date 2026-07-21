"""REST read client + Client convenience methods (injected opener — no network)."""
import pytest

from qjtrader.auth import TokenSource
from qjtrader.client import Client
from qjtrader.errors import QJError
from qjtrader.rest import RestClient


@pytest.fixture(autouse=True)
def _fake_token(monkeypatch):
    monkeypatch.setattr(TokenSource, "token", lambda self: "faketoken")


def test_rest_get_filters_params_and_sends_bearer():
    seen = {}

    def opener(url, headers, method="GET", data=None):
        seen["url"], seen["headers"] = url, headers
        return 200, b'{"ok": true}'

    ts = TokenSource("http://tok", "cid", "sec", "scope")
    rc = RestClient("https://h:8443", ts, opener=opener)
    out = rc.get("/api/v1/history",
                 {"symbol": "CA:RY", "interval": "1m", "to": None, "limit": 5})
    assert out == {"ok": True}
    assert seen["headers"]["Authorization"] == "Bearer faketoken"
    assert "symbol=CA%3ARY" in seen["url"] and "interval=1m" in seen["url"]
    assert "to=" not in seen["url"]          # None dropped
    assert "limit=5" in seen["url"]


def test_rest_get_raises_on_http_error():
    def opener(url, headers, method="GET", data=None):
        return 404, b"no chain snapshot"

    ts = TokenSource("http://tok", "cid", "sec", "scope")
    rc = RestClient("https://h:8443", ts, opener=opener)
    with pytest.raises(QJError) as ei:
        rc.get("/api/v1/chain", {"underlying": "MX:RY", "expiry": "202609"})
    assert "404" in str(ei.value)


def test_rest_put_and_delete_send_json_and_query():
    seen = []

    def opener(url, headers, method="GET", data=None):
        seen.append((url, headers, method, data))
        return 200, b'{"ok": true}'

    ts = TokenSource("http://tok", "cid", "sec", "scope")
    rc = RestClient("https://h:8443", ts, opener=opener)
    rc.put("/api/v1/recording/pin", {"symbol": "CA:RY"})
    rc.delete("/api/v1/recording/pin", {"symbol": "CA:RY"})
    assert seen[0][2] == "PUT" and b'"CA:RY"' in seen[0][3]
    assert seen[1][2] == "DELETE" and "symbol=CA%3ARY" in seen[1][0]


def test_client_recording_memory_methods_hit_data_gateway():
    calls = []

    def opener(url, headers, method="GET", data=None):
        calls.append((url, method, data))
        return 200, b'{"pinned": true, "symbols": ["CA:RY"]}'

    c = Client(client_id="a", client_secret="b", rest_opener=opener)
    assert c.recording_status("CA:RY")["pinned"] is True
    c.recording_pins()
    c.pin_recording("CA:RY")
    c.unpin_recording("CA:RY")
    assert [call[1] for call in calls] == ["GET", "GET", "PUT", "DELETE"]


def test_client_history_hits_data_gateway():
    calls = []

    def opener(url, headers, method="GET", data=None):
        calls.append(url)
        return 200, b'{"bars": []}'

    c = Client(client_id="a", client_secret="b", rest_opener=opener)
    c.history("MX:CGBU26", interval="1m", frm=0, to=60)
    assert "data-feed.qjtrader.ai:8443/api/v1/history" in calls[0]
    assert "symbol=MX%3ACGBU26" in calls[0]


def test_feed_admin_limits_use_admin_scope_and_encode_target():
    calls = []

    def opener(url, headers, method="GET", data=None):
        calls.append((url, method, data))
        return 200, b'{"limits":{"max_symbols":250,"max_connections":3}}'

    c = Client(client_id="admin", client_secret="secret", rest_opener=opener)
    assert c.feed_limits("client/with space")["limits"]["max_symbols"] == 250
    c.set_feed_limits("client/with space", max_symbols=250, max_connections=3)
    assert calls[0][0].endswith("/api/v1/admin/limits/client%2Fwith%20space")
    assert calls[0][1] == "GET"
    assert calls[1][1] == "POST"
    assert b'"max_symbols": 250' in calls[1][2]
    assert c.data_admin_rest()._ts._scope == "qj-data-feed/data-admin"


def test_feed_admin_limits_reject_invalid_local_values():
    c = Client(client_id="admin", client_secret="secret")
    with pytest.raises(ValueError, match="positive"):
        c.set_feed_limits(max_symbols=0)
    with pytest.raises(ValueError, match="provide"):
        c.set_feed_limits()


def test_rest_real_urllib_opener_over_http():
    """Exercise the real urllib opener + query/header build over an actual socket."""
    import http.server
    import json as _json
    import threading

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body = _json.dumps({"path": self.path,
                                "auth": self.headers.get("Authorization")}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        ts = TokenSource("http://tok", "cid", "sec", "scope")  # token faked by fixture
        rc = RestClient(f"http://127.0.0.1:{port}", ts)         # real urllib opener
        out = rc.get("/api/v1/history", {"symbol": "CA:RY"})
        assert out["auth"] == "Bearer faketoken"
        assert out["path"] == "/api/v1/history?symbol=CA%3ARY"
    finally:
        srv.shutdown()


def test_client_chain_normalizes_expiry_client_side():
    calls = []

    def opener(url, headers, method="GET", data=None):
        calls.append(url)
        return 200, b'{"strikes": []}'

    c = Client(client_id="a", client_secret="b", rest_opener=opener)
    # every spelling of Aug-2026 is normalized to YYYYMM before it hits the wire
    for form in ("202608", "2026-08-21", "20260821", "26AUG21"):
        calls.clear()
        c.chain("MX:RY", form)
        assert "data-feed.qjtrader.ai:8443/api/v1/chain" in calls[0]
        assert "expiry=202608" in calls[0]
    # a hopeless expiry is rejected locally with the YYYYMM hint (no round-trip)
    with pytest.raises(ValueError, match="YYYYMM"):
        c.chain("MX:RY", "nope")


def test_client_expiries_hits_data_gateway():
    calls = []

    def opener(url, headers, method="GET", data=None):
        calls.append(url)
        return 200, b'{"underlying": "MX:RY", "expiries": ["202608"]}'

    c = Client(client_id="a", client_secret="b", rest_opener=opener)
    out = c.expiries("MX:RY")
    assert "data-feed.qjtrader.ai:8443/api/v1/expiries" in calls[0]
    assert "underlying=MX%3ARY" in calls[0]
    assert out["expiries"] == ["202608"]


def test_client_events_hits_orders_gateway():
    calls = []

    def opener(url, headers, method="GET", data=None):
        calls.append(url)
        return 200, b'{"events": [], "cursor": null}'

    c = Client(client_id="a", client_secret="b", rest_opener=opener)
    c.events(since="2026-07-13T00:00:00Z", limit=10)
    assert "orders.qjtrader.ai:8443/api/v1/events" in calls[0]
    assert "limit=10" in calls[0]


def test_client_executions_hits_trade_log_projection():
    calls = []

    def opener(url, headers, method="GET", data=None):
        calls.append(url)
        return 200, b'{"executions": [], "next_cursor": null}'

    c = Client(client_id="a", client_secret="b", rest_opener=opener)
    c.executions(cursor="opaque", limit=25)
    assert "orders.qjtrader.ai:8443/api/v1/executions" in calls[0]
    assert "cursor=opaque" in calls[0] and "limit=25" in calls[0]
