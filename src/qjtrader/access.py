"""Safe handoff into QJ Gateway's human-approved production-access flow."""
from __future__ import annotations

from urllib.parse import urlencode

GATEWAY_ACCESS_URL = "https://gateway.qjtrader.ai/credentials"
GATEWAY_ADMIN_URL = "https://gateway.qjtrader.ai/admin"
MARKETS = {
    "ca-equities": "Canadian equities",
    "ca-futures": "Canadian futures",
    "ca-options": "Canadian listed options",
    "us-equities": "US equities and ETFs",
    "us-futures": "US futures",
    "us-options": "US listed options",
}


def production_access_url(*, plane: str = "data", markets: list[str] | tuple[str, ...] = (),
                          label: str = "", base_url: str = GATEWAY_ACCESS_URL) -> str:
    """Build a secret-free URL; Gateway sign-in and admin approval remain mandatory."""
    if plane not in {"data", "orders"}:
        raise ValueError("plane must be 'data' or 'orders'")
    unknown = [market for market in markets if market not in MARKETS]
    if unknown:
        raise ValueError(f"unknown market slug(s): {', '.join(unknown)}")
    params = {"access": plane, "source": "sdk"}
    if markets:
        params["markets"] = ",".join(MARKETS[market] for market in markets)
    if label.strip():
        params["label"] = label.strip()[:80]
    return f"{base_url}?{urlencode(params)}"


def admin_access_url(request_id: str, *, base_url: str = GATEWAY_ADMIN_URL) -> str:
    """Build a human-admin Gateway handoff for one production request.

    The browser session must authenticate as a member of the Gateway admins
    group. This helper carries no token, secret, approval, or authority.
    """
    request_id = request_id.strip()
    if not request_id.startswith("__prodreq__") or len(request_id) > 300:
        raise ValueError("request_id must be a QJ production request id")
    return f"{base_url}?{urlencode({'request': request_id, 'source': 'sdk-admin'})}"
