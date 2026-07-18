"""Small cross-process control record for strategies running on this device."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def runs_dir(root: str | Path | None = None) -> Path:
    path = Path(root) if root else Path.home() / ".qjtrader" / "runs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def record(run_id: str, data: dict, *, root: str | Path | None = None) -> dict:
    current = get(run_id, root=root) or {}
    current.update(data)
    current.update({"id": run_id, "updated_at": datetime.now(timezone.utc).isoformat()})
    (runs_dir(root) / f"{run_id}.json").write_text(json.dumps(current, indent=2), encoding="utf-8")
    return current


def get(run_id: str, *, root: str | Path | None = None) -> dict | None:
    try:
        return json.loads((runs_dir(root) / f"{run_id}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def list_runs(*, root: str | Path | None = None) -> list[dict]:
    values = []
    for path in runs_dir(root).glob("*.json"):
        try: values.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError): pass
    return sorted(values, key=lambda item: str(item.get("updated_at", "")), reverse=True)


def request_stop(run_id: str, *, root: str | Path | None = None) -> dict:
    current = get(run_id, root=root)
    if not current:
        return {"error": f"unknown local run {run_id}"}
    (runs_dir(root) / f"{run_id}.stop").touch()
    return record(run_id, {"status": "stop requested"}, root=root)


def stop_requested(run_id: str, *, root: str | Path | None = None) -> bool:
    return (runs_dir(root) / f"{run_id}.stop").exists()


def clear_stop(run_id: str, *, root: str | Path | None = None) -> None:
    (runs_dir(root) / f"{run_id}.stop").unlink(missing_ok=True)
