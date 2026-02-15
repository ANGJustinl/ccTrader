"""
Quick performance verification test.

Uses a smaller dataset to verify performance within reasonable time.
"""
import sys
import time
from decimal import Decimal
from pathlib import Path
from datetime import datetime, timedelta, timezone

import pytest

# Add src to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from trader.application.backtest_engine import BacktestEngine
from trader.application.strategies.ma_crossover import MovingAverageCrossover
from trader.infrastructure.data_repository import BarData


def generate_test_bars(num_bars: int = 1000) -> list[BarData]:
    """Generate test bar data."""
    bars = []
    base_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
    base_price = Decimal("50000")
    
    import random
    for i in range(num_bars):
        price_change = Decimal(str(random.uniform(-100, 100)))
        open_price = base_price + price_change
        close_price = open_price + Decimal(str(random.uniform(-50, 50)))
        high_price = max(open_price, close_price) + Decimal("20")
        low_price = min(open_price, close_price) - Decimal("20")
        
        bars.append(BarData(
            symbol="BTC/USDT",
            timestamp=base_time + timedelta(minutes=i * 15),
            open=open_price,
            high=high_price,
            low=low_price,
            close=close_price,
            volume=Decimal("100"),
        ))
        
        base_price = close_price
    
    return bars


class TestQuickPerformance:
    """Quick performance verification tests."""

    def test_backtest_performance_scalable(self) -> None:
        """Test that backtest performance scales well."""
        # Test with 1000 bars (should complete in seconds)
        bars = generate_test_bars(1000)
        
        engine = BacktestEngine(
            initial_balance=Decimal("10000"),
            slippage=Decimal("0.0005"),
            commission=Decimal("0.0004"),
        )
        
        engine.load_data(bars)
        
        strategy = MovingAverageCrossover(
            fast_period=10,
            slow_period=20,
            position_size=Decimal("0.001"),
        )
        engine.set_strategy(strategy)
        
        start_time = time.time()
        results = engine.run("BTC/USDT")
        elapsed_time = time.time() - start_time
        
        print(f"Backtest with {len(bars)} bars completed in {elapsed_time:.2f}s")
        
        # Extrapolate to 1 year (35040 bars)
        # If 1000 bars take X seconds, 35040 should take ~35X seconds
        extrapolated_time_1year = elapsed_time * (35040 / 1000)
        print(f"Estimated 1-year backtest time: {extrapolated_time_1year:.2f}s")
        
        # Verify it's reasonable (we expect < 30s, but allow more for safety)
        assert extrapolated_time_1year < 60, \
            f"Estimated {extrapolated_time_1year:.2f}s may be too slow"
        
        assert results is not None
        assert "final_balance" in results
