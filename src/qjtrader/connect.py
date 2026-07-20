"""QJ Connect lifecycle reporting for local strategy processes.

The module is dormant for ordinary SDK users. QJ Connect supplies the environment
variables at process launch; the key remains in the OS vault and is never written
into the strategy project.
"""
from __future__ import annotations

import json
import os
import threading
import urllib.error
import urllib.request
from typing import Any

from .auth import TokenSource
from .client import DEFAULT_TOKEN_URL, MARKET_DATA_SCOPE, ORDERS_SCOPE
from .errors import QJError


class ConnectReporter:
    def __init__(self, api_url: str, computer_id: str, client_id: str,
                 client_secret: str, token_url: str = DEFAULT_TOKEN_URL) -> None:
        self.api_url = api_url.rstrip("/")
        self.computer_id = computer_id
        self.tokens = TokenSource(token_url, client_id, client_secret,
                                  f"{MARKET_DATA_SCOPE} {ORDERS_SCOPE}")
        self._thread: threading.Thread | None = None
        self._finished = threading.Event()

    @classmethod
    def from_environment(cls) -> "ConnectReporter | None":
        api_url = os.environ.get("QJ_CONNECT_API_URL", "").strip()
        computer_id = os.environ.get("QJ_COMPUTER_ID", "").strip()
        if not api_url and not computer_id:
            return None
        required = {
            "QJ_CONNECT_API_URL": api_url,
            "QJ_COMPUTER_ID": computer_id,
            "QJ_CLIENT_ID": os.environ.get("QJ_CLIENT_ID", ""),
            "QJ_CLIENT_SECRET": os.environ.get("QJ_CLIENT_SECRET", ""),
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise QJError(f"QJ Connect launch is missing {', '.join(missing)}")
        return cls(api_url, computer_id, required["QJ_CLIENT_ID"],
                   required["QJ_CLIENT_SECRET"],
                   os.environ.get("QJ_TOKEN_URL", DEFAULT_TOKEN_URL))

    def _request(self, route: str, body: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(
            f"{self.api_url}{route}",
            data=json.dumps(body).encode(),
            headers={"Authorization": f"Bearer {self.tokens.token()}",
                     "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", "replace")[:300]
            raise QJError(f"QJ Connect lifecycle request failed (HTTP {error.code}): {detail}") from None
        except urllib.error.URLError as error:
            raise QJError(f"QJ Connect lifecycle request failed: {error.reason}") from None

    def start(self, *, run_id: str, strategy_id: str, display_name: str,
              version_hash: str, symbols: list[str], stop: threading.Event) -> None:
        self._request("/v1/strategies", {
            "strategy_id": strategy_id, "computer_id": self.computer_id,
            "display_name": display_name, "version_hash": version_hash,
            "symbols": symbols, "explanation": "Local Python strategy managed by QJ Connect.",
        })
        self._request("/v1/runs", {
            "run_id": run_id, "strategy_id": strategy_id,
            "computer_id": self.computer_id, "display_name": display_name,
            "version_hash": version_hash, "pid_hint": str(os.getpid()),
        })

        def heartbeat() -> None:
            while not self._finished.wait(5):
                try:
                    result = self._request(f"/v1/runs/{run_id}/heartbeat", {"summary": "strategy process healthy"})
                    if result.get("stop_requested"):
                        stop.set()
                        return
                except QJError:
                    # The server lease will turn the run to lost. Keep the strategy process
                    # alive through a temporary network interruption and try again.
                    continue

        self._thread = threading.Thread(target=heartbeat, name="qj-connect-heartbeat", daemon=True)
        self._thread.start()

    def finish(self, run_id: str, *, failed: bool = False, reason: str = "") -> None:
        self._finished.set()
        if self._thread:
            self._thread.join(timeout=1)
        self._request(f"/v1/runs/{run_id}/finish", {
            "state": "failed" if failed else "stopped", "reason": reason,
        })
