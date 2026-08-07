from pathlib import Path

import pytest

from qjtrader.scaffold import create_strategy_project
from qjtrader.universe import describe_instrument, product_key, search_symbols
from qjtrader.client import Client


@pytest.mark.parametrize(("symbol", "key"), [
    ("CA:RY", "ca_equity"),
    ("CA:XIU", "ca_etf"),
    ("MX:CGBU26", "mx_future"),
    ("MX:CRAH27CRAU27", "mx_strategy"),
    ("MX:RY26AUG142.5C21", "mx_option"),
    ("US:@ESU26", "us_future"),
    ("US:@USU26", "us_future"),
    ("US:@TYU26", "us_future"),
    ("US:@FVU26", "us_future"),
    ("US:SPY", "us_equity_etf"),
])
def test_product_key(symbol, key):
    assert product_key(symbol) == key


def test_describe_is_authority_aware():
    d = describe_instrument("CA:RY", data_environment="real", orders_environment="canary")
    assert d["plain_name"] == "Canadian common share"
    assert d["can_reach_exchange"] is True
    assert "price-aggregated" in d["data_shape"]
    assert "unquoted" in d["observation_contract"]


def test_search_filters_and_bounds():
    found = search_symbols(["CA:RY", "US:SPY", "MX:CGBU26"], "future", limit=1)
    assert len(found) == 1 and found[0]["symbol"] == "MX:CGBU26"


def test_client_prefers_feed_owned_instrument_catalog():
    class Rest:
        def get(self, _path):
            return {
                "symbols": ["MX:CGBU26"],
                "instruments": [{
                    "instrument_id": "qj_abc", "canonical_symbol": "MX:CGBU26",
                    "asset_class": "future", "instrument_type": "future",
                }],
            }

    client = object.__new__(Client)
    client.data_rest = lambda: Rest()
    client.session_info = lambda: {"data_environment": "real",
                                   "orders_environment": "sandbox"}
    result = client.search_universe("future")
    assert result["source"] == "gateway instrument catalog"
    assert result["instruments"][0]["instrument_id"] == "qj_abc"
    assert result["instruments"][0]["data_environment"] == "real"


def test_scaffold_is_safe_and_does_not_overwrite(tmp_path: Path):
    made = create_strategy_project(str(tmp_path / "mine"), symbol="MX:CGBU26")
    assert len(made) == 3
    strategy = (tmp_path / "mine" / "strategy.py").read_text(encoding="utf-8")
    assert 'allow_orders", False' in strategy
    assert 'report["orders"], 0' in (tmp_path / "mine" / "test_strategy.py").read_text(encoding="utf-8")
    with pytest.raises(FileExistsError):
        create_strategy_project(str(tmp_path / "mine"))
