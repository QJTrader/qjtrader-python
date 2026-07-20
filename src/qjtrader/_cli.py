"""Command-line interface: ``qjtrader <command>``.

Credentials come from QJ_CLIENT_ID / QJ_CLIENT_SECRET (or --client-id/--secret).

    export QJ_CLIENT_ID=... QJ_CLIENT_SECRET=...
    qjtrader subscribe CA:RY MX:CRAU26 US:@ESU26 --watch 30
    qjtrader order --sym MX:CRAU26 --side buy --qty 1 --price 97.00 --account SIM --tif ioc
    qjtrader status
"""
from __future__ import annotations

import argparse
import json
import sys

from . import __version__
from .client import Client
from .errors import ConnectionClosed, QJError


def _client(a: argparse.Namespace) -> Client:
    options = dict(
        client_id=a.client_id, client_secret=a.client_secret,
        token_url=a.token_url, data_host=a.data_host, orders_host=a.orders_host,
        ca_file=a.ca, verify=not a.insecure,
    )
    if a.env_file:
        return Client.from_env_file(a.env_file, **options)
    return Client(**options)


def _common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--env-file", help="ACL-restricted QJ machine credential file (never a human password)")
    p.add_argument("--client-id")
    p.add_argument("--client-secret")
    p.add_argument("--token-url")
    p.add_argument("--data-host")
    p.add_argument("--orders-host")
    p.add_argument("--ca", help="CA/cert file to pin (pilot order endpoint)")
    p.add_argument("--insecure", action="store_true", help="skip TLS verification (dev only)")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="qjtrader", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--version", action="version", version=f"qjtrader {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("init", help="create one safe local strategy project")
    pi.add_argument("path", nargs="?", default="qj-strategy")
    pi.add_argument("--symbol", default="CA:RY")
    pi.add_argument("--force", action="store_true")

    sub.add_parser("login", help="sign in as a QJ Gateway user in your browser")
    sub.add_parser("access-status", help="show live data, order entry, and pending requests")

    pa = sub.add_parser("access-request", help="open the human-approved production access request")
    pa.add_argument("--plane", choices=["data", "orders"], default="data")
    pa.add_argument("--market", action="append", default=[], choices=[
        "ca-equities", "ca-futures", "ca-options", "us-equities", "us-futures", "us-options",
    ], help="least-privilege market entitlement (repeatable)")
    pa.add_argument("--label", default="", help=argparse.SUPPRESS)
    pa.add_argument("--use-case", default="")
    pa.add_argument("--additional-reason", default="", help="request another trading account or additional market-data depth")
    pa.add_argument("--extend", action="store_true", help=argparse.SUPPRESS)
    pa.add_argument("--handoff", action="store_true", help="use the browser request form instead of the signed-in API")
    pa.add_argument("--no-open", action="store_true", help="print the URL without opening a browser")
    plr = sub.add_parser("limit-request", help="request a production cloud API safety-limit change")
    plr.add_argument("--client-id", default="", help="production key id (omit when only one is active)")
    plr.add_argument("--product", required=True, choices=[
        "ca-equities", "ca-futures", "ca-options", "us-equities", "us-futures", "us-options",
    ])
    plr.add_argument("--max-qty", type=int)
    plr.add_argument("--max-open", type=int)
    plr.add_argument("--msgs-per-sec", type=float)
    plr.add_argument("--daily-qty", type=int)
    plr.add_argument("--reason", default="")
    paa = sub.add_parser("access-admin", help="open one request in an authenticated admin Gateway session")
    paa.add_argument("request_id", help="QJ production request id")
    paa.add_argument("--no-open", action="store_true", help="print the URL without opening a browser")
    pal = sub.add_parser("access-admin-list", help="list access decisions requiring an administrator")
    pad = sub.add_parser("access-admin-decide", help="record a human administrator decision")
    pad.add_argument("request_id"); pad.add_argument("decision", choices=["approved", "rejected", "pending"])
    pad.add_argument("--market", action="append", default=None, choices=[
        "ca-equities", "ca-futures", "ca-options", "us-equities", "us-futures", "us-options",
    ], help="approved market subset (repeatable; defaults to all requested markets)")
    pap = sub.add_parser("access-admin-apply", help="provision an approved data request; order entry opens guided setup")
    pap.add_argument("request_id")

    ps = sub.add_parser("subscribe", help="stream market data for symbols")
    ps.add_argument("symbols", nargs="+", help="e.g. CA:RY MX:CRAU26 US:@ESU26")
    ps.add_argument("--depth", type=int)
    ps.add_argument("--watch", type=float, default=60.0)
    _common(ps)

    po = sub.add_parser("order", help="submit a limit order")
    po.add_argument("--sym", required=True)
    po.add_argument("--side", required=True, choices=["buy", "sell"])
    po.add_argument("--qty", type=int, required=True)
    po.add_argument("--price", type=float, required=True)
    po.add_argument("--tif", default="day", choices=["day", "ioc", "fok"])
    po.add_argument("--account", default="")
    po.add_argument("--iceberg", type=int, default=0)
    po.add_argument("--cid")
    po.add_argument("--venue", help="Canadian equity route, e.g. TO, PT, LY, TL, SOR, DARK")
    po.add_argument("--watch", type=float, default=15.0)
    _common(po)

    pc = sub.add_parser("cancel", help="cancel an order by its cid")
    pc.add_argument("--orig", required=True)
    pc.add_argument("--watch", type=float, default=10.0)
    _common(pc)

    pst = sub.add_parser("status", help="show open orders + session state")
    _common(pst)
    pca = sub.add_parser("cancel-all", help="cancel every open order")
    _common(pca)

    pb = sub.add_parser("backtest", help="run a strategy file over synthetic/offline bars")
    pb.add_argument("strategy", help="path to a .py file with a Strategy subclass")
    pb.add_argument("--symbol", required=True, help="e.g. MX:CRAU26")
    pb.add_argument("--bars", type=int, default=390, help="number of synthetic bars")
    pb.add_argument("--interval", type=int, default=60, help="bar seconds")
    pb.add_argument("--seed", type=int, help="synthetic seed (reproducible day)")
    pb.add_argument("--param", action="append", default=[],
                    help="strategy param key=value (repeatable)")

    pr = sub.add_parser("run", help="run a strategy against a live/paper credential")
    pr.add_argument("strategy", help="path to a .py file with a Strategy subclass")
    pr.add_argument("--symbols", nargs="+", required=True)
    pr.add_argument("--tag", default="strat", help="strategy tag on every order")
    pr.add_argument("--run-id", help="recognizable local run id (auto-generated when omitted)")
    pr.add_argument("--account", default="")
    pr.add_argument("--param", action="append", default=[])
    _common(pr)
    sub.add_parser("runs", help="list strategies running or recently stopped on this device")
    psr = sub.add_parser("stop-run", help="safely stop a local strategy by run id")
    psr.add_argument("run_id")

    a = p.parse_args(argv)
    if a.cmd == "init":
        from .scaffold import create_strategy_project
        try:
            files = create_strategy_project(a.path, symbol=a.symbol, force=a.force)
        except (OSError, FileExistsError) as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        print(json.dumps({"created": files, "next": f"qjtrader backtest {a.path}/strategy.py --symbol {a.symbol}"}, indent=2))
        return 0
    if a.cmd == "login":
        from .access import AccessClient
        print(json.dumps(AccessClient().login(), indent=2))
        return 0
    if a.cmd == "access-status":
        from .access import AccessClient
        print(json.dumps(AccessClient().status(), indent=2))
        return 0
    if a.cmd == "access-request":
        import webbrowser
        from .access import AccessClient, production_access_url
        if not a.handoff and not a.no_open:
            try:
                result = AccessClient().request(plane=a.plane, markets=a.market, label=a.label,
                    use_case=a.use_case, mode="additional" if a.additional_reason else "standard",
                    additional_reason=a.additional_reason,
                    credential_mode="account")
                print(json.dumps(result, indent=2)); return 0
            except RuntimeError as e:
                print(f"error: {e}", file=sys.stderr); return 1
        url = production_access_url(plane=a.plane, markets=a.market, label=a.label)
        print(url)
        if not a.no_open:
            webbrowser.open(url)
        return 0
    if a.cmd == "limit-request":
        from .access import AccessClient
        try:
            result = AccessClient().request_limit_change(
                client_id=a.client_id, product=a.product, max_qty=a.max_qty,
                max_open=a.max_open, msgs_per_sec=a.msgs_per_sec,
                daily_qty=a.daily_qty, reason=a.reason)
        except (RuntimeError, ValueError, OSError) as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        print(json.dumps(result, indent=2))
        return 0
    if a.cmd in {"access-admin-list", "access-admin-decide", "access-admin-apply"}:
        from .access import AccessClient
        control = AccessClient()
        if a.cmd == "access-admin-list": result = control.admin_requests()
        elif a.cmd == "access-admin-decide": result = control.admin_decide(a.request_id, a.decision, a.market)
        else: result = control.admin_apply(a.request_id)
        print(json.dumps(result, indent=2)); return 0
    if a.cmd == "access-admin":
        import webbrowser
        from .access import admin_access_url
        try:
            url = admin_access_url(a.request_id)
        except ValueError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        print(url)
        if not a.no_open:
            webbrowser.open(url)
        return 0
    if a.cmd == "backtest":
        return _cmd_backtest(a)
    if a.cmd == "run":
        return _cmd_run(a)
    if a.cmd == "runs":
        from .local_runs import list_runs
        print(json.dumps({"runs": list_runs()}, indent=2)); return 0
    if a.cmd == "stop-run":
        from .local_runs import request_stop
        result = request_stop(a.run_id); print(json.dumps(result, indent=2))
        return 1 if "error" in result else 0
    try:
        client = _client(a)
        if a.cmd == "subscribe":
            with client.market_data() as md:
                print(f"# authenticated as {md.user}; subscribing {a.symbols}", file=sys.stderr)
                md.subscribe(a.symbols, depth=a.depth)
                try:
                    for msg in md.messages(timeout=a.watch):
                        print(json.dumps(msg))
                except ConnectionClosed:
                    print("# server closed the connection", file=sys.stderr)
        elif a.cmd == "order":
            with client.orders() as oe:
                print(f"# authenticated as {oe.user}", file=sys.stderr)
                cid = oe.order(sym=a.sym, side=a.side, qty=a.qty, price=a.price,
                               tif=a.tif, account=a.account, iceberg=a.iceberg, cid=a.cid,
                               venue=a.venue)
                print(f"# submitted cid={cid}", file=sys.stderr)
                _drain(oe, a.watch)
        elif a.cmd == "cancel":
            with client.orders() as oe:
                oe.cancel(a.orig)
                _drain(oe, a.watch)
        elif a.cmd == "cancel-all":
            with client.orders() as oe:
                oe.cancel_all()
                _drain(oe, 5.0)
        elif a.cmd == "status":
            with client.orders() as oe:
                print(json.dumps(oe.status(), indent=2))
    except QJError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


def _parse_params(items: list[str]) -> dict:
    out: dict = {}
    for it in items:
        k, _, v = it.partition("=")
        try:
            out[k] = json.loads(v)      # numbers/bools/JSON pass through
        except ValueError:
            out[k] = v                   # plain string
    return out


def _load_strategy_or_autotool(spec: str):
    """A .py file path, or the name of a built-in auto-tool (e.g. 'scalper')."""
    from .autotools import REGISTRY, make_auto_tool
    from .run import load_strategy
    if spec in REGISTRY:
        return make_auto_tool(spec)
    return load_strategy(spec)


def _cmd_backtest(a: argparse.Namespace) -> int:
    from .backtest import run_backtest, synthetic_bars
    try:
        strat = _load_strategy_or_autotool(a.strategy)
    except QJError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    bars = synthetic_bars(a.symbol, a.bars, interval_s=a.interval, seed=a.seed)
    params = _parse_params(a.param)
    params.setdefault("symbol", a.symbol)     # so auto-tools scope to the tested symbol
    report = run_backtest(strat, bars, params=params)
    report.pop("equity_curve", None)     # keep stdout compact; PnL summary remains
    print(json.dumps(report, indent=2, default=str))
    return 0


def _cmd_run(a: argparse.Namespace) -> int:
    import signal
    import threading

    import uuid
    from .local_runs import clear_stop, record, stop_requested
    from .connect import ConnectReporter
    from .run import run_strategy_live, strategy_version
    stop = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    run_id = a.run_id or f"local-{uuid.uuid4().hex[:10]}"
    clear_stop(run_id)
    record(run_id, {"status": "starting", "strategy": a.strategy, "symbols": a.symbols, "tag": a.tag})
    def watch_stop():
        while not stop.wait(0.5):
            if stop_requested(run_id): stop.set()
    threading.Thread(target=watch_stop, daemon=True).start()
    reporter = None
    failed = False
    terminal_reason = "stopped safely"
    try:
        client = _client(a)
        strategy = _load_strategy_or_autotool(a.strategy)
        params = _parse_params(a.param)
        version = strategy_version(strategy, params)
        reporter = ConnectReporter.from_environment()
        if reporter:
            reporter.start(run_id=run_id, strategy_id=a.tag, display_name=a.tag,
                           version_hash=version, symbols=a.symbols, stop=stop)
        record(run_id, {"status": "running"})
        print(f"# run {run_id}: {a.strategy} on {a.symbols} (tag={a.tag}); Ctrl-C or `qjtrader stop-run {run_id}` to stop",
              file=sys.stderr)
        run_strategy_live(client, strategy, symbols=a.symbols,
                          params=params, account=a.account,
                          strategy_tag=a.tag, stop=stop, run_id=run_id)
    except QJError as e:
        failed = True
        terminal_reason = str(e)
        record(run_id, {"status": "error", "error": str(e)})
        print(f"error: {e}", file=sys.stderr)
        return 1
    finally:
        if reporter:
            try:
                reporter.finish(run_id, failed=failed, reason=terminal_reason)
            except QJError as report_error:
                print(f"# QJ Connect status warning: {report_error}", file=sys.stderr)
        if stop.is_set(): record(run_id, {"status": "stopped"})
        clear_stop(run_id)
    return 0


def _drain(oe: object, watch: float) -> None:
    try:
        for msg in oe.updates(timeout=watch):  # type: ignore[attr-defined]
            print(json.dumps(msg))
            if msg.get("type") == "order_update" and msg.get("status") in (
                "filled", "canceled", "rejected", "replaced",
            ):
                return
            if msg.get("type") == "exec" and msg.get("status") == "filled":
                return
    except ConnectionClosed:
        print("# connection closed", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
