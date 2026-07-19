from urllib.parse import parse_qs, urlparse

import pytest

from qjtrader.access import AccessClient, admin_access_url, production_access_url
from qjtrader._cli import main


def test_access_url_contains_only_human_review_prefill():
    url = production_access_url(plane="data", markets=["ca-equities"], label="M3alpha CSU shadow")
    assert parse_qs(urlparse(url).query) == {
        "access": ["data"], "source": ["sdk"],
        "markets": ["Canadian equities"], "label": ["M3alpha CSU shadow"],
    }
    assert "secret" not in url.lower()
    assert "approve" not in url.lower()


def test_access_url_rejects_unknown_scope():
    with pytest.raises(ValueError, match="unknown market"):
        production_access_url(markets=["everything"])


def test_access_request_cli_can_print_without_credentials(capsys):
    assert main(["access-request", "--plane", "data", "--market", "ca-equities",
                 "--label", "M3alpha CSU shadow", "--no-open"]) == 0
    assert "gateway.qjtrader.ai/credentials?" in capsys.readouterr().out


def test_admin_handoff_contains_no_admin_token_or_secret():
    url = admin_access_url("__prodreq__owner@example.com__client")
    assert "gateway.qjtrader.ai/admin?" in url
    assert "token" not in url.lower()
    assert "secret" not in url.lower()


def test_programmatic_request_uses_human_token_not_machine_key(tmp_path, monkeypatch):
    token_file = tmp_path / "user.json"
    token_file.write_text('{"access_token":"human-token","client_id":"browser-client"}')
    client = AccessClient(base_url="https://control.example", token_file=token_file)
    seen = {}
    def fake_json(method, path, body=None, bearer=""):
        seen.update(method=method, path=path, body=body, bearer=bearer)
        return {"status": "pending"}
    monkeypatch.setattr(client, "_json", fake_json)
    assert client.request(plane="data", markets=["ca-equities"])["status"] == "pending"
    assert seen == {"method": "POST", "path": "/access", "body": {
        "plane": "data", "markets": ["ca-equities"], "use_case": "",
        "mode": "standard", "additional_reason": "", "credential_mode": "account",
    }, "bearer": "human-token"}


def test_programmatic_limit_request_is_human_authorized_and_layered(tmp_path, monkeypatch):
    token_file = tmp_path / "user.json"
    token_file.write_text('{"access_token":"human-token","client_id":"browser-client"}')
    client = AccessClient(base_url="https://control.example", token_file=token_file)
    seen = {}
    monkeypatch.setattr(client, "_authorized", lambda method, path, body=None: seen.update(
        method=method, path=path, body=body) or {"status": "pending"})
    assert client.request_limit_change(product="us-futures", max_qty=2, daily_qty=40,
                                       reason="two-leg strategy")["status"] == "pending"
    assert seen["path"] == "/access/limits"
    assert seen["body"]["product"] == "us-futures"
    assert seen["body"]["max_qty"] == 2 and seen["body"]["daily_qty"] == 40


def test_limit_request_cli_uses_the_same_human_authorized_api(monkeypatch, capsys):
    seen = {}
    monkeypatch.setattr(AccessClient, "request_limit_change", lambda self, **kwargs:
                        seen.update(kwargs) or {"status": "pending"})
    assert main(["limit-request", "--product", "us-futures", "--max-qty", "2",
                 "--daily-qty", "40", "--reason", "two-leg strategy"]) == 0
    assert seen["product"] == "us-futures" and seen["max_qty"] == 2
    assert '"status": "pending"' in capsys.readouterr().out


def test_admin_decision_can_narrow_approved_markets(tmp_path, monkeypatch):
    token_file = tmp_path / "user.json"
    token_file.write_text('{"access_token":"human-token","client_id":"browser-client"}')
    client = AccessClient(base_url="https://control.example", token_file=token_file)
    seen = {}
    monkeypatch.setattr(client, "_authorized", lambda method, path, body=None: seen.update(
        method=method, path=path, body=body) or {"status": "approved"})
    client.admin_decide("request-1", "approved", ["ca-equities"])
    assert seen == {"method": "POST", "path": "/admin/access/requests/request-1",
                    "body": {"decision": "approved", "markets": ["ca-equities"]}}
