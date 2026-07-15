# Changelog

## 0.4.0

- **Broker-truth positions.** `Client.positions()` now documents and types (via the new
  `PositionsEnvelope` / `PositionDetail` `TypedDict`s) the full `GET /api/v1/positions` surface:
  the flat fill-only `positions` map (unchanged, back-compat) plus, on a real-plane credential
  with the broker feed wired, `positions_detail` (`{broker_qty, fill_qty, total_qty}` per canonical
  symbol — the desktop `TotalVolume = InitVolume + NetVolume`), `admserv_limits` (hard floor/ceiling
  risk caps), `capital_required`, `broker_asof`/`broker_synced_at`, and the `orders_env` plane
  (`sandbox`/`paper`/`shadow`/`real`). Simulated planes return a fill-only detail and omit the
  broker/risk fields — that's by design, not a bug.
- **Restart hydration seeds the broker total, not just today's fills.** `run_strategy_live`'s
  reconnect hydration now prefers `positions_detail[sym].total_qty` when the gateway exposes it, so
  a strategy that walked into the day holding a broker start-of-day position resumes from its true
  `InitVolume + NetVolume` instead of understating by the broker half. Falls back to the fill-only
  net for simulated planes / older gateways (never worse than before).

## 0.3.1

- `Client.prove()` — one call runs the full sandbox proof: live quote → resting limit order
  (priced safely below the bid so it never crosses) → cancel → journal, returning a structured
  `{quote, cid, cancel_cid, lifecycle, journal}` result. The three "proving steps" from the
  onboarding brief are now a single method instead of a hand-rolled loop.
- `Client.chain_stats()` — OI concentration, volume, put/call ratio and IV-skew digest for an
  options chain (`/api/v1/chain/stats`), with the same forgiving `YYYYMM` expiry normalization
  as `chain()`.

## 0.1.0 (unreleased)

Initial release.

- `qjtrader.Client` — one entry point for both APIs; credentials + endpoints from args or
  `QJ_*` environment variables. Sandbox and production use the same code.
- Market data: `client.market_data()` → subscribe / unsubscribe / stream `snapshot`, `quote`,
  `level2`, `trade` messages. Consolidated and per-venue equity symbols (`CA:RY`, `CA:RY.PT`).
- Order entry: `client.orders()` → `order` / `cancel` / `replace` / `cancel_all` / `status`, plus
  `order_and_wait()`; deterministic order state machine, idempotent `cid`.
- OAuth2 client-credentials tokens minted + auto-refreshed for you.
- `qjtrader` command-line tool.
- Stdlib only; typed (`py.typed`); Python 3.9+.
