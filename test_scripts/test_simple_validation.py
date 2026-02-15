
"""
Simple RealBroker Validation Test
================================

简化版验证测试，用于快速验证 RealBroker 的核心功能。
"""

import os
import sys
import time
import uuid
from decimal import Decimal
from datetime import datetime, timezone

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from trader.infrastructure.event_bus import EventBus, Event, EventType
from trader.infrastructure.real_broker import RealBroker
from trader.application.order import Order, OrderStatus


def main():
    print("=" * 80)
    print("SIMPLE REAL BROKER VALIDATION TEST")
    print("=" * 80)

    try:
        # Initialize components
        event_bus = EventBus()
        broker = RealBroker(event_bus, env_file=".env.dev", testnet=True)

        # Test 1: Connection
        print("\n[1] Testing connection...")
        summary = broker.get_account_summary()
        print(f"✅ Connected! Balance: ${summary['balance']:,.2f}")

        # Test 2: Get market price
        print("\n[2] Getting market price...")
        symbol = "BTC/USDT:USDT"
        current_price = broker.get_market_price(symbol)
        if current_price:
            print(f"✅ Current price: ${current_price:,.2f}")

        # Test 3: Place a limit order that won't fill
        print("\n[3] Placing limit order (below market)...")
        if not current_price:
            print("❌ Could not get market price")
            return 1
        
        limit_price = current_price * Decimal("0.90")
        quantity = Decimal("0.001")

        order = Order(
            id=str(uuid.uuid4()),
            symbol=symbol,
            side="buy",
            order_type="limit",
            quantity=quantity,
            price=limit_price,
            timestamp=datetime.now(timezone.utc),
        )

        # Capture events
        events_received = []
        def capture_event(event: Event):
            events_received.append(event)
            print(f"📨 EVENT: {event.type.value} - {event.data}")

        event_bus.subscribe(EventType.ORDER_SUBMITTED, capture_event)
        event_bus.subscribe(EventType.ORDER_CANCELLED, capture_event)

        broker.submit_order(order)
        time.sleep(3)

        # Find exchange order ID from orders dict (keys are exchange IDs)
        exchange_order_id = None
        with broker._lock:
            for oid in broker.orders.keys():
                exchange_order_id = oid
                break

        if exchange_order_id:
            print(f"✅ Order placed, exchange ID: {exchange_order_id}")

            # Test order sync
            print("\n[4] Testing order sync...")
            broker.start_order_sync(interval=2)
            time.sleep(5)
            broker.stop_order_sync()
            print("✅ Order sync tested")

            # Cancel the order
            print("\n[5] Cancelling order...")
            broker.cancel_order(exchange_order_id)
            time.sleep(3)
            print("✅ Cancel request sent")

            broker.sync_open_orders()
            time.sleep(2)

        print("\n" + "=" * 80)
        print("✅ Simple validation complete!")
        print("=" * 80)
        return 0

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
