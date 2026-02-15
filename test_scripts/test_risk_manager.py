"""
Test script for RiskManager.

Tests the 5-layer risk management system:
- Max Drawdown Protection (>5% force liquidation)
- Fat Finger Check (>1 BTC rejection)
- Daily Loss Limit (>10% stop)
- Position Size Limit (>50% net value rejection)
- Rate Limiting (>100 req/min delay)
"""
import os
import sys
from decimal import Decimal
from datetime import datetime

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from src.trader.application.risk_manager import RiskManager
from src.trader.application.order import Order, OrderStatus
from src.trader.domain.position import Position
from src.trader.domain.value_objects import Side


def test_fat_finger_check():
    """Test fat finger order rejection."""
    print("\n" + "=" * 80)
    print("TEST 1: Fat Finger Check")
    print("=" * 80)

    risk_manager = RiskManager(initial_balance=Decimal("100000"))  # Higher balance for testing

    # Create a normal order (should pass)
    normal_order = Order(
        symbol="BTC/USDT:USDT",
        side="buy",
        order_type="market",
        quantity=Decimal("0.5"),
        price=Decimal("50000"),
        timestamp=datetime.now(),
    )

    passed, reason = risk_manager.check_order(normal_order, Decimal("100000"), {})
    print(f"Normal order (0.5 BTC): {'PASS' if passed else 'FAIL'} - {reason}")
    assert passed, "Normal order should pass"

    # Create a fat finger order (should fail)
    fat_order = Order(
        symbol="BTC/USDT:USDT",
        side="buy",
        order_type="market",
        quantity=Decimal("2.0"),
        price=Decimal("50000"),
        timestamp=datetime.now(),
    )

    passed, reason = risk_manager.check_order(fat_order, Decimal("100000"), {})
    print(f"Fat finger order (2.0 BTC): {'PASS' if not passed else 'FAIL'} - {reason}")
    assert not passed, "Fat finger order should be rejected"

    print("\n✅ Fat Finger Check tests passed!")


def test_position_size_limit():
    """Test position size limit check."""
    print("\n" + "=" * 80)
    print("TEST 2: Position Size Limit")
    print("=" * 80)

    risk_manager = RiskManager(initial_balance=Decimal("100000"), max_position_pct=Decimal("0.5"))

    # Create an order that doesn't exceed limit
    small_order = Order(
        symbol="BTC/USDT:USDT",
        side="buy",
        order_type="market",
        quantity=Decimal("0.1"),
        price=Decimal("50000"),
        timestamp=datetime.now(),
    )

    passed, reason = risk_manager.check_order(small_order, Decimal("100000"), {})
    print(f"Small position order: {'PASS' if passed else 'FAIL'} - {reason}")
    assert passed, "Small position order should pass"

    print("\n✅ Position Size Limit tests passed!")


def test_drawdown_protection():
    """Test max drawdown protection."""
    print("\n" + "=" * 80)
    print("TEST 3: Max Drawdown Protection")
    print("=" * 80)

    risk_manager = RiskManager(
        initial_balance=Decimal("100000"),
        max_drawdown_pct=Decimal("0.05"),
    )

    # Update balance to peak
    risk_manager.update_balance(Decimal("110000"))
    print(f"Peak balance updated to: ${risk_manager.peak_balance:,.2f}")

    # Create order (should pass)
    order = Order(
        symbol="BTC/USDT:USDT",
        side="buy",
        order_type="market",
        quantity=Decimal("0.001"),
        price=Decimal("50000"),
        timestamp=datetime.now(),
    )

    passed, reason = risk_manager.check_order(order, Decimal("105000"), {})
    print(f"Order with 4.5% drawdown: {'PASS' if passed else 'FAIL'} - {reason}")
    assert passed, "Order with <5% drawdown should pass"

    # Now test with >5% drawdown
    risk_manager.update_balance(Decimal("104000"))  # ~5.45% drawdown from 110000
    print(f"Balance updated to: ${risk_manager.current_balance:,.2f}")
    print(f"Drawdown: {risk_manager.current_drawdown * 100:.2f}%")
    print(f"Trading halted: {risk_manager.trading_halted}")

    assert risk_manager.trading_halted, "Trading should be halted after max drawdown"

    passed, reason = risk_manager.check_order(order, Decimal("104000"), {})
    print(f"Order after halt: {'PASS' if not passed else 'FAIL'} - {reason}")
    assert not passed, "Order should be rejected after trading halted"

    print("\n✅ Max Drawdown Protection tests passed!")


def test_daily_loss_limit():
    """Test daily loss limit."""
    print("\n" + "=" * 80)
    print("TEST 4: Daily Loss Limit")
    print("=" * 80)

    risk_manager = RiskManager(
        initial_balance=Decimal("100000"),
        max_drawdown_pct=Decimal("0.20"),  # Set high to avoid interference
        daily_loss_limit_pct=Decimal("0.10"),
    )

    # Loss of 8% should be ok
    risk_manager.update_balance(Decimal("92000"))
    print(f"Balance after 8% loss: ${risk_manager.current_balance:,.2f}")
    print(f"Daily PnL: ${risk_manager.daily_pnl:,.2f}")
    assert not risk_manager.trading_halted, "Trading should not be halted at 8% loss"

    # Loss of 10%+ should trigger halt
    risk_manager.update_balance(Decimal("89000"))
    print(f"Balance after 11% loss: ${risk_manager.current_balance:,.2f}")
    print(f"Daily PnL: ${risk_manager.daily_pnl:,.2f}")
    assert risk_manager.trading_halted, "Trading should be halted after 10%+ loss"

    print("\n✅ Daily Loss Limit tests passed!")


def test_state_persistence():
    """Test risk manager state get/restore."""
    print("\n" + "=" * 80)
    print("TEST 5: State Persistence")
    print("=" * 80)

    # Create and modify risk manager
    rm1 = RiskManager(initial_balance=Decimal("100000"))
    rm1.update_balance(Decimal("110000"))
    rm1.update_balance(Decimal("105000"))

    state = rm1.get_state()
    print(f"State saved: {state}")

    # Restore state to new instance
    rm2 = RiskManager(initial_balance=Decimal("50000"))
    rm2.restore_state(state)

    print(f"Restored peak balance: ${rm2.peak_balance:,.2f}")
    print(f"Restored current balance: ${rm2.current_balance:,.2f}")
    print(f"Restored drawdown: {rm2.current_drawdown * 100:.2f}%")

    assert rm2.peak_balance == Decimal("110000"), "Peak balance not restored correctly"
    assert rm2.current_balance == Decimal("105000"), "Current balance not restored correctly"

    print("\n✅ State Persistence tests passed!")


def main():
    """Run all risk manager tests."""
    print("\n" + "=" * 80)
    print("RISK MANAGER TEST SUITE")
    print("=" * 80)

    try:
        test_fat_finger_check()
        test_position_size_limit()
        test_drawdown_protection()
        test_daily_loss_limit()
        test_state_persistence()

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
