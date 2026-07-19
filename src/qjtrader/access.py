"""Human-user access control for QJ Gateway.

Machine trading credentials never gain approval authority.  These helpers use
the Gateway's browser sign-in and PKCE, then call the same access request queue
as the UI.  URL handoff helpers remain available for scripts that cannot open a
local callback listener.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from urllib.parse import urlencode

GATEWAY_ACCESS_URL = "https://gateway.qjtrader.ai/credentials"
GATEWAY_ADMIN_URL = "https://gateway.qjtrader.ai/admin"
CONTROL_URL = "https://mcp.qjtrader.ai"
MARKETS = {
    "ca-equities": "Canadian equities",
    "ca-futures": "Canadian futures",
    "ca-options": "Canadian listed options",
    "us-equities": "US equities and ETFs",
    "us-futures": "US futures",
    "us-options": "US listed options",
}


class AccessClient:
    """Authenticated, human-controlled market-access API."""

    def __init__(self, *, base_url: str = CONTROL_URL, token_file: str | Path | None = None):
        self.base_url = base_url.rstrip("/")
        self.token_file = Path(token_file) if token_file else Path.home() / ".qjtrader" / "user-access.json"

    def login(self, *, timeout: float = 180.0, open_browser: bool = True) -> dict:
        verifier = secrets.token_urlsafe(48)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        state = secrets.token_urlsafe(20)
        result: dict[str, str] = {}

        class Callback(BaseHTTPRequestHandler):
            def do_GET(inner):  # noqa: N802
                from urllib.parse import parse_qs, urlparse
                query = parse_qs(urlparse(inner.path).query)
                result.update({key: values[0] for key, values in query.items() if values})
                body = b"QJ Gateway connected. You can close this window."
                inner.send_response(200); inner.send_header("content-type", "text/plain")
                inner.send_header("content-length", str(len(body))); inner.end_headers(); inner.wfile.write(body)
            def log_message(self, *_):
                return

        server = HTTPServer(("127.0.0.1", 0), Callback)
        redirect_uri = f"http://127.0.0.1:{server.server_port}/callback"
        registered = self._json("POST", "/register", {"client_name": "qjtrader Python", "redirect_uris": [redirect_uri]})
        client_id = registered["client_id"]
        authorize = f"{self.base_url}/authorize?{urlencode({'response_type': 'code', 'client_id': client_id, 'redirect_uri': redirect_uri, 'code_challenge': challenge, 'code_challenge_method': 'S256', 'state': state, 'scope': 'access.manage offline_access'})}"
        if open_browser:
            webbrowser.open(authorize)
        else:
            print(authorize)
        thread = threading.Thread(target=server.handle_request, daemon=True); thread.start(); thread.join(timeout)
        server.server_close()
        if result.get("state") != state or not result.get("code"):
            raise TimeoutError("QJ Gateway sign-in did not complete.")
        tokens = self._form("/token", {"grant_type": "authorization_code", "client_id": client_id,
            "code": result["code"], "redirect_uri": redirect_uri, "code_verifier": verifier})
        tokens.update({"client_id": client_id, "saved_at": int(time.time())})
        self._save(tokens)
        return {"ok": True, "expires_in": tokens.get("expires_in", 3600)}

    def status(self) -> dict:
        return self._authorized("GET", "/access")

    def request(self, *, plane: str, markets: list[str], label: str = "", use_case: str = "",
                mode: str = "standard", additional_reason: str = "",
                credential_mode: str = "account") -> dict:
        unknown = [market for market in markets if market not in MARKETS]
        if unknown:
            raise ValueError(f"unknown market slug(s): {', '.join(unknown)}")
        return self._authorized("POST", "/access", {"plane": plane, "markets": markets,
            "use_case": use_case, "mode": mode,
            "additional_reason": additional_reason, "credential_mode": "account"})

    def admin_requests(self) -> dict:
        return self._authorized("GET", "/admin/access/requests")

    def admin_decide(self, request_id: str, decision: str, markets: list[str] | None = None) -> dict:
        body: dict = {"decision": decision}
        if markets is not None:
            unknown = [market for market in markets if market not in MARKETS]
            if unknown:
                raise ValueError(f"unknown market slug(s): {', '.join(unknown)}")
            body["markets"] = markets
        return self._authorized("POST", f"/admin/access/requests/{request_id}", body)

    def admin_apply(self, request_id: str) -> dict:
        return self._authorized("POST", f"/admin/access/requests/{request_id}/apply", {})

    def _authorized(self, method: str, path: str, body: dict | None = None) -> dict:
        tokens = self._load()
        if not tokens:
            raise RuntimeError("Run `qjtrader login` first. Trading API keys are intentionally not admin credentials.")
        try:
            return self._json(method, path, body, bearer=tokens["access_token"])
        except HTTPError as exc:
            if exc.code != 401 or not tokens.get("refresh_token"):
                raise
            fresh = self._form("/token", {"grant_type": "refresh_token", "client_id": tokens["client_id"], "refresh_token": tokens["refresh_token"]})
            tokens.update(fresh); tokens["saved_at"] = int(time.time()); self._save(tokens)
            return self._json(method, path, body, bearer=tokens["access_token"])

    def _json(self, method: str, path: str, body: dict | None = None, bearer: str = "") -> dict:
        data = None if body is None else json.dumps(body).encode()
        headers = {"content-type": "application/json"}
        if bearer: headers["authorization"] = f"Bearer {bearer}"
        with urlopen(Request(self.base_url + path, data=data, headers=headers, method=method), timeout=30) as response:
            return json.loads(response.read())

    def _form(self, path: str, values: dict[str, str]) -> dict:
        with urlopen(Request(self.base_url + path, data=urlencode(values).encode(),
            headers={"content-type": "application/x-www-form-urlencoded"}, method="POST"), timeout=30) as response:
            return json.loads(response.read())

    def _load(self) -> dict:
        try: return json.loads(self.token_file.read_text(encoding="utf-8"))
        except (OSError, ValueError): return {}

    def _save(self, tokens: dict) -> None:
        self.token_file.parent.mkdir(parents=True, exist_ok=True)
        self.token_file.write_text(json.dumps(tokens, indent=2), encoding="utf-8")
        try: os.chmod(self.token_file, 0o600)
        except OSError: pass


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
