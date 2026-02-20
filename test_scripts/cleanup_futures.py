import ccxt
import os
import json
from dotenv import load_dotenv

load_dotenv(".env.dev")

def cleanup_futures():
    print("🧹 Starting Binance Futures Testnet Cleanup...")
    
    api_key = os.getenv("BINANCE_DEMO_API_KEY")
    api_secret = os.getenv("BINANCE_DEMO_API_SECRET")
    
    exchange = ccxt.binance({
        "apiKey": api_key,
        "secret": api_secret,
        "options": {"defaultType": "future"},
        # Manual override required for now
        "urls": {
             'api': {
                 'fapiPublic': 'https://testnet.binancefuture.com/fapi/v1',
                 'fapiPrivate': 'https://testnet.binancefuture.com/fapi/v1',
                 'fapiPrivateV2': 'https://testnet.binancefuture.com/fapi/v2',
                 'public': 'https://testnet.binancefuture.com/fapi/v1',
                 'private': 'https://testnet.binancefuture.com/fapi/v1',
             }
        }
    })
    
    try:
        # 1. Cancel All Orders
        print("1. Cancelling all open orders...")
        # fapiPrivateDeleteAllOpenOrders
        try:
             exchange.fapiPrivateDeleteAllOpenOrders({'symbol': 'BTCUSDT'})
             print("   ✅ All orders cancelled.")
        except Exception as e:
             print(f"   ⚠️ Cancel failed (maybe no orders): {e}")

        # 2. Close All Positions
        print("2. Closing positions...")
        # Get positions
        account = exchange.fapiPrivateV2GetAccount()
        positions = account.get('positions', [])
        
        for pos in positions:
            symbol = pos['symbol']
            amt = float(pos['positionAmt'])
            if amt != 0:
                print(f"   Found position: {symbol} {amt}")
                side = "SELL" if amt > 0 else "BUY"
                # Market close
                params = {
                    'symbol': symbol,
                    'side': side,
                    'type': 'MARKET',
                    'quantity': abs(amt),
                    'reduceOnly': 'true'
                }
                res = exchange.fapiPrivatePostOrder(params)
                print(f"   ✅ Closed position: {res['orderId']}")
        
        print("   ✅ Position cleanup complete.")

        # 3. Clean local state file
        print("3. Removing local state file...")
        if os.path.exists("data/trader_state.json"):
            os.remove("data/trader_state.json")
            print("   ✅ Removed data/trader_state.json")
        else:
             print("   ⚠️ data/trader_state.json not found.")

    except Exception as e:
        print(f"❌ Cleanup failed: {e}")

if __name__ == "__main__":
    cleanup_futures()
