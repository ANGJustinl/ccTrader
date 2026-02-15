"""Domain services for the trading layer.

Provides stateless services that operate on domain objects.
"""
from decimal import Decimal

from .position import Position
from .value_objects import Side


class PositionFactory:
    """Factory service for creating Position instances."""

    @staticmethod
    def create_position(
        symbol: str,
        side: Side,
        quantity: Decimal,
        entry_price: Decimal,
        leverage: int = 1,
    ) -> Position:
        """Create a new Position with automatically calculated liquidation price.

        创建一个新的仓位实例，自动计算清算价格

        Args:
            symbol: Trading pair symbol
            side: Position side (LONG or SHORT)
            quantity: Position quantity
            entry_price: Average entry price
            leverage: Leverage multiplier (default: 1)

        Returns:
            Configured Position instance with liquidation price calculated
        """
        return Position(
            symbol=symbol,
            side=side,
            quantity=quantity,
            entry_price=entry_price,
            leverage=leverage,
        )


class MarginCalculator:
    """Service for calculating margin-related values."""

    @staticmethod
    def calculate_initial_margin(
        quantity: Decimal,
        entry_price: Decimal,
        leverage: int,
    ) -> Decimal:
        """Calculate initial margin required for a position.

        计算初始保证金:
        InitialMargin = (Quantity × EntryPrice) / Leverage

        Args:
            quantity: Position quantity
            entry_price: Entry price
            leverage: Leverage multiplier

        Returns:
            Required initial margin
        """
        position_value = quantity * entry_price
        return position_value / Decimal(leverage)
