"""Stream live (or, in the sandbox, simulated) market data.

    export QJ_CLIENT_ID=...  QJ_CLIENT_SECRET=...   # a key from gateway.qjtrader.ai
    python examples/quickstart_market_data.py
"""
import qjtrader

client = qjtrader.Client()

with client.market_data() as md:
    print(f"authenticated as {md.user}")
    # Consolidated (CA:RY), one-venue (CA:RY.PT — PURE/CSE), and a future.
    md.subscribe(["CA:RY", "CA:RY.PT", "MX:CRAU26"], depth=5)
    for msg in md.messages(timeout=30):
        t = msg.get("type")
        if t in ("snapshot", "quote"):
            d = msg["data"] if t == "quote" else msg.get("quote", {})
            print(f'{msg["symbol"]:12} {t:9} bid {d.get("bid")} / ask {d.get("ask")}')
        elif t == "trade":
            print(f'{msg["symbol"]:12} trade     {msg["data"]["size"]} @ {msg["data"]["price"]}')
