"""Market Data API client — subscribe to symbols and stream updates.

See the symbology reference for the symbol format:
https://docs.qjtrader.ai/docs/ai/symbology
"""
from __future__ import annotations

from typing import Iterable

from ._stream import _Stream


class MarketData(_Stream):
    """A live market-data connection. Obtain one from :meth:`qjtrader.Client.market_data`."""

    def subscribe(self, symbols: Iterable[str], depth: int | None = None) -> None:
        """Subscribe to namespaced symbols, e.g. ``["CA:RY", "CA:RY.PT", "MX:CRAU26"]``.

        A bare equity symbol (``CA:RY``) is the consolidated book; add a venue
        code (``CA:RY.PT``) for one exchange. ``depth`` sets Level-2 price levels.
        """
        msg: dict[str, object] = {"action": "subscribe", "symbols": list(symbols)}
        if depth is not None:
            msg["depth"] = depth
        self.send(msg)

    def unsubscribe(self, symbols: Iterable[str]) -> None:
        self.send({"action": "unsubscribe", "symbols": list(symbols)})

    def ping(self) -> None:
        self.send({"action": "ping"})
