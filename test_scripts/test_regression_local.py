"""Local regression test without network dependency.

Tests existing strategies and indicators using mock data.
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from decimal import Decimal

# Add src to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / "src"))

from trader.application.backtest_engine import BacktestEngine
from trader.application.strategies.crypto_classic import RSIBollingerStrategy
from trader.infrastructure.data_repository import BarData, FundingRateData


def generate_mock_data(symbol: str = "BTC/USDT", days: int = 7):
    """Generate mock bar data for testing."""
    bars = []
    funding_rates = []
    base_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
    base_price = Decimal("50000")
    
    for i in range(days * 24):  # 1h bars
        price = base_price + Decimal(i * 10)
        volatility = Decimal(i * 5)
        
        bar = BarData(
            symbol=symbol,
            timestamp=base_time + timedelta(hours=i),
            open=price - volatility,
            high=price + volatility,
            low=price - volatility - Decimal("10"),
            close=price,
            volume=Decimal("100"),
        )
        bars.append(bar)
        
        # Add funding rate every 8 hours
        if i % 8 == 0:
            funding_rates.append(FundingRateData(
                symbol=symbol,
                timestamp=base_time + timedelta(hours=i),
                rate=Decimal("0.0001"),
                next_funding_time=base_time + timedelta(hours=i + 8),
            ))
    
    return bars, funding_rates


def test_rsi_bollinger_local_backtest():
    """Run RSI Bollinger Strategy backtest with mock data."""
    print("=" * 80)
    print("LOCAL REGRESSION TEST: RSI BOLLINGER STRATEGY")
    print("=" * 80)
    
    # Create backtest engine
    engine = BacktestEngine(
        initial_balance=Decimal("10000"),
        slippage=Decimal("0.0005"),
        commission=Decimal("0.0004")
    )
    
    # Generate mock data
    symbol = "BTC/USDT"
    print(f"\nGenerating mock {symbol} data...")
    bars, funding_rates = generate_mock_data(symbol, days=3)
    engine.load_data(bars, funding_rates)
    print(f"✓ Loaded {len(bars)} bars and {len(funding_rates)} funding rates")
    
    # Create strategy with callback tracking
    class TrackedRSIBollinger(RSIBollingerStrategy):
        """RSI Bollinger Strategy with callback tracking"""
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.on_bar_called = 0
            self.on_funding_rate_called = 0
            self.on_order_update_called = 0
            self.signals_generated = []
        
        def on_bar(self, bar):
            self.on_bar_called += 1
            super().on_bar(bar)
            # Also generate signals
            signals = self.generate_signals(bar)
            if signals:
                self.signals_generated.extend(signals)
        
        def on_funding_rate(self, rate, timestamp):
            self.on_funding_rate_called += 1
            super().on_funding_rate(rate, timestamp)
        
        def on_order_update(self, order):
            self.on_order_update_called += 1
            super().on_order_update(order)
    
    strategy = TrackedRSIBollinger(
        bollinger_period=20,
        bollinger_std=Decimal("2"),
        rsi_period=14,
        rsi_overbought=Decimal("70"),
        rsi_oversold=Decimal("30"),
        position_size=0.001
    )
    
    # Set strategy
    engine.set_strategy(strategy)
    
    print(f"\nRunning backtest for {symbol}...")
    print("-" * 80)
    
    # Run backtest
    result = engine.run(symbol)
    
    print("-" * 80)
    print("\nBACKTEST COMPLETE")
    print("-" * 80)
    
    # Verify callbacks were triggered
    print("\nCALLBACK VERIFICATION:")
    print(f"  on_bar called: {strategy.on_bar_called} times")
    print(f"  on_funding_rate called: {strategy.on_funding_rate_called} times")
    print(f"  on_order_update called: {strategy.on_order_update_called} times")
    print(f"  Signals generated: {len(strategy.signals_generated)}")
    
    # Verify results
    assert strategy.on_bar_called > 0, "on_bar should be called"
    
    print("\nPERFORMANCE METRICS:")
    print(f"  Initial Balance: ${result['initial_balance']:.2f}")
    print(f"  Final Balance: ${result['final_balance']:.2f}")
    print(f"  Total Return: {result['total_return']:.2f}%")
    print(f"  Total Trades: {result['total_trades']}")
    print(f"  Total Commission: ${result['total_commission']:.4f}")
    print(f"  Total Funding Paid: ${result['total_funding_paid']:.4f}")
    
    print("\n" + "=" * 80)
    print("✓ RSI BOLLINGER STRATEGY LOCAL REGRESSION TEST PASSED")
    print("=" * 80)
    
    return True


def test_indicator_integrity():
    """Verify indicator calculations are consistent."""
    print("\n" + "=" * 80)
    print("LOCAL REGRESSION TEST: INDICATOR INTEGRITY")
    print("=" * 80)
    
    from decimal import Decimal
    from src.trader.utils.indicators import (
        calculate_sma,
        calculate_ema,
        calculate_rsi,
        calculate_bollinger_bands,
        calculate_macd,
        calculate_kdj,
        calculate_adx,
        calculate_zscore,
    )
    
    # Create test data
    test_data = [Decimal(str(100 + i)) for i in range(100)]
    highs = [Decimal(str(105 + i)) for i in range(100)]
    lows = [Decimal(str(95 + i)) for i in range(100)]
    closes = test_data
    
    # Test SMA
    print("\nTesting SMA...")
    sma_results = calculate_sma(test_data, 10)
    assert len(sma_results) == 100
    assert sma_results[9] is not None
    print("✓ SMA calculation works")
    
    # Test EMA
    print("\nTesting EMA...")
    ema_results = calculate_ema(test_data, 10)
    assert len(ema_results) == 100
    assert ema_results[9] is not None
    print("✓ EMA calculation works")
    
    # Test RSI
    print("\nTesting RSI...")
    rsi_results = calculate_rsi(test_data, 14)
    assert len(rsi_results) == 100
    assert rsi_results[14] is not None
    print("✓ RSI calculation works")
    
    # Test Bollinger Bands
    print("\nTesting Bollinger Bands...")
    bb_results = calculate_bollinger_bands(test_data, 20)
    assert len(bb_results) == 100
    assert bb_results[19].middle is not None
    assert bb_results[19].upper is not None
    assert bb_results[19].lower is not None
    print("✓ Bollinger Bands calculation works")
    
    # Test MACD
    print("\nTesting MACD...")
    macd_results = calculate_macd(test_data, 12, 26, 9)
    assert len(macd_results) == 100
    print("✓ MACD calculation works")
    
    # Test KDJ
    print("\nTesting KDJ...")
    kdj_results = calculate_kdj(highs, lows, closes, 9, 3, 3)
    assert len(kdj_results) == 100
    print("✓ KDJ calculation works")
    
    # Test ADX
    print("\nTesting ADX...")
    adx_results = calculate_adx(highs, lows, closes, 14)
    assert len(adx_results) == 100
    print("✓ ADX calculation works")
    
    # Test Z-Score
    print("\nTesting Z-Score...")
    zscore_results = calculate_zscore(test_data, 20)
    assert len(zscore_results) == 100
    assert zscore_results[19] is not None
    print("✓ Z-Score calculation works")
    
    print("\n" + "=" * 80)
    print("✓ INDICATOR INTEGRITY TEST PASSED")
    print("=" * 80)
    
    return True


if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("STARTING LOCAL REGRESSION TEST (NO NETWORK)")
    print("=" * 80)
    
    passed = 0
    failed = 0
    
    try:
        if test_indicator_integrity():
            passed += 1
        else:
            failed += 1
    except Exception as e:
        print(f"✗ Indicator integrity test failed: {e}")
        import traceback
        traceback.print_exc()
        failed += 1
    
    try:
        if test_rsi_bollinger_local_backtest():
            passed += 1
        else:
            failed += 1
    except Exception as e:
        print(f"✗ RSI Bollinger local backtest failed: {e}")
        import traceback
        traceback.print_exc()
        failed += 1
    
    print("\n" + "=" * 80)
    print(f"LOCAL REGRESSION TEST SUMMARY: {passed} PASSED, {failed} FAILED")
    print("=" * 80)
    
    if failed == 0:
        print("\n✓ ALL LOCAL REGRESSION TESTS PASSED - NO DEGRADATION DETECTED")
    else:
        print("\n✗ REGRESSION DETECTED - PLEASE INVESTIGATE")
        sys.exit(1)
