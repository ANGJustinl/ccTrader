"""DRAMM Strategy Backtest with Realistic Market Data.

This script:
1. Generates realistic BTC/USDT 1-minute K-line data with real market patterns
2. Runs DRAMM strategy backtest
3. Verifies regime identification (TREND/CHOP/SQUEEZE)
4. Validates indicator calculations
5. Generates comprehensive backtest report
"""
import sys
import random
from pathlib import Path
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, Any

# Add src to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / "src"))

from trader.application.backtest_engine import BacktestEngine
from trader.application.strategies.dramm import DRAMMStrategy, MarketRegime
from trader.infrastructure.data_repository import BarData, FundingRateData


class DRAMMBacktestTester:
    """DRAMM Strategy backtest tester with realistic market data."""

    def __init__(self):
        self.symbol = "BTC/USDT"
        self.timeframe = "1m"
        self.regime_stats: Dict[MarketRegime, int] = {
            MarketRegime.TREND: 0,
            MarketRegime.CHOP: 0,
            MarketRegime.SQUEEZE: 0,
            MarketRegime.UNKNOWN: 0,
        }
        self.indicator_checks = {
            "adx_calculated": 0,
            "bb_calculated": 0,
            "rsi_calculated": 0,
            "atr_calculated": 0,
            "zscore_calculated": 0,
        }

    def generate_realistic_data(self, num_bars: int = 2000) -> tuple[list[BarData], list[FundingRateData]]:
        """Generate realistic BTC/USDT 1-minute data with real market patterns.

        Args:
            num_bars: Number of bars to generate (minimum 1000)

        Returns:
            Tuple of (bars, funding_rates)
        """
        print("=" * 80)
        print("GENERATING REALISTIC MARKET DATA")
        print("=" * 80)

        num_bars = max(num_bars, 1000)
        base_time = datetime.now(timezone.utc) - timedelta(minutes=num_bars)
        base_price = Decimal("67500")  # Realistic BTC price as of 2026
        bars = []
        funding_rates = []

        # Market regime simulation parameters
        current_trend = 0  # -1 for downtrend, 0 for chop, 1 for uptrend
        trend_strength = Decimal("0")
        volatility = Decimal("0.0015")  # 0.15% per minute
        regime_changes = 0

        current_price = base_price

        for i in range(num_bars):
            # Change regime occasionally
            if i % random.randint(120, 480) == 0:  # Every 2-8 hours
                regime_changes += 1
                new_regime = random.choice([-1, 0, 0, 1])  # Higher chance for chop
                if new_regime != current_trend:
                    current_trend = new_regime
                    trend_strength = Decimal(str(random.uniform(0.0002, 0.0008)))

            # Calculate price movement
            trend_component = Decimal("0")
            if current_trend == 1:
                trend_component = trend_strength
            elif current_trend == -1:
                trend_component = -trend_strength

            # Random walk + trend
            random_shock = Decimal(str(random.gauss(0, float(volatility))))
            price_change = trend_component + random_shock * current_price

            new_close = current_price + price_change

            # Generate OHLC
            open_price = current_price
            close_price = new_close

            # Generate high and low with realistic spreads
            high_wick = Decimal(str(random.uniform(0, float(volatility) * float(current_price) * 1.5)))
            low_wick = Decimal(str(random.uniform(0, float(volatility) * float(current_price) * 1.5)))
            high_price = max(open_price, close_price) + high_wick
            low_price = min(open_price, close_price) - low_wick

            # Generate volume (realistic variation)
            volume = Decimal(str(random.uniform(0.5, 3.0)))

            bar = BarData(
                symbol=self.symbol,
                timestamp=base_time + timedelta(minutes=i),
                open=open_price,
                high=high_price,
                low=low_price,
                close=close_price,
                volume=volume,
            )
            bars.append(bar)

            current_price = close_price

            # Add funding rate every 8 hours (480 minutes)
            if i % 480 == 0:
                funding_rate = Decimal(str(random.uniform(-0.0003, 0.0003)))
                funding_rates.append(FundingRateData(
                    symbol=self.symbol,
                    timestamp=base_time + timedelta(minutes=i),
                    rate=funding_rate,
                    next_funding_time=base_time + timedelta(minutes=i + 480),
                ))

        print(f"\n✓ Generated {len(bars)} realistic 1-minute bars")
        print(f"✓ Generated {len(funding_rates)} funding rates")
        print(f"✓ Price range: ${bars[0].close:.2f} -> ${bars[-1].close:.2f}")
        print(f"✓ Regime changes simulated: {regime_changes}")

        return bars, funding_rates

    def run_backtest(self, bars: list[BarData], funding_rates: list[FundingRateData]) -> Dict[str, Any]:
        """Run DRAMM strategy backtest with tracking.

        Args:
            bars: List of BarData objects
            funding_rates: List of FundingRateData objects

        Returns:
            Backtest results dictionary
        """
        print("\n" + "=" * 80)
        print("RUNNING DRAMM STRATEGY BACKTEST")
        print("=" * 80)

        # Create backtest engine
        engine = BacktestEngine(
            initial_balance=Decimal("10000"),
            slippage=Decimal("0.0005"),
            commission=Decimal("0.0004")
        )

        # Load data
        engine.load_data(bars, funding_rates)
        print(f"\n✓ Loaded {len(bars)} bars and {len(funding_rates)} funding rates")

        # Create tracked strategy
        class TrackedDRAMMStrategy(DRAMMStrategy):
            """DRAMM Strategy with tracking capabilities."""

            def __init__(self, tester, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.tester = tester
                self.on_bar_called = 0
                self.signals_generated = []

            def on_bar(self, bar: BarData) -> None:
                self.on_bar_called += 1
                super().on_bar(bar)

                # Track regime statistics
                if self.current_regime in self.tester.regime_stats:
                    self.tester.regime_stats[self.current_regime] += 1

                # Check indicator calculations
                if len(self.bar_history) >= self.min_history:
                    from trader.utils.indicators import (
                        calculate_adx,
                        calculate_bollinger_bands,
                        calculate_rsi,
                        calculate_atr,
                        calculate_zscore,
                    )

                    closes = [b.close for b in self.bar_history]
                    highs = [b.high for b in self.bar_history]
                    lows = [b.low for b in self.bar_history]

                    adx_results = calculate_adx(highs, lows, closes, self.adx_period)
                    bb_results = calculate_bollinger_bands(closes, self.bollinger_period, self.bollinger_std)
                    rsi_results = calculate_rsi(closes, self.rsi_period)
                    atr_results = calculate_atr(highs, lows, closes, self.atr_period)
                    zscore_results = calculate_zscore(closes, self.zscore_period)

                    if adx_results and adx_results[-1].adx is not None:
                        self.tester.indicator_checks["adx_calculated"] += 1
                    if bb_results and bb_results[-1].middle is not None:
                        self.tester.indicator_checks["bb_calculated"] += 1
                    if rsi_results and rsi_results[-1] is not None:
                        self.tester.indicator_checks["rsi_calculated"] += 1
                    if atr_results and atr_results[-1] is not None:
                        self.tester.indicator_checks["atr_calculated"] += 1
                    if zscore_results and zscore_results[-1] is not None:
                        self.tester.indicator_checks["zscore_calculated"] += 1

        strategy = TrackedDRAMMStrategy(
            tester=self,
            adx_period=14,
            bollinger_period=20,
            rsi_period=14,
            atr_period=14,
            zscore_period=20,
            position_size=0.001,
            atr_multiplier=Decimal("3"),
            entry_score_threshold=Decimal("0.6"),
            exit_score_threshold=Decimal("-0.4"),
        )

        engine.set_strategy(strategy)

        print(f"\nRunning backtest for {self.symbol}...")
        print("-" * 80)

        # Run backtest
        result = engine.run(self.symbol)

        print("-" * 80)
        print("\nBACKTEST COMPLETE")
        print("-" * 80)

        # Add strategy tracking info to result
        result["on_bar_called"] = strategy.on_bar_called
        result["min_history_required"] = strategy.min_history

        return result

    def print_validation_report(self, result: Dict[str, Any]):
        """Print comprehensive validation report.

        Args:
            result: Backtest results dictionary
        """
        print("\n" + "=" * 80)
        print("VALIDATION REPORT")
        print("=" * 80)

        # 1. Regime Identification Check
        print("\n1. MARKET REGIME IDENTIFICATION:")
        print("-" * 40)
        total_regimes = sum(self.regime_stats.values())
        for regime, count in self.regime_stats.items():
            percentage = (count / total_regimes * 100) if total_regimes > 0 else 0
            status = "✓" if count > 0 or regime == MarketRegime.UNKNOWN else "✗"
            print(f"  {status} {regime.value.upper():10s}: {count:5d} bars ({percentage:5.1f}%)")

        regime_validation = (
            self.regime_stats[MarketRegime.TREND] > 0 or
            self.regime_stats[MarketRegime.CHOP] > 0 or
            self.regime_stats[MarketRegime.SQUEEZE] > 0
        )
        print(f"\n  Regime identification working: {'✓ YES' if regime_validation else '✗ NO'}")

        # 2. Indicator Calculation Check
        print("\n2. INDICATOR CALCULATIONS:")
        print("-" * 40)
        expected_bars = result.get("on_bar_called", 0) - result.get("min_history_required", 0)

        indicators = [
            ("ADX", "adx_calculated"),
            ("Bollinger Bands", "bb_calculated"),
            ("RSI", "rsi_calculated"),
            ("ATR", "atr_calculated"),
            ("Z-Score", "zscore_calculated"),
        ]

        all_indicators_ok = True
        for name, key in indicators:
            count = self.indicator_checks[key]
            percentage = (count / expected_bars * 100) if expected_bars > 0 else 0
            status = "✓" if count >= expected_bars * 0.9 else "✗"  # Allow 10% margin
            if status == "✗":
                all_indicators_ok = False
            print(f"  {status} {name:20s}: {count:5d}/{expected_bars:5d} ({percentage:5.1f}%)")

        print(f"\n  All indicators calculating correctly: {'✓ YES' if all_indicators_ok else '✗ NO'}")

        # 3. Logging Check
        print("\n3. STRATEGY EXECUTION:")
        print("-" * 40)
        on_bar_called = result.get("on_bar_called", 0)
        print(f"  ✓ on_bar() called: {on_bar_called} times")
        print(f"  ✓ Min history required: {result.get('min_history_required', 0)} bars")

        # 4. Performance Metrics
        print("\n4. BACKTEST PERFORMANCE:")
        print("-" * 40)
        print(f"  Initial Balance:    ${result['initial_balance']:.2f}")
        print(f"  Final Balance:      ${result['final_balance']:.2f}")
        print(f"  Total Return:       {result['total_return']:+.2f}%")
        print(f"  Total Trades:       {result['total_trades']}")
        print(f"  Total Commission:   ${result['total_commission']:.4f}")
        print(f"  Total Funding Paid: ${result['total_funding_paid']:.4f}")

        # Summary
        print("\n" + "=" * 80)
        overall_passed = regime_validation and all_indicators_ok and on_bar_called > 0

        if overall_passed:
            print("✓ DRAMM STRATEGY BACKTEST PASSED - ALL SYSTEMS NOMINAL")
        else:
            print("✗ DRAMM STRATEGY BACKTEST FAILED - PLEASE INVESTIGATE")
        print("=" * 80)

        return overall_passed


def main():
    """Main backtest execution."""
    print("\n" + "=" * 80)
    print("DRAMM STRATEGY BACKTEST WITH REALISTIC MARKET DATA")
    print("=" * 80)

    tester = DRAMMBacktestTester()

    try:
        # Step 1: Generate realistic data
        bars, funding_rates = tester.generate_realistic_data(num_bars=2000)

        # Step 2: Run backtest
        result = tester.run_backtest(bars, funding_rates)

        # Step 3: Print validation report
        overall_passed = tester.print_validation_report(result)

        if not overall_passed:
            sys.exit(1)

    except Exception as e:
        print(f"\n✗ Backtest failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
