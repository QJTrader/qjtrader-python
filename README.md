# qjtrader

Hosted assistants should use the delegated OAuth connector from [QJ Gateway](https://gateway.qjtrader.ai), which keeps the trading client secret out of chat. This SDK remains the full programmatic client for Python services and local agents.

[![PyPI version](https://img.shields.io/pypi/v/qjtrader)](https://pypi.org/project/qjtrader/)
[![Python versions](https://img.shields.io/pypi/pyversions/qjtrader)](https://pypi.org/project/qjtrader/)
[![License](https://img.shields.io/pypi/l/qjtrader)](https://github.com/QJTrader/qjtrader-python/blob/main/LICENSE)

Official Python client for the **QJ Trader AI Trading APIs** — stream real-time Canadian and selected
US market data and send orders through entitled Canadian or US gateway accounts (Montréal Exchange derivatives, and equities across every
lit exchange and dark pool) over one authenticated connection.

```bash
pip install qjtrader
```

- **Free sandbox, no approval.** Create an account at [gateway.qjtrader.ai](https://gateway.qjtrader.ai),
  click *Create sandbox credential*, and you get a `client_id` + `client_secret` that stream
  **simulated** data and return **simulated** fills — in the *exact production wire format*, 24/7.
- **Sandbox → production without a code change.** Request licensed data and order authority
  independently. A human admin approves the scope, then separately provisions a dedicated
  least-privilege key; the SDK and sandbox credential cannot self-promote.
- **Stdlib only.** No dependencies — easy to install, easy to audit.
- **Verifiable releases.** Published straight from this repo via [PyPI Trusted
  Publishing](https://docs.pypi.org/trusted-publishers/) with signed [PEP 740](https://peps.python.org/pep-0740/)
  provenance — no manual uploads, no stored tokens. See [SECURITY.md](SECURITY.md) to verify a release.

## Quickstart

Get a sandbox key from the [console](https://gateway.qjtrader.ai), then:

```bash
export QJ_CLIENT_ID="your-client-id"
export QJ_CLIENT_SECRET="your-client-secret"
```

For a long-running service or coding agent, keep the dedicated machine credential outside the
repository in an ACL-restricted file:

```dotenv
QJ_CLIENT_ID=your-dedicated-client-id
QJ_CLIENT_SECRET=your-dedicated-client-secret
```

```python
client = qjtrader.Client.from_env_file("~/.qj/m3alpha-csu.env")
```

```bash
chmod 600 ~/.qj/m3alpha-csu.env
qjtrader subscribe CA:CSU CA:CSU.PT CA:CSU.TO --depth 5 --watch 30 \
  --env-file ~/.qj/m3alpha-csu.env
```

The SDK parses this file itself: it does not source shell expressions or copy secrets into the
process-wide environment. On Windows, restrict the file to your user with NTFS permissions. Never
store a Gateway password, MFA code, or human admin session in this file; it is only for a dedicated
OAuth machine credential. Production data and order credentials still require separate human
approval, and production order entry additionally requires an admin-selected existing trader
profile.

### Send an order

```python
import qjtrader

client = qjtrader.Client()  # reads QJ_CLIENT_ID / QJ_CLIENT_SECRET from the environment

with client.orders() as oe:
    fill = oe.order_and_wait(
        sym="MX:CRAU26", side="buy", qty=1, price=97.00, account="SIM", tif="ioc",
    )
    print(fill)   # {'type': 'exec', 'status': 'filled', 'last_px': 97.0, 'cum_qty': 1, ...}
```

Lower-level, if you want every message:

```python
with client.orders() as oe:
    cid = oe.order(sym="MX:CRAU26", side="buy", qty=1, price=97.00, account="SIM")
    for msg in oe.updates(timeout=10):
        print(msg)          # accepted -> new -> (partial)* -> filled | canceled | replaced
    oe.cancel(cid)
    print(oe.status())      # open orders + session state
```

### Stream market data

```python
import qjtrader

client = qjtrader.Client()

with client.market_data() as md:
    md.subscribe(["CA:RY", "CA:RY.PT", "MX:CRAU26", "US:@ESU26"], depth=5)
    for msg in md.messages(timeout=30):
        if msg["type"] == "quote":
            print(msg["symbol"], msg["data"]["bid"], msg["data"]["ask"])
```

- `CA:RY` is the **consolidated** Canadian equity book (each level tagged with its venue);
  `CA:RY.PT` is **PURE (CSE)** only. Futures like `MX:CRAU26` and selected US contracts such as
  `US:@ESU26` are venue-native. Production access remains product- and entitlement-specific. See the full
  [symbology reference](https://docs.qjtrader.ai/docs/ai/symbology).
- On real consolidated Canadian symbols, `md.quote("CA:RY")` waits for the official
  `cbbo=true` quote. Canadian external L2 is currently five-level price-aggregated depth—not an
  order-by-order D4 feed—and carries no order IDs or add/execute actions. `bids`/`asks` are the
  rounded Top5 book; additive `odd_lot_bids`/`odd_lot_asks` and
  `special_lot_bids`/`special_lot_asks` expose full displayed sizes by desktop book type and must
  not be summed into Top5.

### Check what is available

Coverage differs by product and entitlement, especially for US depth. The offline matrix requires
no credential or network connection:

```python
from qjtrader import market_availability

print(market_availability()["markets"]["US"])
```

Verified examples include AAPL L1, SPY L1/L2, and selected US futures L1/L2. AAPL depth, NDX,
and US listed-option depth are not currently available. See
[Market Availability](https://docs.qjtrader.ai/docs/ai/availability).

## Command line

The package installs a `qjtrader` command:

```bash
qjtrader init my-strategy --symbol MX:CRAU26
qjtrader login  # browser sign-in; separate from trading API keys
qjtrader access-status
qjtrader access-request --plane data --market ca-equities --label "M3alpha CSU shadow"
qjtrader access-admin-list
qjtrader access-admin-decide __prodreq__... approved --market ca-equities  # omit --market to approve the requested set
qjtrader access-admin-apply __prodreq__...  # data keys; orders return guided account setup
qjtrader subscribe CA:RY MX:CRAU26 US:@ESU26 --watch 30 --env-file ~/.qj/strategy.env
qjtrader order --sym MX:CRAU26 --side buy --qty 1 --price 97.00 --account SIM --tif ioc
qjtrader status
qjtrader cancel --orig qj-abc123

# strategies: the same file runs in backtest and live
qjtrader backtest examples/strategy_meanreversion.py --symbol MX:CRAU26 --bars 200
qjtrader run       examples/strategy_meanreversion.py --symbols MX:CRAU26 --tag mr1
qjtrader runs
qjtrader stop-run local-abc123
```

`qjtrader init` creates a small local project that observes by default and keeps order mutation
disabled until the user deliberately changes `allow_orders`. It is designed for a coding agent to
inspect, test, and run locally without adding a cloud IDE or another account-setup step.

## Strategies — one contract, every venue

Subclass `Strategy` and the same file runs in the backtest engine, a paper run, or
live (plan §10). Backtests are offline and deterministic (no network, no secrets);
`qjtrader run` hosts it against a live/paper credential, tags every order with the
strategy name, writes a local run record, and cancels working orders on Ctrl-C or
`qjtrader stop-run RUN_ID`. Access commands use browser-authenticated human identity;
ordinary trading credentials cannot approve or provision themselves.

```python
from qjtrader import Strategy, run_backtest, synthetic_bars

class Buy2Percent(Strategy):
    def on_bar(self, ctx, bar):
        if ctx.position(bar["symbol"]) == 0 and bar["close"] < ctx.param("floor", 0):
            ctx.buy(bar["symbol"], 1, bar["close"], tif="ioc")
    def on_fill(self, ctx, fill):
        ctx.log("filled", fill.get("cid"), "@", fill.get("last_px") or fill.get("price"))

report = run_backtest(Buy2Percent(), synthetic_bars("MX:CRAU26", 200), params={"floor": 95})
print(report["total_pnl"], report["positions"])
```

The bar-level backtester is for **logic**; L2 event-replay with queue-model fills
(microstructure truth) comes from the paper environment.

## Configuration

`Client()` reads these (constructor args override environment):

| Setting | Env var | Default |
|---|---|---|
| Client ID | `QJ_CLIENT_ID` | — (required) |
| Client secret | `QJ_CLIENT_SECRET` | — (required) |
| Token endpoint | `QJ_TOKEN_URL` | QJ Cognito token URL |
| Market-data host | `QJ_DATA_HOST` | `data-feed.qjtrader.ai:7000` |
| Order-entry host | `QJ_ORDERS_HOST` | `orders.qjtrader.ai:7001` |
| Pinned CA/cert | `QJ_CA_FILE` | none (standard public-CA validation) |

Tokens are minted for you (OAuth2 client-credentials) and refreshed automatically before they
expire — you never handle them directly. Need a raw token (e.g. for the WebSocket interface)?
`client.token(qjtrader.MARKET_DATA_SCOPE)`.

Use `client.session_info()` when a local agent needs the Gateway's authoritative data and order
environments. `client.search_universe()` and `client.describe_instrument(symbol)` provide small,
machine-readable discovery helpers so code does not have to infer product identity from prose.

Both public API hosts use standard public-certificate validation. `QJ_CA_FILE` remains available
for controlled private deployments but is not required for the hosted QJ Gateway services.

## How it works

Both APIs speak **NDJSON over TLS** — one JSON object per line, UTF-8, newline-terminated,
authenticated with an OAuth2 JWT sent on the first line. The order lifecycle is a deterministic,
journaled state machine (`accepted → new → (partial)* → filled | canceled | replaced`), commands are
idempotent per client order id (`cid`), and the server enforces pre-trade risk checks +
cancel-on-disconnect. Full protocol: **[Order Entry](https://docs.qjtrader.ai/docs/ai/order-entry)**
and **[Market Data](https://docs.qjtrader.ai/docs/ai/market-data)**.

## Use it from an LLM (MCP)

Prefer to drive QJ from Claude or another AI assistant? The companion
[`qjtrader-mcp`](https://github.com/QJTrader/qjtrader-python) server exposes these APIs as Model
Context Protocol tools — subscribe to quotes and place **simulated** orders in plain language, no
code. Order tools refuse a live credential by default (sandbox-only unless you opt in). Add it to
Claude Code with:

```bash
claude mcp add qjtrader -e QJ_CLIENT_ID=... -e QJ_CLIENT_SECRET=... -e QJ_ENV=sandbox -- uvx qjtrader-mcp
```

The console's "Connect your AI" panel generates this for you, pre-filled.

## Links

- 📚 Docs: https://docs.qjtrader.ai/docs/ai
- 🔑 Console (get a key): https://gateway.qjtrader.ai
- 🔤 Symbology: https://docs.qjtrader.ai/docs/ai/symbology
- 🐛 Issues: https://github.com/QJTrader/qjtrader-python/issues

## License

Apache-2.0. See [LICENSE](LICENSE).
