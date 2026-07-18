"""Market Data API client — subscribe to symbols and stream updates.

See the symbology reference for the symbol format:
https://docs.qjtrader.ai/docs/ai/symbology
"""
from __future__ import annotations

from typing import Iterable

from ._stream import _Stream


def top_of_book(message: dict) -> dict:
    """Normalize either a quote or L2 snapshot to one stable touch shape."""
    data = message.get("data") or {}
    bids = data.get("bids") or []
    asks = data.get("asks") or []
    return {
        "symbol": message.get("symbol"),
        "bid": data.get("bid", bids[0].get("price") if bids else None),
        "ask": data.get("ask", asks[0].get("price") if asks else None),
        "bid_size": data.get("bid_size", bids[0].get("size") if bids else None),
        "ask_size": data.get("ask_size", asks[0].get("size") if asks else None),
        "source_type": message.get("type"),
        "cbbo": data.get("cbbo") is True,
        "venue": data.get("venue"),
    }


class MarketData(_Stream):
    """A live market-data connection. Obtain one from :meth:`qjtrader.Client.market_data`."""

    def subscribe(self, symbols: Iterable[str], depth: int | None = None) -> None:
        """Subscribe to namespaced symbols, e.g. ``["CA:RY", "MX:CRAU26", "US:@ESU26"]``.

        A bare equity symbol (``CA:RY``) is the consolidated book; add a venue
        code (``CA:RY.PT``) for one exchange. ``depth`` sets Level-2 price levels.
        """
        msg: dict[str, object] = {"action": "subscribe", "symbols": list(symbols)}
        if depth is not None:
            msg["depth"] = depth
        self.send(msg)

    def unsubscribe(self, symbols: Iterable[str]) -> None:
        self.send({"action": "unsubscribe", "symbols": list(symbols)})

    def identify(self, tag: str) -> None:
        """Publish a metadata-only peer identity to observing Gateway sessions."""
        self.send({"action": "hello", "tag": tag[:512]})

    def ping(self) -> None:
        self.send({"action": "ping"})

    def quote(self, symbol: str, timeout: float = 10.0) -> dict:
        """Return a normalized touch.

        On a real consolidated Canadian symbol (``CA:RY``), this waits for the
        official ``cbbo=true`` quote. It deliberately ignores venue tops and L2
        snapshots that share the channel. A venue symbol such as ``CA:RY.PT``
        continues to return that venue's visible touch.
        """
        self.subscribe([symbol], depth=1)
        root = symbol.split(":", 1)[-1]
        official_cbbo = self.environment in {"real", "live"} and symbol.startswith("CA:") and "." not in root
        for msg in self.messages(timeout=timeout):
            if msg.get("symbol") != symbol:
                continue
            if official_cbbo and not (msg.get("type") == "quote" and (msg.get("data") or {}).get("cbbo") is True):
                continue
            if msg.get("type") in ("quote", "snapshot", "level2"):
                return top_of_book(msg)
        return {"symbol": symbol, "bid": None, "ask": None,
                "bid_size": None, "ask_size": None, "source_type": "timeout"}
