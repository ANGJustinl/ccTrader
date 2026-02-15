
"""Classic crypto trading strategies.

Includes:
- RSI_Bollinger_Strategy: Trend + reversal composite strategy
- Funding_Arbitrage_Strategy: Observer for funding rate opportunities
"""
from datetime import datetime
from decimal import Decimal
from typing import List
from ..strategy import BaseStrategy
from ...infrastructure.data_repository import BarData
from ...utils.indicators import (
    calculate_bollinger_bands,
    calculate_rsi,
    BollingerBandsResult,
    StreamingBollingerBands,
    StreamingKDJ,
)
from ..order import Order


class RSIBollingerStrategy(BaseStrategy):
    """RSI + Bollinger Bands Composite Strategy.

    Strategy Logic:
    - Trend Confirmation: Bollinger Band width expansion
    - Reversal Confirmation: RSI overbought/oversold
    - Entry: Trend + Reversal aligned
    - Exit: Opposite signal or take profit/stop loss
    """

    def __init__(
        self,
        bollinger_period: int = 20,
        bollinger_std: Decimal = Decimal("2"),
        rsi_period: int = 14,
        rsi_overbought: Decimal = Decimal("70"),
        rsi_oversold: Decimal = Decimal("30"),
        position_size: float = 0.01,
        stop_loss_pct: Decimal = Decimal("0.02"),  # 2%
        take_profit_pct: Decimal = Decimal("0.04"),  # 4%
    ):
        super().__init__("RSI+Bollinger")
        self.bollinger_period = bollinger_period
        self.bollinger_std = bollinger_std
        self.rsi_period = rsi_period
        self.rsi_overbought = rsi_overbought
        self.rsi_oversold = rsi_oversold
        self.position_size = position_size
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct

        self.bar_history: List[BarData] = []
        self.entry_price: Decimal | None = None

        # Streaming indicators for real-time use
        self.streaming_bb = StreamingBollingerBands(
            period=bollinger_period,
            std_dev=bollinger_std,
            window_size=100,
        )

    def on_bar(self, bar: BarData) -> None:
        """Bar callback with strategy logic."""
        print(f"[Strategy] on_bar() called at {bar.timestamp}")
        self.bar_history.append(bar)

        # Keep sufficient history
        max_history = max(self.bollinger_period, self.rsi_period) + 10
        if len(self.bar_history) > max_history:
            self.bar_history.pop(0)

        # Update streaming indicator
        self.streaming_bb.update(bar.close)

        # Need enough data
        if len(self.bar_history) < max(self.bollinger_period, self.rsi_period):
            print(f"[Strategy] Not enough data: {len(self.bar_history)}/{max(self.bollinger_period, self.rsi_period)}")
            return

        # Calculate indicators
        closes = [b.close for b in self.bar_history]
        bb_results = calculate_bollinger_bands(closes, self.bollinger_period, self.bollinger_std)
        rsi_results = calculate_rsi(closes, self.rsi_period)

        current_bb = bb_results[-1] if bb_results else None
        current_rsi = rsi_results[-1] if rsi_results else None

        if current_bb is None or current_rsi is None:
            return

        # Get current position
        print(f"[Strategy] Checking position for {bar.symbol}...")
        position = self.broker.get_position(bar.symbol)
        print(f"[Strategy] Position: {position is not None}")
        if position:
            print(f"[Strategy]   Side: {position.side}, Qty: {position.quantity}")

        # Generate signals
        if position is None:
            # No position, look for entry
            print(f"[Strategy] No position, checking entry signals...")
            self._check_entry_signals(bar, current_bb, current_rsi)
        else:
            # In position, look for exit
            print(f"[Strategy] In position, checking exit signals...")
            self._check_exit_signals(bar, current_bb, current_rsi)

    def _check_entry_signals(
        self,
        bar: BarData,
        bb: BollingerBandsResult,
        rsi: Decimal,
    ) -> None:
        """Check for entry conditions."""
        # Debug log
        percent_b_str = f"{bb.percent_b:.2f}" if bb.percent_b else "None"
        print(f"[Strategy] Checking entry: RSI={rsi:.2f}, %B={percent_b_str} | Thresholds: RSI<{self.rsi_oversold}/>{self.rsi_overbought}, %B<0.3/>0.7")
        
        # Long entry: Oversold RSI + Price near/above lower band
        if rsi < self.rsi_oversold and bb.percent_b is not None and bb.percent_b < Decimal("0.3"):
            print(f"[Strategy] 🔥 LONG ENTRY SIGNAL TRIGGERED! RSI={rsi:.2f} < {self.rsi_oversold}, %B={bb.percent_b:.2f} < 0.3")
            self.create_market_order(
                symbol=bar.symbol,
                side="buy",
                quantity=self.position_size,
            )
            self.entry_price = bar.close

        # Short entry: Overbought RSI + Price near/below upper band
        elif rsi > self.rsi_overbought and bb.percent_b is not None and bb.percent_b > Decimal("0.7"):
            print(f"[Strategy] 🔥 SHORT ENTRY SIGNAL TRIGGERED! RSI={rsi:.2f} > {self.rsi_overbought}, %B={bb.percent_b:.2f} > 0.7")
            self.create_market_order(
                symbol=bar.symbol,
                side="sell",
                quantity=self.position_size,
            )
            self.entry_price = bar.close

    def _check_exit_signals(
        self,
        bar: BarData,
        bb: BollingerBandsResult,
        rsi: Decimal,
    ) -> None:
        """Check for exit conditions."""
        position = self.broker.get_position(bar.symbol)
        if position is None or self.entry_price is None:
            return

        side = position.side.value
        pnl_pct = (bar.close - self.entry_price) / self.entry_price

        # Stop loss / Take profit
        if side == "LONG":
            if pnl_pct < -self.stop_loss_pct or pnl_pct > self.take_profit_pct:
                print(f"[Strategy] LONG EXIT (SL/TP): PnL={pnl_pct:.2%}")
                self.create_market_order(
                    symbol=bar.symbol,
                    side="sell",
                    quantity=float(position.quantity),
                )
                self.entry_price = None
            # Exit signal: RSI overbought or price crosses upper band
            elif rsi > self.rsi_overbought or (bb.percent_b is not None and bb.percent_b > Decimal("0.9")):
                print(f"[Strategy] LONG EXIT (Signal): RSI={rsi:.2f}, %B={bb.percent_b:.2f}")
                self.create_market_order(
                    symbol=bar.symbol,
                    side="sell",
                    quantity=float(position.quantity),
                )
                self.entry_price = None
        elif side == "SHORT":
            if pnl_pct > self.stop_loss_pct or pnl_pct < -self.take_profit_pct:
                print(f"[Strategy] SHORT EXIT (SL/TP): PnL={pnl_pct:.2%}")
                self.create_market_order(
                    symbol=bar.symbol,
                    side="buy",
                    quantity=float(position.quantity),
                )
                self.entry_price = None
            # Exit signal: RSI oversold or price crosses lower band
            elif rsi < self.rsi_oversold or (bb.percent_b is not None and bb.percent_b < Decimal("0.1")):
                print(f"[Strategy] SHORT EXIT (Signal): RSI={rsi:.2f}, %B={bb.percent_b:.2f}")
                self.create_market_order(
                    symbol=bar.symbol,
                    side="buy",
                    quantity=float(position.quantity),
                )
                self.entry_price = None

    def generate_signals(self, bar: BarData) -> List[dict]:
        """Signal generation interface."""
        signals = []
        self.bar_history.append(bar)

        max_history = max(self.bollinger_period, self.rsi_period) + 10
        if len(self.bar_history) > max_history:
            self.bar_history.pop(0)

        if len(self.bar_history) < max(self.bollinger_period, self.rsi_period):
            return signals

        closes = [b.close for b in self.bar_history]
        bb_results = calculate_bollinger_bands(closes, self.bollinger_period, self.bollinger_std)
        rsi_results = calculate_rsi(closes, self.rsi_period)

        current_bb = bb_results[-1] if bb_results else None
        current_rsi = rsi_results[-1] if rsi_results else None

        if current_bb is None or current_rsi is None:
            return signals

        position = self.broker.get_position(bar.symbol)

        if position is None:
            if current_rsi < self.rsi_oversold and current_bb.percent_b is not None and current_bb.percent_b < Decimal("0.3"):
                signals.append({
                    "type": "entry",
                    "symbol": bar.symbol,
                    "side": "buy",
                    "quantity": self.position_size,
                    "price": float(bar.close),
                    "reason": "RSI oversold + Bollinger lower band",
                })
            elif current_rsi > self.rsi_overbought and current_bb.percent_b is not None and current_bb.percent_b > Decimal("0.7"):
                signals.append({
                    "type": "entry",
                    "symbol": bar.symbol,
                    "side": "sell",
                    "quantity": self.position_size,
                    "price": float(bar.close),
                    "reason": "RSI overbought + Bollinger upper band",
                })

        return signals


class FundingArbitrageStrategy(BaseStrategy):
    """Funding Rate Arbitrage Observer Strategy.

    This is an MVP single-leg observer that:
    - Monitors funding rate changes
    - Calculates potential arbitrage profits
    - Logs opportunities without executing trades
    - Avoids multi-symbol complexity

    For full arbitrage, you'd need: Long Spot + Short Perpetual
    """

    def __init__(
        self,
        min_funding_spread: Decimal = Decimal("0.0001"),  # 0.01%
    ):
        super().__init__("FundingArbObserver")
        self.min_funding_spread = min_funding_spread

        self.funding_history: List[tuple[datetime, Decimal]] = []
        self.opportunities: List[dict] = []

    def on_funding_rate(self, rate: Decimal, timestamp: datetime) -> None:
        """Funding rate callback - detects arbitrage opportunities."""
        self.funding_history.append((timestamp, rate))

        # Keep last 100 funding rates
        if len(self.funding_history) > 100:
            self.funding_history.pop(0)

        # Analyze opportunity
        if len(self.funding_history) >= 2:
            prev_rate = self.funding_history[-2][1]
            rate_change = rate - prev_rate

            opportunity = {
                "timestamp": timestamp.isoformat(),
                "current_rate": float(rate),
                "previous_rate": float(prev_rate),
                "change_bps": float(rate_change * Decimal("10000")),
                "is_positive": rate > Decimal("0"),
                "is_significant": abs(rate) >= self.min_funding_spread,
                "estimated_daily_yield": float(rate * Decimal("3")),  # 3 settlements per day
            }

            self.opportunities.append(opportunity)

            # Log the opportunity
            if opportunity["is_significant"]:
                if opportunity["is_positive"]:
                    self._log_opportunity(
                        "Long Spot + Short Perp",
                        f"Funding +{opportunity['estimated_daily_yield']:.4%} daily",
                    )
                else:
                    self._log_opportunity(
                        "Short Spot + Long Perp",
                        f"Funding {opportunity['estimated_daily_yield']:.4%} daily",
                    )

    def _log_opportunity(self, strategy: str, description: str) -> None:
        """Log a potential arbitrage opportunity."""
        msg = f"[FundingArb] Opportunity: {strategy} | {description}"
        print(msg)

    def on_bar(self, bar: BarData) -> None:
        """Bar callback - not used for this observer strategy."""
        pass

    def generate_signals(self, bar: BarData) -> List[dict]:
        """Signal generation - returns informational signals only."""
        signals = []
        if self.opportunities:
            last_opp = self.opportunities[-1]
            if last_opp["is_significant"]:
                signals.append({
                    "type": "info",
                    "symbol": bar.symbol,
                    "side": "funding_arb",
                    "quantity": 0,
                    "price": float(bar.close),
                    "opportunity": last_opp,
                })
        return signals

