"""Test script for DRAMM Strategy initialization."""
from decimal import Decimal
from src.trader.application.strategies.dramm import DRAMMStrategy, MarketRegime


def test_dramm_init():
    """Test DRAMM Strategy initialization."""
    print("Testing DRAMM Strategy initialization...")
    
    strategy = DRAMMStrategy(
        adx_period=14,
        bollinger_period=20,
        rsi_period=14,
        atr_period=14,
        zscore_period=20,
        position_size=0.01,
        atr_multiplier=Decimal("3"),
        entry_score_threshold=Decimal("0.6"),
        exit_score_threshold=Decimal("-0.4"),
    )
    
    print(f"Strategy name: {strategy.name}")
    print(f"Current regime: {strategy.current_regime}")
    print(f"Min history required: {strategy.min_history}")
    print(f"Regime weights keys: {list(strategy.REGIME_WEIGHTS.keys())}")
    
    # Test RegimeWeights
    trend_weights = strategy.REGIME_WEIGHTS[MarketRegime.TREND]
    print(f"\nTrend regime weights:")
    print(f"  Trend factor: {trend_weights.trend_factor}")
    print(f"  Momentum factor: {trend_weights.momentum_factor}")
    print(f"  Volatility factor: {trend_weights.volatility_factor}")
    print(f"  Microstructure factor: {trend_weights.microstructure_factor}")
    
    print("\nDRAMM Strategy initialization test passed!")


if __name__ == "__main__":
    test_dramm_init()
