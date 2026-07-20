import json
import os
import threading
from unittest.mock import patch

from qjtrader.connect import ConnectReporter


class _Response:
    def __init__(self, body): self.body = body
    def __enter__(self): return self
    def __exit__(self, *_): pass
    def read(self): return json.dumps(self.body).encode()


def test_reporter_is_dormant_without_connect_environment():
    with patch.dict(os.environ, {}, clear=True):
        assert ConnectReporter.from_environment() is None


def test_start_registers_strategy_and_run():
    reporter = ConnectReporter("https://connect.example", "computer-1", "client", "secret")
    reporter.tokens.token = lambda: "token"
    calls = []
    def open_request(request, timeout=0):
        calls.append((request.full_url, json.loads(request.data)))
        return _Response({"state": "running"})
    with patch("urllib.request.urlopen", open_request):
        stop = threading.Event()
        reporter.start(run_id="run-1", strategy_id="first", display_name="First",
                       version_hash="abc", symbols=["CA:RY"], stop=stop)
        reporter.finish("run-1", reason="done")
    assert [url.rsplit("/", 1)[-1] for url, _ in calls] == ["strategies", "runs", "finish"]
    assert calls[0][1]["computer_id"] == "computer-1"
    assert calls[1][1]["version_hash"] == "abc"
