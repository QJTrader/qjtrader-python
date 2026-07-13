"""Background run registry — the control plane for hosted/local strategy runs
(plan §10.3 rung 2). Manages long-lived strategy runs (start/stop/status) in
daemon threads; the MCP's ``start_paper_run``/``stop_run``/``run_status`` and a
future hosted runner both drive it.

The heavy hosting (24/7 QJ compute, isolation, secrets) is the deploy concern; this
is the process-local manager that models it and is fully testable with a fake
runner. A paper run is zero-risk (simulated fills), so 'hosted paper' delivers the
product moment — "my AI's strategy has been paper-trading for a week; I watch it
from my phone" — without the hard parts of hosted *live* execution.
"""
from __future__ import annotations

import threading
import time
from typing import Any, Callable

from .run import run_strategy_live


class RunRegistry:
    def __init__(self, runner: Callable[..., None] = run_strategy_live,
                 clock: Callable[[], float] = time.time) -> None:
        self._runner = runner
        self._clock = clock
        self._runs: dict[str, dict[str, Any]] = {}
        self._seq = 0
        self._lock = threading.Lock()

    def start(self, client: Any, strategy: Any, *, symbols: list[str],
              params: dict[str, Any] | None = None, tag: str | None = None,
              account: str = "") -> dict[str, Any]:
        with self._lock:
            self._seq += 1
            run_id = f"run-{self._seq}"
        stop = threading.Event()
        rec = {"id": run_id, "symbols": symbols, "tag": tag or run_id,
               "status": "starting", "started": self._clock(), "error": None,
               "_stop": stop, "_thread": None}
        self._runs[run_id] = rec

        def _target() -> None:
            rec["status"] = "running"
            try:
                self._runner(client, strategy, symbols=symbols, params=params or {},
                             account=account, strategy_tag=rec["tag"], stop=stop)
                rec["status"] = "stopped"
            except Exception as e:  # surface the failure in status, don't crash the host
                rec["status"] = "error"
                rec["error"] = str(e)

        t = threading.Thread(target=_target, daemon=True, name=run_id)
        rec["_thread"] = t
        t.start()
        return self.status(run_id)

    def stop(self, run_id: str) -> dict[str, Any]:
        rec = self._runs.get(run_id)
        if rec is None:
            return {"error": f"unknown run {run_id}"}
        rec["_stop"].set()
        rec["status"] = "stopping" if rec["status"] == "running" else rec["status"]
        return self.status(run_id)

    def stop_all(self) -> None:
        for rec in self._runs.values():
            rec["_stop"].set()

    def _public(self, rec: dict[str, Any]) -> dict[str, Any]:
        return {k: v for k, v in rec.items() if not k.startswith("_")}

    def status(self, run_id: str | None = None) -> dict[str, Any]:
        if run_id is not None:
            rec = self._runs.get(run_id)
            return self._public(rec) if rec else {"error": f"unknown run {run_id}"}
        return {"runs": [self._public(r) for r in self._runs.values()]}
