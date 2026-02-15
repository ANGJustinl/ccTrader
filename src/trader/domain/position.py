"""Position aggregate root for the trading domain.

Represents a trading position with associated operations.
"""
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from .value_objects import Side, TradeFill


class Position(BaseModel):
    """Aggregate root representing a trading position.

    Attributes:
        symbol: Trading pair symbol
        side: Position side (LONG or SHORT)
        quantity: Position quantity (can be zero when closed)
        entry_price: Average entry price
        leverage: Leverage multiplier
        liquidation_price: Price at which position would be liquidated
        maintenance_margin_rate: Maintenance margin rate (default 0.5%)
    """

    symbol: str = Field(..., description="Trading pair symbol")
    side: Side = Field(..., description="Position side")
    quantity: Decimal = Field(default=Decimal("0"), ge=0, description="Position quantity")
    entry_price: Decimal = Field(default=Decimal("0"), gt=0, description="Average entry price")
    leverage: int = Field(default=1, gt=0, description="Leverage multiplier")
    liquidation_price: Decimal | None = Field(default=None, description="Liquidation price")
    maintenance_margin_rate: Decimal = Field(
        default=Decimal("0.005"), gt=0, description="Maintenance margin rate (0.5%)"
    )

    def __init__(self, **data):
        """Initialize position and calculate liquidation price."""
        super().__init__(**data)
        if self.quantity > Decimal("0"):
            self._recalculate_liquidation_price()

    @field_validator("leverage")
    @classmethod
    def validate_leverage(cls, v: int) -> int:
        """Validate leverage is within reasonable bounds."""
        if v > 200:
            raise ValueError("Leverage cannot exceed 200x")
        return v

    def increase(self, fill: TradeFill) -> None:
        """Increase position size (add to existing position).

        计算新的平均开仓价格:
        NewEntryPrice = (OldQty × OldPrice + NewQty × NewPrice) / TotalQty

        Args:
            fill: Trade fill representing the addition

        Raises:
            ValueError: If fill side does not match position side
        """
        if fill.side != self.side:
            raise ValueError(f"Cannot {fill.side} position with {self.side} fill")

        if self.quantity == Decimal("0"):
            # First fill for this position
            self.quantity = fill.quantity
            self.entry_price = fill.price
        else:
            # Calculate weighted average entry price
            total_quantity = self.quantity + fill.quantity
            old_value = self.quantity * self.entry_price
            new_value = fill.quantity * fill.price
            self.entry_price = (old_value + new_value) / total_quantity
            self.quantity = total_quantity

        self._recalculate_liquidation_price()

    def decrease(self, fill: TradeFill) -> Decimal:
        """Decrease position size (close partial or full position).

        计算已实现盈亏:
        RealizedPNL = (ExitPrice - EntryPrice) × Qty × Direction

        For SHORT positions, PNL is inverted (LONG=1, SHORT=-1)

        Args:
            fill: Trade fill representing the reduction

        Returns:
            Realized profit and loss

        Raises:
            ValueError: If fill side does not match position side
            ValueError: If fill quantity exceeds current position quantity
        """
        if fill.side != self.side:
            raise ValueError(f"Cannot {fill.side} position with {self.side} fill")

        if fill.quantity > self.quantity:
            raise ValueError("Fill quantity exceeds current position quantity")

        # Calculate realized PNL
        direction = 1 if self.side == Side.LONG else -1
        pnl = (fill.price - self.entry_price) * fill.quantity * direction

        # Update position
        remaining_qty = self.quantity - fill.quantity
        if remaining_qty == Decimal("0"):
            # Position fully closed
            self.quantity = Decimal("0")
            self.entry_price = Decimal("0")
            self.liquidation_price = None
        else:
            self.quantity = remaining_qty
            self._recalculate_liquidation_price()

        return pnl

    def calculate_unrealized_pnl(self, current_price: Decimal) -> Decimal:
        """Calculate unrealized profit and loss.

        计算未结盈亏:
        UnrealizedPNL = (CurrentPrice - EntryPrice) × Quantity × Direction

        For SHORT positions, PNL is inverted (LONG=1, SHORT=-1)

        Args:
            current_price: Current market price

        Returns:
            Unrealized profit and loss
        """
        if self.quantity == Decimal("0"):
            return Decimal("0")

        direction = 1 if self.side == Side.LONG else -1
        return (current_price - self.entry_price) * self.quantity * direction

    def calculate_maintenance_margin(self, current_price: Decimal) -> Decimal:
        """Calculate maintenance margin required for the position.

        计算维持保证金:
        MaintenanceMargin = PositionValue × MaintenanceMarginRate
        PositionValue = Quantity × CurrentPrice

        Args:
            current_price: Current market price

        Returns:
            Required maintenance margin
        """
        position_value = self.quantity * current_price
        return position_value * self.maintenance_margin_rate

    def is_closed(self) -> bool:
        """Check if position is closed (quantity is zero).

        Returns:
            True if position is closed, False otherwise
        """
        return self.quantity == Decimal("0")

    def _recalculate_liquidation_price(self) -> None:
        """Calculate and update liquidation price.

        多头清算价 = EntryPrice × (1 - 1/Leverage + MaintenanceMarginRate)
        空头清算价 = EntryPrice × (1 + 1/Leverage - MaintenanceMarginRate)
        """
        if self.quantity == Decimal("0"):
            self.liquidation_price = None
            return

        one_over_leverage = Decimal("1") / Decimal(self.leverage)

        if self.side == Side.LONG:
            # Long: price must drop to this level to be liquidated
            factor = Decimal("1") - one_over_leverage + self.maintenance_margin_rate
            self.liquidation_price = self.entry_price * factor
        else:
            # Short: price must rise to this level to be liquidated
            factor = Decimal("1") + one_over_leverage - self.maintenance_margin_rate
            self.liquidation_price = self.entry_price * factor
