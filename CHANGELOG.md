# Changelog

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
