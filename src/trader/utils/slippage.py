"""Slippage models for realistic trade execution.

Provides various slippage models for backtesting, including volatility-based
slippage that adjusts based on market conditions.
"""
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, Field


class BarDataForSlippage(BaseModel):
    """Bar data structure for slippage calculation."""
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Optional[Decimal] = None


class VolatilitySlippageModel(BaseModel):
    """Volatility-based slippage model.

    Calculates slippage based on recent market volatility using ATR
    (Average True Range) or simple volatility measures.

    Attributes:
        base_slippage: Minimum slippage rate (default: 0.0005 = 0.05%)
        max_slippage: Maximum slippage rate (default: 0.005 = 0.5%)
        volatility_factor: Multiplier for volatility to slippage (default: 0.1)
        lookback_period: Number of bars to calculate volatility (default: 14)
    """
    base_slippage: Decimal = Field(default=Decimal("0.0005"), description="Minimum slippage rate")
    max_slippage: Decimal = Field(default=Decimal("0.005"), description="Maximum slippage rate")
    volatility_factor: Decimal = Field(default=Decimal("0.1"), description="Volatility to slippage multiplier")
    lookback_period: int = Field(default=14, description="Number of bars for volatility calculation")

    def calculate_volatility(self, bars: List[BarDataForSlippage]) -> Decimal:
        """Calculate market volatility from recent bars.

        Uses simple True Range calculation over the lookback period.

        Args:
            bars: List of recent bar data

        Returns:
            Average volatility as a percentage of price
        """
        if not bars or len(bars) < 2:
            return Decimal("0")

        # Use at most lookback_period bars
        recent_bars = bars[-self.lookback_period:] if len(bars) > self.lookback_period else bars

        true_ranges = []
        for i in range(1, len(recent_bars)):
            prev_bar = recent_bars[i - 1]
            curr_bar = recent_bars[i]

            # Calculate True Range components
            high_low = curr_bar.high - curr_bar.low
            high_close_prev = abs(curr_bar.high - prev_bar.close)
            low_close_prev = abs(curr_bar.low - prev_bar.close)

            # True Range is the maximum of the three
            true_range = max(high_low, high_close_prev, low_close_prev)

            # Normalize by previous close to get percentage
            if prev_bar.close > Decimal("0"):
                tr_pct = true_range / prev_bar.close
                true_ranges.append(tr_pct)

        if not true_ranges:
            return Decimal("0")

        # Average True Range percentage
        avg_tr = sum(true_ranges) / Decimal(str(len(true_ranges)))
        return avg_tr

    def calculate_slippage(
        self,
        bars: List[BarDataForSlippage],
        side: str,  # "buy" or "sell"
    ) -> Decimal:
        """Calculate slippage rate based on market volatility.

        Args:
            bars: List of recent bar data for volatility calculation
            side: Order side ("buy" or "sell")

        Returns:
            Slippage rate as a decimal (e.g., 0.001 = 0.1%)
        """
        volatility = self.calculate_volatility(bars)

        # Calculate slippage: base + (volatility * factor)
        slippage = self.base_slippage + (volatility * self.volatility_factor)

        # Clamp to max slippage
        slippage = min(slippage, self.max_slippage)

        return slippage

    def apply_slippage(
        self,
        price: Decimal,
        bars: List[BarDataForSlippage],
        side: str,
    ) -> Decimal:
        """Apply slippage to a price.

        Args:
            price: Original price
            bars: List of recent bar data
            side: Order side ("buy" or "sell")

        Returns:
            Price with slippage applied
        """
        slippage_rate = self.calculate_slippage(bars, side)

        if side == "buy":
            # Buy orders pay higher price (slippage added)
            return price * (Decimal("1") + slippage_rate)
        else:
            # Sell orders get lower price (slippage subtracted)
            return price * (Decimal("1") - slippage_rate)


def calculate_slippage(
    price: Decimal,
    volatility: Decimal,
    side: str,
    base_slippage: Decimal = Decimal("0.0005"),
    max_slippage: Decimal = Decimal("0.005"),
    volatility_factor: Decimal = Decimal("0.1"),
) -> Decimal:
    """Simple function to calculate slippage.

    A convenience function that doesn't require the VolatilitySlippageModel class.

    Args:
        price: Original price
        volatility: Current market volatility (as percentage of price)
        side: Order side ("buy" or "sell")
        base_slippage: Minimum slippage rate (default: 0.0005)
        max_slippage: Maximum slippage rate (default: 0.005)
        volatility_factor: Multiplier for volatility (default: 0.1)

    Returns:
        Price with slippage applied
    """
    slippage_rate = base_slippage + (volatility * volatility_factor)
    slippage_rate = min(slippage_rate, max_slippage)

    if side == "buy":
        return price * (Decimal("1") + slippage_rate)
    else:
        return price * (Decimal("1") - slippage_rate)
