"""Order Entry API client — send orders and stream execution reports.

Order lifecycle (journaled, monotonic):
``accepted -> new -> (partial)* -> filled | canceled | replaced``; ``rejected``
may replace any non-terminal state. Each order carries a client order id (``cid``)
that is unique per credential forever — re-sending the same ``cid`` is idempotent
and never double-fires. Full reference: https://docs.qjtrader.ai/docs/ai/order-entry
"""
from __future__ import annotations

import uuid
from typing import Any, Iterator

from ._stream import _Stream

_TERMINAL = frozenset({"filled", "canceled", "rejected", "replaced"})


def _new_cid() -> str:
    return f"qj-{uuid.uuid4().hex[:12]}"


class Orders(_Stream):
    """A live order-entry connection. Obtain one from :meth:`qjtrader.Client.orders`."""

    def order(self, *, sym: str, side: str, qty: int, price: float,
              account: str = "", tif: str = "day", iceberg: int = 0,
              cid: str | None = None, venue: str | None = None,
              actor: dict[str, str] | None = None) -> str:
        """Submit a limit order. Returns the ``cid`` (generated if not given).

        ``side``: ``"buy"``/``"sell"``. ``tif``: ``"day"``/``"ioc"``/``"fok"``.
        ``venue`` uses the desktop QJ exchange suffix vocabulary (for example
        ``TO``, ``PT``, ``LY``, or ``TL``); ``SOR`` and ``DARK`` are cloud
        route selectors. A venue suffix on ``sym`` remains supported.
        Iterate :meth:`updates` to receive acks and fills.
        """
        cid = cid or _new_cid()
        msg: dict[str, Any] = {
            "action": "order", "cid": cid, "sym": sym, "side": side, "qty": qty,
            "type": "limit", "price": price, "tif": tif, "account": account,
            "iceberg": iceberg,
        }
        if venue:
            msg["venue"] = venue.upper()
        if actor:
            # Structured attribution survives cid format changes and lets the
            # Gateway correlate one strategy run across orders and executions.
            msg["actor"] = {str(k): str(v) for k, v in actor.items() if v}
        self.send(msg)
        return cid

    def cancel(self, orig_cid: str, cid: str | None = None) -> str:
        cid = cid or _new_cid()
        self.send({"action": "cancel", "cid": cid, "orig_cid": orig_cid})
        return cid

    def replace(self, orig_cid: str, *, qty: int | None = None,
                price: float | None = None, cid: str | None = None) -> str:
        cid = cid or _new_cid()
        msg: dict[str, Any] = {"action": "replace", "cid": cid, "orig_cid": orig_cid}
        if qty is not None:
            msg["qty"] = qty
        if price is not None:
            msg["price"] = price
        self.send(msg)
        return cid

    def cancel_all(self) -> None:
        self.send({"action": "cancel_all"})

    def status(self, timeout: float = 10.0) -> dict[str, Any] | None:
        """Request open orders + session state; returns the ``status`` message."""
        self.send({"action": "status"})
        for msg in self.messages(timeout=timeout):
            if msg.get("type") == "status":
                return msg
        return None

    def updates(self, timeout: float = 15.0) -> Iterator[dict[str, Any]]:
        """Stream ``order_update`` / ``exec`` messages for `timeout` seconds."""
        return self.messages(timeout=timeout)

    def order_and_wait(self, *, timeout: float = 15.0, **order_kwargs: Any) -> dict[str, Any]:
        """Submit an order and block until it reaches a terminal state (or timeout).

        Returns the last message seen (a fill, cancel, reject, or the resting
        ``new`` if it hasn't completed within `timeout`).
        """
        cid = self.order(**order_kwargs)
        last: dict[str, Any] = {"type": "order_update", "cid": cid, "status": "submitted"}
        for msg in self.updates(timeout=timeout):
            if msg.get("cid") == cid or msg.get("new_cid") == cid:
                last = msg
                status = msg.get("status")
                if msg.get("type") == "exec" and status == "filled":
                    return msg
                if msg.get("type") == "order_update" and status in _TERMINAL:
                    return msg
        return last
