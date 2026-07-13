"""Hosted paper-runner service (plan §10.3 rung 2, S5). A long-lived process that
runs a set of strategies unattended against **paper** credentials and reports their
status — the deployable shell over `RunRegistry`. Containerize it and you have the
"my AI's strategy has been paper-trading for a week, I watch it from my phone"
product moment, without any of the hard parts of hosted *live* execution (paper is
zero-risk).

Config (JSON): a list of run specs —

    [{"name": "mr1", "autoTool": "scalper", "symbols": ["MX:CRAU26"],
      "params": {"edge": 0.02}, "clientId": "...", "clientSecret": "..."},
     {"name": "mine", "strategyFile": "s.py", "symbols": ["CA:RY"], "clientId": "..."}]

Credentials come from the spec or QJ_CLIENT_ID/SECRET env. Run:
    qjtrader-runner runs.json
"""
from __future__ import annotations

import json
import signal
import sys
import threading
import time
from typing import Any, Callable

from .autotools import make_auto_tool
from .client import Client
from .errors import QJError
from .run import load_strategy
from .runner import RunRegistry
from .strategy import Strategy


def _strategy_for(spec: dict[str, Any]) -> Strategy:
    if spec.get("strategyFile"):
        return load_strategy(str(spec["strategyFile"]))
    if spec.get("autoTool"):
        return make_auto_tool(str(spec["autoTool"]))
    raise QJError(f"run spec {spec.get('name')!r} needs 'autoTool' or 'strategyFile'")


def _client_for(spec: dict[str, Any]) -> Client:
    return Client(client_id=spec.get("clientId"), client_secret=spec.get("clientSecret"))


class RunnerService:
    def __init__(self, registry: RunRegistry | None = None, *,
                 make_client: Callable[[dict], Any] = _client_for,
                 make_strategy: Callable[[dict], Strategy] = _strategy_for) -> None:
        self.registry = registry or RunRegistry()
        self._make_client = make_client
        self._make_strategy = make_strategy
        self.names: dict[str, str] = {}  # run_id -> spec name

    def start_spec(self, spec: dict[str, Any]) -> dict[str, Any]:
        strat = self._make_strategy(spec)
        client = self._make_client(spec)
        params = dict(spec.get("params") or {})
        symbols = list(spec.get("symbols") or [])
        params.setdefault("symbol", symbols[0] if symbols else None)
        st = self.registry.start(client, strat, symbols=symbols, params=params,
                                 tag=str(spec.get("name") or "run"),
                                 account=str(spec.get("account") or ""))
        self.names[st["id"]] = str(spec.get("name") or st["id"])
        return st

    def start_all(self, specs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out = []
        for spec in specs:
            try:
                out.append(self.start_spec(spec))
            except (QJError, KeyError, FileNotFoundError) as e:
                out.append({"error": str(e), "name": spec.get("name")})
        return out

    def status(self) -> dict[str, Any]:
        s = self.registry.status()
        for r in s.get("runs", []):
            r["name"] = self.names.get(r["id"], r["id"])
        return s

    def stop_all(self) -> None:
        self.registry.stop_all()


def load_config(path: str) -> list[dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise QJError("runner config must be a JSON array of run specs")
    return data


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print("usage: qjtrader-runner <config.json>", file=sys.stderr)
        return 2
    try:
        specs = load_config(args[0])
    except (OSError, QJError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    svc = RunnerService()
    stop = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    started = svc.start_all(specs)
    print(f"# started {len([s for s in started if 'error' not in s])}/{len(specs)} runs; "
          f"Ctrl-C to stop", file=sys.stderr)
    try:
        while not stop.is_set():
            print(json.dumps(svc.status()))
            stop.wait(30.0)
    finally:
        svc.stop_all()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
