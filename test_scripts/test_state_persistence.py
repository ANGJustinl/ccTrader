"""
Test script for StatePersistence.

Tests the JSON-based state persistence system including:
- Saving positions, orders, risk manager state, and balance
- Loading and restoring from saved state
- Serialization and deserialization
"""
import os
import sys
import tempfile
from decimal import Decimal
from datetime import datetime
from pathlib import Path

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from src.trader.infrastructure.state_persistence import StatePersistence
from src.trader.domain.position import Position
from src.trader.domain.value_objects import Side
from src.trader.application.order import Order, OrderStatus


def test_position_serialization():
    """Test position serialization and deserialization."""
    print("\n" + "=" * 80)
    print("TEST 1: Position Serialization")
    print("=" * 80)

    # Create test position
    position = Position(
        symbol="BTC/USDT:USDT",
        side=Side.LONG,
        quantity=Decimal("0.1"),
        entry_price=Decimal("50000.0"),
        leverage=1,
    )

    persistence = StatePersistence()

    # Serialize
    pos_dict = persistence._position_to_dict(position)
    print(f"Serialized position: {pos_dict}")

    # Deserialize
    restored_pos = persistence._dict_to_position(pos_dict)

    print(f"Restored symbol: {restored_pos.symbol}")
    print(f"Restored side: {restored_pos.side}")
    print(f"Restored quantity: {restored_pos.quantity}")
    print(f"Restored entry price: {restored_pos.entry_price}")

    assert restored_pos.symbol == position.symbol
    assert restored_pos.side == position.side
    assert restored_pos.quantity == position.quantity
    assert restored_pos.entry_price == position.entry_price

    print("\n✅ Position Serialization tests passed!")


def test_order_serialization():
    """Test order serialization and deserialization."""
    print("\n" + "=" * 80)
    print("TEST 2: Order Serialization")
    print("=" * 80)

    # Create test order
    order = Order(
        id="test-order-123",
        symbol="BTC/USDT:USDT",
        side="buy",
        order_type="limit",
        quantity=Decimal("0.1"),
        price=Decimal("50000.0"),
        status=OrderStatus.FILLED,
        filled_quantity=Decimal("0.1"),
        avg_fill_price=Decimal("50000.0"),
        timestamp=datetime.now(),
        create_time=datetime.now(),
    )

    persistence = StatePersistence()

    # Serialize
    order_dict = persistence._order_to_dict(order)
    print(f"Serialized order: {order_dict}")

    # Deserialize
    restored_order = persistence._dict_to_order(order_dict)

    print(f"Restored order ID: {restored_order.id}")
    print(f"Restored symbol: {restored_order.symbol}")
    print(f"Restored side: {restored_order.side}")
    print(f"Restored quantity: {restored_order.quantity}")
    print(f"Restored status: {restored_order.status}")

    assert restored_order.id == order.id
    assert restored_order.symbol == order.symbol
    assert restored_order.side == order.side
    assert restored_order.quantity == order.quantity
    assert restored_order.status == order.status

    print("\n✅ Order Serialization tests passed!")


def test_save_and_load_state():
    """Test full state save and load."""
    print("\n" + "=" * 80)
    print("TEST 3: Full State Save & Load")
    print("=" * 80)

    # Create temporary file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        temp_path = f.name

    try:
        # Create test data
        positions = {
            "BTC/USDT:USDT": Position(
                symbol="BTC/USDT:USDT",
                side=Side.LONG,
                quantity=Decimal("0.1"),
                entry_price=Decimal("50000.0"),
                leverage=1,
            )
        }

        orders = {
            "order-1": Order(
                id="order-1",
                symbol="BTC/USDT:USDT",
                side="buy",
                order_type="market",
                quantity=Decimal("0.1"),
                status=OrderStatus.FILLED,
                timestamp=datetime.now(),
                create_time=datetime.now(),
            )
        }

        risk_state = {
            "initial_balance": "10000",
            "peak_balance": "11000",
            "current_balance": "10500",
            "current_drawdown": "0.045",
            "daily_pnl": "500",
            "trading_halted": False,
        }

        balance = Decimal("10500.0")

        # Save state
        persistence = StatePersistence(storage_path=temp_path)
        persistence.save_state(positions, orders, risk_state, balance)

        print(f"\nState saved to: {temp_path}")

        # Load state
        loaded_state = persistence.load_state()
        assert loaded_state is not None, "State should not be None after save"

        print(f"\nLoaded state timestamp: {loaded_state.get('timestamp')}")
        print(f"Loaded balance: {loaded_state.get('balance')}")
        print(f"Loaded positions count: {len(loaded_state.get('positions', {}))}")
        print(f"Loaded orders count: {len(loaded_state.get('orders', {}))}")

        # Restore positions and orders
        restored_positions = persistence.restore_positions(loaded_state)
        restored_orders = persistence.restore_orders(loaded_state)

        assert len(restored_positions) == 1
        assert len(restored_orders) == 1

        restored_pos = restored_positions["BTC/USDT:USDT"]
        assert restored_pos.quantity == Decimal("0.1")
        assert restored_pos.entry_price == Decimal("50000.0")

        restored_order = restored_orders["order-1"]
        assert restored_order.id == "order-1"
        assert restored_order.quantity == Decimal("0.1")

        print("\n✅ Full State Save & Load tests passed!")

    finally:
        # Clean up
        try:
            os.unlink(temp_path)
        except:
            pass


def test_nonexistent_file():
    """Test loading from nonexistent file."""
    print("\n" + "=" * 80)
    print("TEST 4: Nonexistent File Handling")
    print("=" * 80)

    persistence = StatePersistence(storage_path="nonexistent_file_12345.json")
    state = persistence.load_state()

    assert state is None, "Nonexistent file should return None"
    print("✅ Nonexistent file handling test passed!")


def main():
    """Run all state persistence tests."""
    print("\n" + "=" * 80)
    print("STATE PERSISTENCE TEST SUITE")
    print("=" * 80)

    try:
        test_position_serialization()
        test_order_serialization()
        test_save_and_load_state()
        test_nonexistent_file()

        print("\n" + "=" * 80)
        print("✅ ALL TESTS PASSED!")
        print("=" * 80)

    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
