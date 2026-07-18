from urllib.parse import parse_qs, urlparse

import pytest

from qjtrader.access import admin_access_url, production_access_url
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
