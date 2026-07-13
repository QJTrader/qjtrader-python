# qjtrader

Official Python client for the **QJ Trader AI Trading APIs** — stream real-time Canadian market
data and send orders to Canadian venues (Montréal Exchange derivatives, and equities across every
lit exchange and dark pool) over one authenticated connection.

```bash
pip install qjtrader
```

- **Free sandbox, no approval.** Create an account at [console.qjtrader.ai](https://console.qjtrader.ai),
  click *Create sandbox credential*, and you get a `client_id` + `client_secret` that stream
  **simulated** data and return **simulated** fills — in the *exact production wire format*, 24/7.
- **Sandbox → production with one credential swap.** Your code never changes; the credential decides
  sandbox vs. real, server-side.
- **Stdlib only.** No dependencies — easy to install, easy to audit.

## Quickstart

Get a sandbox key from the [console](https://console.qjtrader.ai), then:

```bash
export QJ_CLIENT_ID="your-client-id"
export QJ_CLIENT_SECRET="your-client-secret"
```

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
    md.subscribe(["CA:RY", "CA:RY.PT", "MX:CRAU26"], depth=5)
    for msg in md.messages(timeout=30):
        if msg["type"] == "quote":
            print(msg["symbol"], msg["data"]["bid"], msg["data"]["ask"])
```

- `CA:RY` is the **consolidated** Canadian equity book (each level tagged with its venue);
  `CA:RY.PT` is **PURE (CSE)** only. Futures like `MX:CRAU26` are venue-native. See the full
  [symbology reference](https://docs.qjtrader.ai/docs/ai/symbology).

## Command line

The package installs a `qjtrader` command:

```bash
qjtrader subscribe CA:RY MX:CRAU26 --watch 30
qjtrader order --sym MX:CRAU26 --side buy --qty 1 --price 97.00 --account SIM --tif ioc
qjtrader status
qjtrader cancel --orig qj-abc123

# strategies: the same file runs in backtest and live
qjtrader backtest examples/strategy_meanreversion.py --symbol MX:CRAU26 --bars 200
qjtrader run       examples/strategy_meanreversion.py --symbols MX:CRAU26 --tag mr1
```

## Strategies — one contract, every venue

Subclass `Strategy` and the same file runs in the backtest engine, a paper run, or
live (plan §10). Backtests are offline and deterministic (no network, no secrets);
`qjtrader run` hosts it against a live/paper credential, tags every order with the
strategy name (so the journal groups by strategy), and cancels everything on Ctrl-C.

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

> **Pilot note:** while order entry is in private pilot it may be reached by IP with a pinned
> certificate provided at onboarding — pass `ca_file="pilot-server.pem"` (or `QJ_CA_FILE`). Market
> data uses a standard public certificate.

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
- 🔑 Console (get a key): https://console.qjtrader.ai
- 🔤 Symbology: https://docs.qjtrader.ai/docs/ai/symbology
- 🐛 Issues: https://github.com/QJTrader/qjtrader-python/issues

## License

Apache-2.0. See [LICENSE](LICENSE).
