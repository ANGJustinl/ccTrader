"""Unit tests for the domain layer.

Tests value objects, position aggregate root, and domain services.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from src.trader.domain import (
    FundingInfo,
    MarginCalculator,
    OrderType,
    Position,
    PositionFactory,
    Side,
    TradeFill,
)


class TestSide:
    """Tests for Side enum."""

    def test_side_values(self):
        """Test Side enum has correct values."""
        assert Side.LONG == "LONG"
        assert Side.SHORT == "SHORT"

    def test_side_str_enum(self):
        """Test Side is a string enum."""
        assert isinstance(Side.LONG, str)
        assert isinstance(Side.SHORT, str)


class TestOrderType:
    """Tests for OrderType enum."""

    def test_order_type_values(self):
        """Test OrderType enum has correct values."""
        assert OrderType.MARKET == "MARKET"
        assert OrderType.LIMIT == "LIMIT"

    def test_order_type_str_enum(self):
        """Test OrderType is a string enum."""
        assert isinstance(OrderType.MARKET, str)
        assert isinstance(OrderType.LIMIT, str)


class TestFundingInfo:
    """Tests for FundingInfo value object."""

    def test_funding_info_creation(self):
        """Test FundingInfo can be created."""
        funding_info = FundingInfo(
            symbol="BTCUSDT",
            rate=Decimal("0.0001"),
            timestamp=datetime.now(timezone.utc),
            next_funding_time=datetime.now(timezone.utc) + timedelta(hours=8),
        )
        assert funding_info.symbol == "BTCUSDT"
        assert funding_info.rate == Decimal("0.0001")

    def test_funding_info_immutability(self):
        """Test FundingInfo is immutable."""
        funding_info = FundingInfo(
            symbol="BTCUSDT",
            rate=Decimal("0.0001"),
            timestamp=datetime.now(timezone.utc),
            next_funding_time=datetime.now(timezone.utc) + timedelta(hours=8),
        )
        with pytest.raises(Exception):
            funding_info.symbol = "ETHUSDT"


class TestTradeFill:
    """Tests for TradeFill value object."""

    def test_trade_fill_creation(self):
        """Test TradeFill can be created."""
        fill = TradeFill(
            id="fill_123",
            order_id="order_123",
            symbol="BTCUSDT",
            side=Side.LONG,
            price=Decimal("50000"),
            quantity=Decimal("0.1"),
            commission=Decimal("0.05"),
            timestamp=datetime.now(timezone.utc),
        )
        assert fill.id == "fill_123"
        assert fill.symbol == "BTCUSDT"
        assert fill.side == Side.LONG

    def test_trade_fill_validation_negative_price(self):
        """Test TradeFill rejects negative price."""
        with pytest.raises(Exception):
            TradeFill(
                id="fill_123",
                order_id="order_123",
                symbol="BTCUSDT",
                side=Side.LONG,
                price=Decimal("-100"),
                quantity=Decimal("0.1"),
                commission=Decimal("0.05"),
                timestamp=datetime.now(timezone.utc),
            )

    def test_trade_fill_validation_negative_quantity(self):
        """Test TradeFill rejects negative quantity."""
        with pytest.raises(Exception):
            TradeFill(
                id="fill_123",
                order_id="order_123",
                symbol="BTCUSDT",
                side=Side.LONG,
                price=Decimal("50000"),
                quantity=Decimal("-0.1"),
                commission=Decimal("0.05"),
                timestamp=datetime.now(timezone.utc),
            )


class TestPositionIncrease:
    """Tests for Position increase (add) logic."""

    def test_long_position_increase_avg_price(self):
        """Test long position average price calculation."""
        position = Position(
            symbol="BTCUSDT",
            side=Side.LONG,
            quantity=Decimal("0.1"),
            entry_price=Decimal("50000"),
            leverage=2,
        )

        fill = TradeFill(
            id="fill_1",
            order_id="order_1",
            symbol="BTCUSDT",
            side=Side.LONG,
            price=Decimal("51000"),
            quantity=Decimal("0.1"),
            commission=Decimal("0"),
            timestamp=datetime.now(timezone.utc),
        )

        position.increase(fill)

        # Average price = (0.1 * 50000 + 0.1 * 51000) / 0.2 = 50500
        assert position.quantity == Decimal("0.2")
        assert position.entry_price == Decimal("50500")

    def test_short_position_increase_avg_price(self):
        """Test short position average price calculation."""
        position = Position(
            symbol="BTCUSDT",
            side=Side.SHORT,
            quantity=Decimal("0.1"),
            entry_price=Decimal("50000"),
            leverage=2,
        )

        fill = TradeFill(
            id="fill_1",
            order_id="order_1",
            symbol="BTCUSDT",
            side=Side.SHORT,
            price=Decimal("49000"),
            quantity=Decimal("0.1"),
            commission=Decimal("0"),
            timestamp=datetime.now(timezone.utc),
        )

        position.increase(fill)

        # Average price = (0.1 * 50000 + 0.1 * 49000) / 0.2 = 49500
        assert position.quantity == Decimal("0.2")
        assert position.entry_price == Decimal("49500")

    def test_multiple_increases_accumulate(self):
        """Test multiple increases accumulate correctly."""
        position = Position(
            symbol="BTCUSDT",
            side=Side.LONG,
            quantity=Decimal("0.1"),
            entry_price=Decimal("50000"),
            leverage=2,
        )

        fill1 = TradeFill(
            id="fill_1",
            order_id="order_1",
            symbol="BTCUSDT",
            side=Side.LONG,
            price=Decimal("51000"),
            quantity=Decimal("0.1"),
            commission=Decimal("0"),
            timestamp=datetime.now(timezone.utc),
        )

        fill2 = TradeFill(
            id="fill_2",
            order_id="order_2",
            symbol="BTCUSDT",
            side=Side.LONG,
            price=Decimal("52000"),
            quantity=Decimal("0.1"),
            commission=Decimal("0"),
            timestamp=datetime.now(timezone.utc),
        )

        position.increase(fill1)
        position.increase(fill2)

        # After fill1: (0.1 * 50000 + 0.1 * 51000) / 0.2 = 50500
        # After fill2: (0.2 * 50500 + 0.1 * 52000) / 0.3 = 51000
        assert position.quantity == Decimal("0.3")
        assert position.entry_price == Decimal("51000")

    def test_increase_wrong_side_raises_error(self):
        """Test increasing with wrong side raises error."""
        position = Position(
            symbol="BTCUSDT",
            side=Side.LONG,
            quantity=Decimal("0.1"),
            entry_price=Decimal("50000"),
            leverage=2,
        )

        fill = TradeFill(
            id="fill_1",
            order_id="order_1",
            symbol="BTCUSDT",
            side=Side.SHORT,
            price=Decimal("50000"),
            quantity=Decimal("0.1"),
            commission=Decimal("0"),
            timestamp=datetime.now(timezone.utc),
        )

        with pytest.raises(ValueError, match="Cannot SHORT position with LONG"):
            position.increase(fill)


class TestPositionDecrease:
    """Tests for Position decrease (close) logic."""

    def test_long_position_close_pnl(self):
        """Test long position realized PNL calculation."""
        position = Position(
            symbol="BTCUSDT",
            side=Side.LONG,
            quantity=Decimal("0.1"),
            entry_price=Decimal("50000"),
            leverage=2,
        )

        fill = TradeFill(
            id="fill_1",
            order_id="order_1",
            symbol="BTCUSDT",
            side=Side.LONG,
            price=Decimal("51000"),
            quantity=Decimal("0.1"),
            commission=Decimal("0"),
            timestamp=datetime.now(timezone.utc),
        )

        pnl = position.decrease(fill)

        # PNL = (51000 - 50000) * 0.1 * 1 = 100
        assert pnl == Decimal("100")
        assert position.is_closed()

    def test_short_position_close_pnl(self):
        """Test short position realized PNL (inverted direction)."""
        position = Position(
            symbol="BTCUSDT",
            side=Side.SHORT,
            quantity=Decimal("0.1"),
            entry_price=Decimal("50000"),
            leverage=2,
        )

        fill = TradeFill(
            id="fill_1",
            order_id="order_1",
            symbol="BTCUSDT",
            side=Side.SHORT,
            price=Decimal("49000"),
            quantity=Decimal("0.1"),
            commission=Decimal("0"),
            timestamp=datetime.now(timezone.utc),
        )

        pnl = position.decrease(fill)

        # PNL = (49000 - 50000) * 0.1 * (-1) = 100 (inverted because short)
        assert pnl == Decimal("100")
        assert position.is_closed()

    def test_short_position_loss_pnl(self):
        """Test short position loss PNL calculation."""
        position = Position(
            symbol="BTCUSDT",
            side=Side.SHORT,
            quantity=Decimal("0.1"),
            entry_price=Decimal("50000"),
            leverage=2,
        )

        fill = TradeFill(
            id="fill_1",
            order_id="order_1",
            symbol="BTCUSDT",
            side=Side.SHORT,
            price=Decimal("51000"),
            quantity=Decimal("0.1"),
            commission=Decimal("0"),
            timestamp=datetime.now(timezone.utc),
        )

        pnl = position.decrease(fill)

        # PNL = (51000 - 50000) * 0.1 * (-1) = -100
        assert pnl == Decimal("-100")

    def test_partial_close(self):
        """Test partial position close."""
        position = Position(
            symbol="BTCUSDT",
            side=Side.LONG,
            quantity=Decimal("0.3"),
            entry_price=Decimal("50000"),
            leverage=2,
        )

        fill = TradeFill(
            id="fill_1",
            order_id="order_1",
            symbol="BTCUSDT",
            side=Side.LONG,
            price=Decimal("51000"),
            quantity=Decimal("0.1"),
            commission=Decimal("0"),
            timestamp=datetime.now(timezone.utc),
        )

        pnl = position.decrease(fill)

        # PNL = (51000 - 50000) * 0.1 * 1 = 100
        assert pnl == Decimal("100")
        assert position.quantity == Decimal("0.2")
        assert not position.is_closed()

    def test_decrease_wrong_side_raises_error(self):
        """Test decreasing with wrong side raises error."""
        position = Position(
            symbol="BTCUSDT",
            side=Side.LONG,
            quantity=Decimal("0.1"),
            entry_price=Decimal("50000"),
            leverage=2,
        )

        fill = TradeFill(
            id="fill_1",
            order_id="order_1",
            symbol="BTCUSDT",
            side=Side.SHORT,
            price=Decimal("50000"),
            quantity=Decimal("0.1"),
            commission=Decimal("0"),
            timestamp=datetime.now(timezone.utc),
        )

        with pytest.raises(ValueError, match="Cannot SHORT position with LONG"):
            position.decrease(fill)

    def test_decrease_exceeds_quantity_raises_error(self):
        """Test decreasing more than quantity raises error."""
        position = Position(
            symbol="BTCUSDT",
            side=Side.LONG,
            quantity=Decimal("0.1"),
            entry_price=Decimal("50000"),
            leverage=2,
        )

        fill = TradeFill(
            id="fill_1",
            order_id="order_1",
            symbol="BTCUSDT",
            side=Side.LONG,
            price=Decimal("50000"),
            quantity=Decimal("0.2"),
            commission=Decimal("0"),
            timestamp=datetime.now(timezone.utc),
        )

        with pytest.raises(ValueError, match="exceeds current position quantity"):
            position.decrease(fill)


class TestPositionLiquidationPrice:
    """Tests for liquidation price calculation."""

    def test_long_liquidation_price(self):
        """Test long position liquidation price calculation."""
        position = Position(
            symbol="BTCUSDT",
            side=Side.LONG,
            quantity=Decimal("0.1"),
            entry_price=Decimal("50000"),
            leverage=2,
        )

        # LiqPrice = 50000 * (1 - 1/2 + 0.005) = 50000 * 0.505 = 25250
        assert position.liquidation_price is not None
        assert abs(position.liquidation_price - Decimal("25250")) < Decimal("0.01")

    def test_short_liquidation_price(self):
        """Test short position liquidation price calculation."""
        position = Position(
            symbol="BTCUSDT",
            side=Side.SHORT,
            quantity=Decimal("0.1"),
            entry_price=Decimal("50000"),
            leverage=2,
        )

        # LiqPrice = 50000 * (1 + 1/2 - 0.005) = 50000 * 1.495 = 74750
        assert position.liquidation_price is not None
        assert abs(position.liquidation_price - Decimal("74750")) < Decimal("0.01")

    def test_different_leverage_liquidation_price(self):
        """Test liquidation price with different leverage."""
        position = Position(
            symbol="BTCUSDT",
            side=Side.LONG,
            quantity=Decimal("0.1"),
            entry_price=Decimal("50000"),
            leverage=10,
        )

        # LiqPrice = 50000 * (1 - 1/10 + 0.005) = 50000 * 0.905 = 45250
        assert position.liquidation_price is not None
        assert abs(position.liquidation_price - Decimal("45250")) < Decimal("0.01")

    def test_zero_position_no_liquidation_price(self):
        """Test zero quantity position has no liquidation price."""
        position = Position(
            symbol="BTCUSDT",
            side=Side.LONG,
            quantity=Decimal("0"),
            entry_price=Decimal("50000"),
            leverage=2,
        )
        assert position.liquidation_price is None


class TestPositionUnrealizedPnl:
    """Tests for unrealized PNL calculation."""

    def test_long_profit_unrealized_pnl(self):
        """Test long position profit scenario."""
        position = Position(
            symbol="BTCUSDT",
            side=Side.LONG,
            quantity=Decimal("0.1"),
            entry_price=Decimal("50000"),
            leverage=2,
        )

        current_price = Decimal("51000")
        pnl = position.calculate_unrealized_pnl(current_price)

        # PNL = (51000 - 50000) * 0.1 * 1 = 100
        assert pnl == Decimal("100")

    def test_long_loss_unrealized_pnl(self):
        """Test long position loss scenario."""
        position = Position(
            symbol="BTCUSDT",
            side=Side.LONG,
            quantity=Decimal("0.1"),
            entry_price=Decimal("50000"),
            leverage=2,
        )

        current_price = Decimal("49000")
        pnl = position.calculate_unrealized_pnl(current_price)

        # PNL = (49000 - 50000) * 0.1 * 1 = -100
        assert pnl == Decimal("-100")

    def test_short_profit_unrealized_pnl(self):
        """Test short position profit scenario (inverted direction)."""
        position = Position(
            symbol="BTCUSDT",
            side=Side.SHORT,
            quantity=Decimal("0.1"),
            entry_price=Decimal("50000"),
            leverage=2,
        )

        current_price = Decimal("49000")
        pnl = position.calculate_unrealized_pnl(current_price)

        # PNL = (49000 - 50000) * 0.1 * (-1) = 100
        assert pnl == Decimal("100")

    def test_short_loss_unrealized_pnl(self):
        """Test short position loss scenario (inverted direction)."""
        position = Position(
            symbol="BTCUSDT",
            side=Side.SHORT,
            quantity=Decimal("0.1"),
            entry_price=Decimal("50000"),
            leverage=2,
        )

        current_price = Decimal("51000")
        pnl = position.calculate_unrealized_pnl(current_price)

        # PNL = (51000 - 50000) * 0.1 * (-1) = -100
        assert pnl == Decimal("-100")

    def test_zero_position_unrealized_pnl(self):
        """Test zero quantity position has zero PNL."""
        position = Position(
            symbol="BTCUSDT",
            side=Side.LONG,
            quantity=Decimal("0"),
            entry_price=Decimal("50000"),
            leverage=2,
        )

        pnl = position.calculate_unrealized_pnl(Decimal("51000"))
        assert pnl == Decimal("0")


class TestPositionMaintenanceMargin:
    """Tests for maintenance margin calculation."""

    def test_maintenance_margin_calculation(self):
        """Test maintenance margin calculation."""
        position = Position(
            symbol="BTCUSDT",
            side=Side.LONG,
            quantity=Decimal("0.1"),
            entry_price=Decimal("50000"),
            leverage=2,
            maintenance_margin_rate=Decimal("0.005"),
        )

        current_price = Decimal("51000")
        margin = position.calculate_maintenance_margin(current_price)

        # PositionValue = 0.1 * 51000 = 5100
        # MaintenanceMargin = 5100 * 0.005 = 25.5
        expected = Decimal("0.1") * Decimal("51000") * Decimal("0.005")
        assert margin == expected


class TestPositionBoundaryConditions:
    """Tests for boundary conditions."""

    def test_zero_position(self):
        """Test zero quantity position."""
        position = Position(
            symbol="BTCUSDT",
            side=Side.LONG,
            quantity=Decimal("0"),
            entry_price=Decimal("50000"),
            leverage=2,
        )
        assert position.quantity == Decimal("0")
        assert position.is_closed()

    def test_max_leverage(self):
        """Test maximum leverage (200x)."""
        position = Position(
            symbol="BTCUSDT",
            side=Side.LONG,
            quantity=Decimal("0.1"),
            entry_price=Decimal("50000"),
            leverage=200,
        )
        assert position.leverage == 200

    def test_leverage_exceeds_max_raises_error(self):
        """Test leverage exceeding 200x raises error."""
        with pytest.raises(ValueError, match="cannot exceed 200"):
            Position(
                symbol="BTCUSDT",
                side=Side.LONG,
                quantity=Decimal("0.1"),
                entry_price=Decimal("50000"),
                leverage=201,
            )


class TestPositionFactory:
    """Tests for PositionFactory domain service."""

    def test_create_position(self):
        """Test PositionFactory creates position with liquidation price."""
        position = PositionFactory.create_position(
            symbol="BTCUSDT",
            side=Side.LONG,
            quantity=Decimal("0.1"),
            entry_price=Decimal("50000"),
            leverage=2,
        )

        assert position.symbol == "BTCUSDT"
        assert position.side == Side.LONG
        assert position.quantity == Decimal("0.1")
        assert position.entry_price == Decimal("50000")
        assert position.leverage == 2
        assert position.liquidation_price is not None


class TestMarginCalculator:
    """Tests for MarginCalculator domain service."""

    def test_calculate_initial_margin(self):
        """Test initial margin calculation."""
        margin = MarginCalculator.calculate_initial_margin(
            quantity=Decimal("0.1"),
            entry_price=Decimal("50000"),
            leverage=2,
        )

        # InitialMargin = (0.1 * 50000) / 2 = 2500
        expected = Decimal("2500")
        assert margin == expected

    def test_calculate_initial_margin_10x(self):
        """Test initial margin with 10x leverage."""
        margin = MarginCalculator.calculate_initial_margin(
            quantity=Decimal("0.1"),
            entry_price=Decimal("50000"),
            leverage=10,
        )

        # InitialMargin = (0.1 * 50000) / 10 = 500
        expected = Decimal("500")
        assert margin == expected
