"""
Performance and stress tests for the trading system.

These tests measure:
- Backtest performance benchmarks
- Memory usage analysis
- High-frequency signal scenario stress testing
"""
import gc
import sys
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
import tracemalloc

import pytest

# Add src to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from trader.application.backtest_engine import BacktestEngine
from trader.application.order import Order
from trader.application.strategies.ma_crossover import MovingAverageCrossover
from trader.infrastructure.data_repository import BarData, FundingRateData


class TestPerformanceBenchmarks:
    """Performance benchmark tests."""

    @pytest.fixture
    def large_dataset(self) -> list[BarData]:
        """Generate a large dataset (~1 year of 15-minute bars)."""
        bars = []
        base_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
        base_price = Decimal("50000")
        
        # ~1 year of 15-minute data: 365 * 24 * 4 = 35040 bars
        num_bars = 35040
        
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
                volume=Decimal(str(random.uniform(10, 100))),
            ))
            
            base_price = close_price
        
        return bars

    def test_backtest_performance_1year_data(self, large_dataset: list[BarData]) -> None:
        """Test that backtest completes in < 30 seconds with 1 year of data."""
        engine = BacktestEngine(
            initial_balance=Decimal("10000"),
            slippage=Decimal("0.0005"),
            commission=Decimal("0.0004"),
        )
        
        engine.load_data(large_dataset)
        
        strategy = MovingAverageCrossover(
            fast_period=10,
            slow_period=20,
            position_size=Decimal("0.001"),
        )
        engine.set_strategy(strategy)
        
        # Time the backtest
        start_time = time.time()
        results = engine.run("BTC/USDT")
        end_time = time.time()
        
        elapsed_time = end_time - start_time
        
        print(f"Backtest completed in {elapsed_time:.2f} seconds")
        print(f"Processed {len(large_dataset)} bars")
        print(f"Final balance: ${results['final_balance']:.2f}")
        
        # Assert performance target
        assert elapsed_time < 30, f"Backtest took {elapsed_time:.2f}s, target is <30s"
        assert results is not None

    def test_multiple_backtest_performance(self) -> None:
        """Test performance of multiple consecutive backtests."""
        # Generate medium dataset
        bars = []
        base_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
        base_price = Decimal("50000")
        
        import random
        for i in range(1000):
            price = base_price + Decimal(str(random.uniform(-50, 50)))
            bars.append(BarData(
                symbol="BTC/USDT",
                timestamp=base_time + timedelta(minutes=i * 15),
                open=price,
                high=price + Decimal("10"),
                low=price - Decimal("10"),
                close=price,
                volume=Decimal("100"),
            ))
        
        # Run 5 backtests
        times = []
        for i in range(5):
            engine = BacktestEngine(
                initial_balance=Decimal("10000"),
                slippage=Decimal("0.0005"),
                commission=Decimal("0.0004"),
            )
            engine.load_data(bars)
            strategy = MovingAverageCrossover(position_size=Decimal("0.001"))
            engine.set_strategy(strategy)
            
            start = time.time()
            engine.run("BTC/USDT")
            end = time.time()
            times.append(end - start)
        
        avg_time = sum(times) / len(times)
        print(f"Average backtest time: {avg_time:.2f}s")
        print(f"Individual times: {[f'{t:.2f}s' for t in times]}")
        
        assert avg_time < 5, f"Average time {avg_time:.2f}s exceeds 5s target"


class TestMemoryUsage:
    """Memory usage analysis tests."""

    def test_memory_usage_backtest(self) -> None:
        """Test memory usage stays under 2GB during backtest."""
        # Generate large dataset
        bars = []
        base_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
        base_price = Decimal("50000")
        
        import random
        for i in range(35040):  # 1 year of 15min data
            price = base_price + Decimal(str(random.uniform(-50, 50)))
            bars.append(BarData(
                symbol="BTC/USDT",
                timestamp=base_time + timedelta(minutes=i * 15),
                open=price,
                high=price + Decimal("10"),
                low=price - Decimal("10"),
                close=price,
                volume=Decimal("100"),
            ))
            base_price = price
        
        # Force garbage collection before test
        gc.collect()
        
        # Start memory tracking
        tracemalloc.start()
        
        try:
            engine = BacktestEngine(
                initial_balance=Decimal("10000"),
                slippage=Decimal("0.0005"),
                commission=Decimal("0.0004"),
            )
            engine.load_data(bars)
            strategy = MovingAverageCrossover(position_size=Decimal("0.001"))
            engine.set_strategy(strategy)
            
            results = engine.run("BTC/USDT")
            
            # Get memory snapshot
            snapshot = tracemalloc.take_snapshot()
            top_stats = snapshot.statistics('lineno')
            
            total_memory = sum(stat.size for stat in top_stats)
            total_memory_mb = total_memory / (1024 * 1024)
            total_memory_gb = total_memory_mb / 1024
            
            print(f"Total memory usage: {total_memory_mb:.2f} MB ({total_memory_gb:.3f} GB)")
            
            # Check peak memory
            peak_memory = tracemalloc.get_traced_memory()[1]
            peak_memory_mb = peak_memory / (1024 * 1024)
            peak_memory_gb = peak_memory_mb / 1024
            print(f"Peak memory usage: {peak_memory_mb:.2f} MB ({peak_memory_gb:.3f} GB)")
            
            # Assert memory target
            assert peak_memory_gb < 2, f"Peak memory {peak_memory_gb:.3f}GB exceeds 2GB limit"
            
        finally:
            tracemalloc.stop()


class TestHighFrequencyStress:
    """Stress tests for high-frequency signal scenarios."""

    def test_high_frequency_signals(self) -> None:
        """Test system under high-frequency signal generation."""
        # Generate data with high volatility
        bars = []
        base_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
        base_price = Decimal("50000")
        
        import random
        for i in range(10000):  # Large number of bars
            # High volatility, frequent price swings
            price_change = Decimal(str(random.uniform(-200, 200)))
            open_price = base_price + price_change
            close_price = open_price + Decimal(str(random.uniform(-100, 100)))
            
            bars.append(BarData(
                symbol="BTC/USDT",
                timestamp=base_time + timedelta(minutes=i),
                open=open_price,
                high=max(open_price, close_price) + Decimal("50"),
                low=min(open_price, close_price) - Decimal("50"),
                close=close_price,
                volume=Decimal(str(random.uniform(100, 1000))),
            ))
            base_price = close_price
        
        # Strategy that generates signals on every bar
        class HighFrequencyStrategy:
            def __init__(self):
                self.signal_count = 0
                self.broker = None
            
            def attach_backtest_engine(self, engine):
                self.broker = engine.broker
            
            def on_bar(self, bar: BarData) -> None:
                self.signal_count += 1
                # Generate order on every other bar
                if self.signal_count % 2 == 0 and self.broker:
                    position = self.broker.get_position("BTC/USDT")
                    if not position:
                        # Open position
                        order = Order(
                            symbol="BTC/USDT",
                            side="buy",
                            order_type="market",
                            quantity=Decimal("0.001"),
                            timestamp=bar.timestamp,
                        )
                        self.broker.submit_order(order)
                    else:
                        # Close position
                        order = Order(
                            symbol="BTC/USDT",
                            side="sell",
                            order_type="market",
                            quantity=position.quantity,
                            timestamp=bar.timestamp,
                        )
                        self.broker.submit_order(order)
        
        engine = BacktestEngine(
            initial_balance=Decimal("100000"),  # Larger balance for frequent trading
            slippage=Decimal("0.0001"),
            commission=Decimal("0.0001"),
        )
        engine.load_data(bars)
        
        strategy = HighFrequencyStrategy()
        engine.set_strategy(strategy)
        strategy.attach_backtest_engine(engine)
        
        start_time = time.time()
        results = engine.run("BTC/USDT")
        end_time = time.time()
        
        elapsed_time = end_time - start_time
        
        print(f"High-frequency stress test completed in {elapsed_time:.2f}s")
        print(f"Signals generated: {strategy.signal_count}")
        print(f"Total trades: {results['total_trades']}")
        print(f"Final balance: ${results['final_balance']:.2f}")
        
        # Verify system handled high frequency without errors
        assert results is not None
        assert results["total_trades"] >= 0
