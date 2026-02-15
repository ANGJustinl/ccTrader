
#!/usr/bin/env python
"""
Diagnostic script to check Binance Testnet status.
- Check open orders on exchange
- Check current positions
- Check account balance
"""

import os
import sys
from decimal import Decimal

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))

from dotenv import load_dotenv
import ccxt


def main():
    print("=" * 80)
    print("BINANCE TESTNET DIAGNOSTIC")
    print("=" * 80)

    # Load environment variables
    load_dotenv(".env.dev")
    api_key = os.getenv("BINANCE_API_KEY") or ""
    api_secret = os.getenv("BINANCE_API_SECRET") or ""

    # Initialize exchange
    exchange = ccxt.binance({
        "apiKey": api_key,
        "secret": api_secret,
        "enableRateLimit": True,
    })
    exchange.set_sandbox_mode(True)
    print("✅ Connected to Binance Testnet (Sandbox Mode)")

    symbol = "BTC/USDT"

    try:
        # 1. Check account balance
        print("\n" + "-" * 80)
        print("1. ACCOUNT BALANCE")
        print("-" * 80)
        balance = exchange.fetch_balance()
        usdt_free = balance.get("USDT", {}).get("free", 0)
        usdt_total = balance.get("USDT", {}).get("total", 0)
        print(f"   USDT Free:  ${usdt_free:,.2f}")
        print(f"   USDT Total: ${usdt_total:,.2f}")

        # 2. Check open orders
        print("\n" + "-" * 80)
        print("2. OPEN ORDERS ON EXCHANGE")
        print("-" * 80)
        open_orders = exchange.fetch_open_orders(symbol)
        print(f"   Found {len(open_orders)} open order(s) on exchange")
        for i, order in enumerate(open_orders, 1):
            print(f"   {i}. ID={order['id']}, {order['side'].upper()} {order['amount']} @ {order.get('price', 'MARKET')}, status={order['status']}")

        # 3. Check all orders (last 100)
        print("\n" + "-" * 80)
        print("3. RECENT ORDERS (last 50)")
        print("-" * 80)
        all_orders = exchange.fetch_orders(symbol, limit=50)
        print(f"   Found {len(all_orders)} total order(s)")
        for i, order in enumerate(reversed(all_orders[-20:]), 1):  # Show last 20
            print(f"   {i}. ID={order['id']}, {order['side'].upper()} {order['amount']} @ {order.get('price', 'MARKET')}, status={order['status']}, filled={order.get('filled', 0)}")

        # 4. Check positions (for futures)
        print("\n" + "-" * 80)
        print("4. POSITIONS")
        print("-" * 80)
        try:
            positions = exchange.fetch_positions([symbol])
            for pos in positions:
                if pos.get("contracts", 0) != 0:
                    print(f"   {pos['symbol']}: {pos['side']} {pos['contracts']} @ {pos.get('entryPrice', 'N/A')}")
                    print(f"      Unrealized PnL: {pos.get('unrealizedPnl', 'N/A')}")
            if not any(pos.get("contracts", 0) != 0 for pos in positions):
                print("   No open positions")
        except Exception as e:
            print(f"   Could not fetch positions: {e}")

        print("\n" + "=" * 80)
        print("DIAGNOSTIC COMPLETE")
        print("=" * 80)

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

