#!/usr/bin/env python3
"""E4 - fresh-install smoke test for the *published* QJ packages.

Proves that a real user's `pip install qjtrader` (and `qjtrader-mcp`) gives them
the same surface our dev checkout has - the exact class of bug that started the
remediation ("your machine runs 0.3.1, PyPI ships 0.3.0 without prove()").

What it does, in a throwaway virtualenv (never touches your dev env):
  1. installs `qjtrader` (+ `qjtrader-mcp`) from PyPI at a target version,
  2. asserts the installed version matches and the agent-facing API surface is
     present - including `quote`, `expiries`, `chain`, `chain_stats`, `prove`,
  3. asserts `qjtrader_mcp` imports and exposes its `main` entry point,
  4. OPTIONAL: if QJ_CLIENT_ID / QJ_CLIENT_SECRET are set, runs a real
     `Client.prove()` against production and asserts the order lifecycle.

Usage:
  python scripts/smoke_published.py                    # latest on PyPI
  python scripts/smoke_published.py --sdk 0.3.1        # pin the SDK version
  python scripts/smoke_published.py --sdk 0.3.1 --mcp 0.2.0
  python scripts/smoke_published.py --no-mcp           # SDK only
  QJ_CLIENT_ID=... QJ_CLIENT_SECRET=... python scripts/smoke_published.py --live

Exit code 0 = all checks passed; non-zero = something a real user would hit.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import urllib.request

# The methods the onboarding brief tells an agent to call. If any of these is
# missing from the *installed* package, a fresh user's flow breaks.
REQUIRED_SDK_METHODS = [
    "quote", "expiries", "chain", "chain_stats", "prove", "events",
    "market_data", "orders", "history", "stats", "positions",
]


def latest_on_pypi(pkg: str) -> str:
    with urllib.request.urlopen(f"https://pypi.org/pypi/{pkg}/json", timeout=30) as r:
        return json.load(r)["info"]["version"]


def venv_python(venv_dir: str) -> str:
    # Windows: <venv>/Scripts/python.exe ; POSIX: <venv>/bin/python
    win = os.path.join(venv_dir, "Scripts", "python.exe")
    return win if os.path.exists(win) else os.path.join(venv_dir, "bin", "python")


def run(cmd: list[str], label: str | None = None, **kw) -> subprocess.CompletedProcess:
    # For inline `python -c <source>` calls, print a short label, not the source.
    shown = label or " ".join(cmd)
    print("  $", shown)
    return subprocess.run(cmd, text=True, capture_output=True, **kw)


# The check that runs *inside* the fresh venv. Prints "OK <json>" or raises.
IN_VENV_CHECK = r"""
import json, sys
result = {"checks": []}

import qjtrader
from qjtrader import Client
result["sdk_version"] = getattr(qjtrader, "__version__", "?")

required = json.loads(sys.argv[1])
missing = [m for m in required if not callable(getattr(Client, m, None))]
result["missing_sdk_methods"] = missing

want_mcp = sys.argv[2] == "1"
if want_mcp:
    import qjtrader_mcp
    result["mcp_version"] = getattr(qjtrader_mcp, "__version__", "?")
    result["mcp_has_main"] = callable(getattr(qjtrader_mcp, "main", None))

ok = not missing and (not want_mcp or result.get("mcp_has_main"))
print("RESULT " + json.dumps(result))
sys.exit(0 if ok else 1)
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sdk", default=None, help="qjtrader version (default: latest on PyPI)")
    ap.add_argument("--mcp", default=None, help="qjtrader-mcp version (default: latest on PyPI)")
    ap.add_argument("--no-mcp", action="store_true", help="skip the MCP package")
    ap.add_argument("--live", action="store_true",
                    help="also run a real Client.prove() (needs QJ_CLIENT_ID/SECRET)")
    ap.add_argument("--symbol", default="CA:RY", help="symbol for the live prove()")
    args = ap.parse_args()

    sdk_ver = args.sdk or latest_on_pypi("qjtrader")
    want_mcp = not args.no_mcp
    mcp_ver = args.mcp or (latest_on_pypi("qjtrader-mcp") if want_mcp else None)

    print(f"E4 smoke test - SDK qjtrader=={sdk_ver}"
          + (f", MCP qjtrader-mcp=={mcp_ver}" if want_mcp else " (no MCP)"))

    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="qj-smoke-") as tmp:
        venv_dir = os.path.join(tmp, "venv")
        print(f"[1/3] creating clean venv at {venv_dir}")
        cp = run([sys.executable, "-m", "venv", venv_dir])
        if cp.returncode != 0:
            print(cp.stderr); return 2
        py = venv_python(venv_dir)
        run([py, "-m", "pip", "install", "--quiet", "--upgrade", "pip"])

        print("[2/3] installing published packages from PyPI")
        pkgs = [f"qjtrader=={sdk_ver}"]
        if want_mcp:
            pkgs.append(f"qjtrader-mcp=={mcp_ver}")
        cp = run([py, "-m", "pip", "install", "--quiet"] + pkgs)
        if cp.returncode != 0:
            print(cp.stdout); print(cp.stderr)
            failures.append("pip install failed")
            print("\nFAIL:", *failures, sep="\n  - "); return 1

        print("[3/3] checking installed surface")
        cp = run([py, "-c", IN_VENV_CHECK, json.dumps(REQUIRED_SDK_METHODS),
                  "1" if want_mcp else "0"], label="python -c <surface-check>")
        line = next((l for l in cp.stdout.splitlines() if l.startswith("RESULT ")), None)
        info = json.loads(line[len("RESULT "):]) if line else {}
        print("  installed:", json.dumps(info))
        if info.get("sdk_version") != sdk_ver:
            failures.append(f"SDK version mismatch: got {info.get('sdk_version')}, want {sdk_ver}")
        if info.get("missing_sdk_methods"):
            failures.append(f"SDK missing methods: {info['missing_sdk_methods']}")
        if want_mcp and not info.get("mcp_has_main"):
            failures.append("MCP package missing main entry point")

        # uv / uvx is how the brief tells users to run the MCP server.
        uv = _which("uv") or _which("uvx")
        print("  uv/uvx available:", bool(uv), f"({uv})" if uv else "")

        if args.live:
            print("[live] running a real Client.prove() against production")
            if not (os.environ.get("QJ_CLIENT_ID") and os.environ.get("QJ_CLIENT_SECRET")):
                failures.append("--live given but QJ_CLIENT_ID/QJ_CLIENT_SECRET not set")
            else:
                live = run([py, "-c", _LIVE_PROVE, args.symbol],
                           label="python -c <live-prove>", env={**os.environ})
                print(live.stdout.strip())
                if live.returncode != 0:
                    print(live.stderr)
                    failures.append("live prove() failed")

    print()
    if failures:
        print("FAIL:")
        for f in failures:
            print("  -", f)
        return 1
    print("PASS - a fresh `pip install` gets the full published surface"
          + (" and a live prove() lifecycle" if args.live else "") + ".")
    return 0


def _which(name: str) -> str | None:
    from shutil import which
    return which(name)


_LIVE_PROVE = r"""
import json, sys
from qjtrader import Client
out = Client().prove(sys.argv[1])
statuses = [m.get("status") for m in out.get("lifecycle", [])]
print("  prove() cid=%s statuses=%s journal=%d"
      % (out.get("cid"), statuses, len(out.get("journal", []))))
sys.exit(0 if ("new" in statuses and "canceled" in statuses) else 1)
"""


if __name__ == "__main__":
    raise SystemExit(main())
