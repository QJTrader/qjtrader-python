# Changelog

## 0.5.8

- Market availability now documents live-sampled sparse shapes across Canadian cash listings,
  Montréal derivatives, US equities/options, and selected US futures.
- History/stat responses expose `source=synthetic|recorded|unavailable` and availability metadata;
  production history never silently falls back to generated bars.

## 0.5.7

- Added `AccessClient.request_limit_change()` and `qjtrader limit-request` so users and agents can
  request product-specific cloud API safety-limit changes programmatically.
- Limit requests are human-authorized and explicitly leave broker/Desktop risk controls unchanged.

## 0.5.6

- Market availability now exposes the production QJ/TMX order-level TL2 rows,
  round/odd/special-lot books, message provenance, and the complete MX event and
  summary contract.
- Documentation now reserves `D4` for QuoteMedia/M3 comparison context and uses
  QJ/TMX order-level TL2 for the QJ data model.

## 0.5.3

- Added source-aware `data_shapes` and an explicit `observation_contract` to market availability.
- `describe_instrument()` now explains the expected payload shape and preserves sparse or
  null-priced observations as unquoted rather than treating them as zero.
- Canadian ETF discovery now distinguishes supported ETF examples from common shares.

## 0.5.2

- Corrected the published onboarding description: QJ promotes licensed data and order authority
  independently on the credential; users do not need to rewrite code or assume a credential swap.

## 0.5.1

- `Client.session_info()` now probes data and order authority independently, so credentials with
  only one granted scope still report that plane while returning a plain error for the other.

## 0.5.0

- **Server-authoritative sessions.** `Client.session_info()` reports the data and order
  environments returned by authenticated Gateway handshakes, including the order authority version.
- **Agent-friendly universe.** `search_universe()` and `describe_instrument()` provide compact,
  machine-readable discovery without requiring an agent to infer the symbol grammar from prose.
- **Safe local strategy start.** `qjtrader init` creates a tested, observation-first local project;
  live runners announce strategy, version, run, agent, and session identity when the feed supports it.

## 0.4.3

- **Product-level availability.** `market_availability()` now separates sandbox and production
  data/order support for Canadian cash listings, MX futures/options/strategies, US equities/ETFs,
  US listed options, selected US futures, and explicitly unavailable cloud products.
- **Cross-market examples.** Quickstarts and API documentation now demonstrate `CA:`, `MX:`, and
  `US:` symbols and explain that market data, L2, accounts, routes, and order authority are separate.
- Removed the obsolete private-pilot/pinned-certificate deployment note; the public hosts use
  standard certificate validation.

## 0.4.1

- **Direct venue routing.** `Orders.order(...)` (and the async `order_and_wait`) now takes an
  optional `venue=` argument, and the CLI takes `--venue`, to route a Canadian equity order to a
  specific venue or route instead of the account default. Every Canadian venue is addressable —
  `TO`/`T`/`TX` (TSX), `V` (TSX Venture), `AL` (Alpha), `PT` (PURE/CSE), `OG` (Omega), `CH`
  (Nasdaq CXC), `CX` (Nasdaq CX2), `CXD` (Nasdaq dark), `AQN` (NEO-N), `AQL` (NEO-L), `LY` (Lynx),
  `TL`/`TLM` (MATCHNow dark) — plus the route selectors `SOR` (smart order router) and `DARK` (its
  dark-only sweep). Equivalent to the `CA:RY.<venue>` symbol suffix; if both are given they must
  agree. The value is upper-cased and forwarded — a bare symbol keeps using the account default.

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
