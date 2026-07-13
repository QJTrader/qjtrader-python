"""Place a sandbox order and print the fill.

    export QJ_CLIENT_ID=...  QJ_CLIENT_SECRET=...   # a sandbox key from console.qjtrader.ai
    python examples/quickstart_orders.py
"""
import qjtrader

client = qjtrader.Client()

with client.orders() as oe:
    print(f"authenticated as {oe.user}")
    # Marketable IOC buy — fills immediately in the sandbox simulator.
    result = oe.order_and_wait(
        sym="MX:CRAU26", side="buy", qty=1, price=97.00, account="SIM", tif="ioc",
    )
    print("result:", result)

    # A resting limit + explicit cancel:
    cid = oe.order(sym="MX:CRAU26", side="buy", qty=1, price=90.00, account="SIM")
    for msg in oe.updates(timeout=5):
        print(msg)
    oe.cancel(cid)
    print("open orders:", oe.status())
