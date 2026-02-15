
"""Test RealBroker with Binance Testnet"""
from trader.infrastructure import RealBroker, EventBus

# Initialize components
event_bus = EventBus()

# Create real broker (uses Testnet by default)
print("=" * 70)
print("Testing RealBroker with Binance Testnet")
print("=" * 70)

try:
    broker = RealBroker(
        event_bus=event_bus,
        env_file=".env.dev",
        testnet=True
    )

    print("\n✅ RealBroker initialized successfully")

    # Test get_account_summary
    print("\n--- Testing get_account_summary ---")
    summary = broker.get_account_summary()
    print(f"Account Summary:")
    print(f"  Balance: ${summary['balance']:,.2f}")
    print(f"  Equity: ${summary['total_equity']:,.2f}")
    print(f"  Positions: {summary['positions']}")
    print(f"  Open Orders: {summary['open_orders']}")
    print(f"  Return: {summary['total_return']:.2f}%")

    print("\n✅ Test completed successfully!")
    print("=" * 70)

except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()

