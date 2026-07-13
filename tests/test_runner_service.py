"""Hosted paper-runner service (plan §10.3 rung 2 / S5)."""
import json
import threading
import time

from qjtrader import RunRegistry, RunnerService


def _fake_runner_factory():
    started = []

    def runner(client, strategy, *, symbols, params, account, strategy_tag, stop):
        started.append({"tag": strategy_tag, "symbols": symbols, "params": params})
        stop.wait(timeout=2.0)

    return runner, started


def test_service_starts_specs_from_config(tmp_path):
    runner, started = _fake_runner_factory()
    svc = RunnerService(
        RunRegistry(runner=runner),
        make_client=lambda spec: object(),  # no real client
    )
    specs = [
        {"name": "mr1", "autoTool": "scalper", "symbols": ["MX:CRAU26"], "params": {"edge": 0.02}},
        {"name": "mr2", "autoTool": "scalper", "symbols": ["CA:RY"]},
    ]
    out = svc.start_all(specs)
    assert len(out) == 2 and all("id" in o for o in out)
    for _ in range(50):
        if len(started) == 2:
            break
        time.sleep(0.02)
    assert {s["tag"] for s in started} == {"mr1", "mr2"}
    # status reports both runs with their spec names
    st = svc.status()
    assert {r["name"] for r in st["runs"]} == {"mr1", "mr2"}
    svc.stop_all()


def test_service_bad_spec_is_reported_not_fatal(tmp_path):
    runner, _ = _fake_runner_factory()
    svc = RunnerService(RunRegistry(runner=runner), make_client=lambda spec: object())
    out = svc.start_all([{"name": "bad"}])  # no autoTool/strategyFile
    assert "error" in out[0]
    svc.stop_all()


def test_load_config(tmp_path):
    from qjtrader.runner_service import load_config
    p = tmp_path / "runs.json"
    p.write_text(json.dumps([{"name": "a", "autoTool": "scalper", "symbols": ["X"]}]))
    specs = load_config(str(p))
    assert specs[0]["name"] == "a"
