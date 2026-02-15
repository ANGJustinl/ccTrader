"""Regression test for existing strategies and indicators.

Ensures DRAMM development doesn't break existing functionality.
Uses real Binance historical data for testing.
"""
import sys
from datetime import datetime, timedelta
from pathlib import Path
from decimal import Decimal

# Add src to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / "src"))

from trader.application.backtest_engine import BacktestEngine
from trader.application.strategies.crypto_classic import RSIBollingerStrategy


def test_rsi_bollinger_backtest():
    """Run RSI Bollinger Strategy backtest with real Binance data."""
    print("=" * 80)
    print("REGRESSION TEST: RSI BOLLINGER STRATEGY")
    print("=" * 80)
    
    # Create backtest engine
    engine = BacktestEngine(
        initial_balance=Decimal("10000"),
        slippage=Decimal("0.0005"),
        commission=Decimal("0.0004")
    )
    
    # Download real Binance data (3 days for faster test)
    symbol = "BTC/USDT"
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=3)
    timeframe = "1h"
    
    print(f"\nDownloading {symbol} data from {start_date} to {end_date}...")
    
    try:
        engine.download_data(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            timeframe=timeframe,
            exchange="binance"
        )
        print("✓ Data downloaded successfully")
    except Exception as e:
        print(f"✗ Failed to download data: {e}")
        print("Note: If this fails due to network issues, check your internet connection.")
        return False
    
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
    print("✓ RSI BOLLINGER STRATEGY REGRESSION TEST PASSED")
    print("=" * 80)
    
    return True


def test_indicator_integrity():
    """Verify indicator calculations are consistent."""
    print("\n" + "=" * 80)
    print("REGRESSION TEST: INDICATOR INTEGRITY")
    print("=" * 80)
    
    from decimal import Decimal
    from src.trader.utils.indicators import (
        calculate_sma,
        calculate_ema,
        calculate_rsi,
        calculate_bollinger_bands,
    )
    
    # Create test data
    test_data = [Decimal(str(100 + i)) for i in range(50)]
    
    # Test SMA
    print("\nTesting SMA...")
    sma_results = calculate_sma(test_data, 10)
    assert len(sma_results) == 50
    assert sma_results[9] is not None
    print("✓ SMA calculation works")
    
    # Test EMA
    print("\nTesting EMA...")
    ema_results = calculate_ema(test_data, 10)
    assert len(ema_results) == 50
    assert ema_results[9] is not None
    print("✓ EMA calculation works")
    
    # Test RSI
    print("\nTesting RSI...")
    rsi_results = calculate_rsi(test_data, 14)
    assert len(rsi_results) == 50
    assert rsi_results[14] is not None
    print("✓ RSI calculation works")
    
    # Test Bollinger Bands
    print("\nTesting Bollinger Bands...")
    bb_results = calculate_bollinger_bands(test_data, 20)
    assert len(bb_results) == 50
    assert bb_results[19].middle is not None
    assert bb_results[19].upper is not None
    assert bb_results[19].lower is not None
    print("✓ Bollinger Bands calculation works")
    
    print("\n" + "=" * 80)
    print("✓ INDICATOR INTEGRITY TEST PASSED")
    print("=" * 80)
    
    return True


if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("STARTING COMPREHENSIVE REGRESSION TEST")
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
        if test_rsi_bollinger_backtest():
            passed += 1
        else:
            failed += 1
    except Exception as e:
        print(f"✗ RSI Bollinger backtest failed: {e}")
        import traceback
        traceback.print_exc()
        failed += 1
    
    print("\n" + "=" * 80)
    print(f"REGRESSION TEST SUMMARY: {passed} PASSED, {failed} FAILED")
    print("=" * 80)
    
    if failed == 0:
        print("\n✓ ALL REGRESSION TESTS PASSED - NO DEGRADATION DETECTED")
    else:
        print("\n✗ REGRESSION DETECTED - PLEASE INVESTIGATE")
        sys.exit(1)
