"""Tests for trading strategies"""
from datetime import datetime
from decimal import Decimal

import pytest

from trader.application.strategy import BaseStrategy
from trader.application.strategies import MovingAverageCrossover
from trader.application.backtest_engine import BacktestEngine
from trader.infrastructure.data_repository import BarData, FundingRateData


class TestBaseStrategy:
    """Tests for BaseStrategy"""
    
    def test_abstract_on_bar(self):
        """Test on_bar is abstract"""
        with pytest.raises(TypeError):
            BaseStrategy()


class TestMovingAverageCrossover:
    """Tests for MovingAverageCrossover strategy"""
    
    @pytest.fixture
    def strategy(self):
        """Create a strategy instance"""
        return MovingAverageCrossover(
            fast_period=5,
            slow_period=10,
            position_size=0.01
        )
    
    @pytest.fixture
    def sample_bars(self):
        """Generate sample bars for testing"""
        bars = []
        base_time = datetime(2024, 1, 1)
        for i in range(50):
            bar = BarData(
                symbol="BTC/USDT",
                timestamp=base_time.replace(hour=i // 4, minute=(i % 4) * 15),
                open=Decimal("50000") + Decimal(str(i * 10)),
                high=Decimal("50100") + Decimal(str(i * 10)),
                low=Decimal("49900") + Decimal(str(i * 10)),
                close=Decimal("50050") + Decimal(str(i * 10)),
                volume=Decimal("100")
            )
            bars.append(bar)
        return bars
    
    def test_strategy_initialization(self, strategy):
        """Test strategy initialization"""
        assert strategy.name == "MA Crossover"
        assert strategy.fast_period == 5
        assert strategy.slow_period == 10
        assert strategy.position_size == 0.01
        assert len(strategy.bar_history) == 0
    
    def test_calculate_sma(self, strategy, sample_bars):
        """Test SMA calculation"""
        # Add bars to history
        for bar in sample_bars[:10]:
            strategy.bar_history.append(bar)
        
        # Calculate SMA for period 5
        sma_5 = strategy._calculate_sma(5)
        expected = sum(bar.close for bar in strategy.bar_history[-5:]) / Decimal("5")
        assert sma_5 == expected
        
        # Calculate SMA for period 10
        sma_10 = strategy._calculate_sma(10)
        expected = sum(bar.close for bar in strategy.bar_history[-10:]) / Decimal("10")
        assert sma_10 == expected
    
    def test_on_bar_insufficient_data(self, strategy):
        """Test on_bar with insufficient data"""
        bar = BarData(
            symbol="BTC/USDT",
            timestamp=datetime(2024, 1, 1),
            open=Decimal("50000"),
            high=Decimal("50100"),
            low=Decimal("49900"),
            close=Decimal("50050"),
            volume=Decimal("100")
        )
        
        # Mock broker
        class MockBrokerBroker:
            def submit_order(self, order):
                pass
            def get_position(self, symbol):
                return None
        
        strategy.broker = MockBrokerBroker()
        
        # Process bar with insufficient data
        for _ in range(strategy.slow_period - 1):
            strategy.on_bar(bar)
        
        # Should not submit any orders
        assert len(strategy.bar_history) == strategy.slow_period - 1


class TestBacktestIntegration:
    """Integration tests for backtesting with strategies"""
    
    @pytest.fixture
    def sample_data(self):
        """Generate sample data for backtesting"""
        bars = []
        funding_rates = []
        base_time = datetime(2024, 1, 1)
        
        for i in range(50):
            # Create uptrend then downtrend
            if i < 25:
                price_trend = i * 20
            else:
                price_trend = 25 * 20 - (i - 25) * 10
            
            bar = BarData(
                symbol="BTC/USDT",
                timestamp=base_time.replace(hour=i // 4, minute=(i % 4) * 15),
                open=Decimal("50000") + Decimal(str(price_trend)),
                high=Decimal("50100") + Decimal(str(price_trend)),
                low=Decimal("49900") + Decimal(str(price_trend)),
                close=Decimal("50050") + Decimal(str(price_trend)),
                volume=Decimal("100")
            )
            bars.append(bar)
        
        # Add funding rate
        funding_rates.append(FundingRateData(
            symbol="BTC/USDT",
            rate=Decimal("0.0001"),
            timestamp=base_time,
            next_funding_time=datetime(2024, 1, 1, 8)
        ))
        
        return bars, funding_rates
    
    def test_backtest_with_ma_crossover(self, sample_data):
        """Test backtest with MA crossover strategy"""
        bars, funding_rates = sample_data
        
        engine = BacktestEngine(
            initial_balance=Decimal("10000"),
            slippage=Decimal("0.0005"),
            commission=Decimal("0.0004")
        )
        
        engine.load_data(bars, funding_rates)
        
        strategy = MovingAverageCrossover(
            fast_period=5,
            slow_period=10,
            position_size=0.01
        )
        engine.set_strategy(strategy.on_bar)
        
        results = engine.run("BTC/USDT")
        
        # Check results structure
        assert "initial_balance" in results
        assert "final_balance" in results
        assert "total_return" in results
        assert "total_trades" in results
        assert "equity_curve" in results
        
        # Check initial balance
        assert results["initial_balance"] == Decimal("10000")
        
        # Check equity curve
        assert len(results["equity_curve"]) > 0
        assert results["equity_curve"][0]["balance"] == Decimal("10000")
        
        # Should have processed all bars
        assert len(results["equity_curve"]) == len(bars)
    
    def test_backtest_with_no_signals(self, sample_data):
        """Test backtest with no trading signals"""
        bars, funding_rates = sample_data
        
        engine = BacktestEngine(
            initial_balance=Decimal("10000"),
            slippage=Decimal("0.0005"),
            commission=Decimal("0.0004")
        )
        
        engine.load_data(bars, funding_rates)
        
        # No-op strategy
        def no_op_strategy(bar):
            pass
        
        engine.set_strategy(no_op_strategy)
        
        results = engine.run("BTC/USDT")
        
        # Should have no trades
        assert results["total_trades"] == 0
        
        # Balance should remain unchanged (minus fees if any)
        assert results["final_balance"] == results["initial_balance"]


class TestBacktestScript:
    """Tests for backtest script functionality"""
    
    def test_generate_sample_data(self):
        """Test sample data generation function"""
        from trader.scripts.run_backtest import generate_sample_data
        
        bars, funding_rates = generate_sample_data()
        
        # Check we got data
        assert len(bars) == 200
        assert len(funding_rates) > 0
        
        # Check first bar
        assert bars[0].symbol == "BTC/USDT"
        assert bars[0].open > 0
        assert bars[0].high > 0
        assert bars[0].low > 0
        assert bars[0].close > 0
        assert bars[0].volume > 0
        
        # Check funding rates
        assert funding_rates[0].symbol == "BTC/USDT"
        assert funding_rates[0].rate == Decimal("0.0001")
