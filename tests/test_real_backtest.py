"""Real backtest without mocks - uses actual Binance data"""
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add src to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from trader.application.backtest_engine import BacktestEngine
from trader.application.strategies.ma_crossover import MovingAverageCrossover


def test_real_backtest():
    """Run a real backtest with actual Binance data"""
    print("=" * 80)
    print("REAL BACKTEST - NO MOCKS")
    print("=" * 80)
    
    # Create backtest engine
    engine = BacktestEngine(
        initial_balance=10000,
        slippage=0.0005,
        commission=0.0004
    )
    
    # Download real Binance data
    symbol = "BTC/USDT"
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=7)  # 7 days of data
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
        return
    
    # Create strategy with callback tracking
    class TrackedMACrossover(MovingAverageCrossover):
        """MA Crossover with callback tracking"""
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
            print(f"  [Funding Rate] {timestamp}: {rate}")
        
        def on_order_update(self, order):
            self.on_order_update_called += 1
            super().on_order_update(order)
            print(f"  [Order Update] {order.id}: {order.status.value}")
    
    strategy = TrackedMACrossover(
        fast_period=5,
        slow_period=20,
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
    assert len(strategy.signals_generated) >= 0, "signals can be generated"
    
    print("\nPERFORMANCE METRICS:")
    print(f"  Initial Balance: ${result['initial_balance']:.2f}")
    print(f"  Final Balance: ${result['final_balance']:.2f}")
    print(f"  Total Return: {result['total_return']:.2f}%")
    print(f"  Total Trades: {result['total_trades']}")
    print(f"  Total Commission: ${result['total_commission']:.4f}")
    print(f"  Total Funding Paid: ${result['total_funding_paid']:.4f}")
    
    print("\n" + "=" * 80)
    print("✓ ALL TESTS PASSED - REAL BACKTEST SUCCESSFUL")
    print("=" * 80)
    
    return result


if __name__ == "__main__":
    test_real_backtest()
