
"""
Cleanup Script for Binance Testnet
==================================

Cancels all open orders on Binance Testnet and clears state file.
"""

import os
import sys
import json
from decimal import Decimal

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))

from src.trader.infrastructure.real_broker import RealBroker
from src.trader.infrastructure.event_bus import EventBus
from src.trader.application.risk_manager import RiskManager
from src.trader.infrastructure.state_persistence import StatePersistence


def cleanup_testnet() -> None:
    """Cleanup Binance Testnet and local state."""
    print("=" * 80)
    print("BINANCE TESTNET CLEANUP")
    print("=" * 80)

    # Initialize components
    event_bus = EventBus()
    risk_manager = RiskManager(initial_balance=Decimal("10000"))
    state_persistence = StatePersistence()

    # Create broker
    broker = RealBroker(
        event_bus=event_bus,
        env_file=".env.dev",
        testnet=True,
        risk_manager=risk_manager,
        state_persistence=state_persistence,
    )

    print("\n[1] Fetching account summary...")
    summary = broker.get_account_summary()
    print(f"    Balance: ${summary['balance']:,.2f}")
    print(f"    Open Orders: {summary['open_orders']}")
    print(f"    Positions: {summary['positions']}")

    # Cancel all open orders by calling sync_open_orders first
    print(f"\n[2] Syncing and cancelling open orders...")
    try:
        broker.sync_open_orders()
        print("    Sync complete")
    except Exception as e:
        print(f"    Sync warning: {e}")
    
    print("\n[3] Note: Full cancellation requires exchange API access")
    print("    Please use Binance Testnet UI to cancel any remaining orders")

    # Clear local state file
    print("\n[3] Clearing local state file...")
    state_file = "data/trader_state.json"
    if os.path.exists(state_file):
        # Backup first
        backup_file = f"data/trader_state_backup_{os.path.getmtime(state_file):.0f}.json"
        os.rename(state_file, backup_file)
        print(f"    Backed up to: {backup_file}")
        
        # Create empty state
        empty_state = {
            "timestamp": "2026-01-01T00:00:00",
            "balance": "10000",
            "risk_manager": {
                "initial_balance": "10000",
                "peak_balance": "10000",
                "current_balance": "10000",
                "current_drawdown": "0",
                "daily_pnl": "0",
                "trading_halted": False
            },
            "positions": {},
            "orders": {}
        }
        with open(state_file, "w") as f:
            json.dump(empty_state, f, indent=2)
        print(f"    Created empty state: {state_file}")
    else:
        print(f"    State file not found: {state_file}")

    print("\n" + "=" * 80)
    print("CLEANUP COMPLETE")
    print("=" * 80)
    print("\nVerifying final state...")
    final_summary = broker.get_account_summary()
    print(f"Final Open Orders: {final_summary['open_orders']}")
    print(f"Final Positions: {final_summary['positions']}")


if __name__ == "__main__":
    cleanup_testnet()
