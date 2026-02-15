"""
Test streaming vs batch indicator consistency.

Ensures that streaming indicators (incremental updates) produce
identical results to batch calculations on the full dataset.
"""
import pytest
from decimal import Decimal
from src.trader.utils.indicators import (
    calculate_bollinger_bands,
    calculate_macd,
    calculate_kdj,
    StreamingBollingerBands,
    StreamingMACD,
    StreamingKDJ,
)

# Acceptable tolerance for decimal precision (10 bps)
TOLERANCE = Decimal("0.01")


def generate_test_data(n: int = 150) -> tuple[list[Decimal], list[Decimal], list[Decimal], list[Decimal]]:
    """Generate synthetic price data for testing.
    
    Args:
        n: Number of data points
        
    Returns:
        Tuple of (prices, highs, lows, closes)
    """
    import random
    random.seed(42)
    
    prices = []
    highs = []
    lows = []
    closes = []
    
    price = Decimal("100.0")
    
    for _ in range(n):
        change = Decimal(str(random.uniform(-2, 2)))
        price = max(Decimal("50"), price + change)
        
        high = price + Decimal(str(random.uniform(0, 1)))
        low = price - Decimal(str(random.uniform(0, 1)))
        close = price + Decimal(str(random.uniform(-0.5, 0.5)))
        
        prices.append(close)
        highs.append(high)
        lows.append(low)
        closes.append(close)
    
    return prices, highs, lows, closes


class TestStreamingBollingerBands:
    """Test streaming Bollinger Bands vs batch calculation."""
    
    def test_consistency(self):
        """Streaming should match batch results."""
        prices, _, _, _ = generate_test_data(150)
        
        # Batch calculation
        batch_results = calculate_bollinger_bands(prices, period=20, std_dev=Decimal("2"))
        
        # Streaming calculation
        streaming = StreamingBollingerBands(period=20, std_dev=Decimal("2"), window_size=100)
        streaming_results = []
        
        for price in prices:
            streaming.update(price)
            current = streaming.get_current()
            streaming_results.append(current)
        
        # Compare results (skip initial None values)
        for i in range(len(batch_results)):
            batch = batch_results[i]
            stream = streaming_results[i]
            
            if batch.middle is not None:
                assert stream is not None
                # Compare with acceptable tolerance
                assert abs(batch.middle - stream.middle) < TOLERANCE
                assert abs(batch.upper - stream.upper) < TOLERANCE
                assert abs(batch.lower - stream.lower) < TOLERANCE


class TestStreamingMACD:
    """Test streaming MACD vs batch calculation."""
    
    def test_consistency(self):
        """Streaming should match batch results."""
        prices, _, _, _ = generate_test_data(150)
        
        # Batch calculation
        batch_results = calculate_macd(prices, fast_period=12, slow_period=26, signal_period=9)
        
        # Streaming calculation
        streaming = StreamingMACD(
            fast_period=12,
            slow_period=26,
            signal_period=9,
            window_size=100,
        )
        streaming_results = []
        
        for price in prices:
            streaming.update(price)
            current = streaming.get_current()
            streaming_results.append(current)
        
        # Compare results
        for i in range(len(batch_results)):
            batch = batch_results[i]
            stream = streaming_results[i]
            
            if batch.macd_line is not None:
                assert stream is not None
                assert abs(batch.macd_line - stream.macd_line) < TOLERANCE
                if batch.signal_line is not None:
                    assert stream.signal_line is not None
                    assert abs(batch.signal_line - stream.signal_line) < TOLERANCE
                    assert abs(batch.histogram - stream.histogram) < TOLERANCE


class TestStreamingKDJ:
    """Test streaming KDJ vs batch calculation."""
    
    def test_consistency(self):
        """Streaming should match batch results."""
        _, highs, lows, closes = generate_test_data(150)
        
        # Batch calculation
        batch_results = calculate_kdj(
            highs,
            lows,
            closes,
            rsv_period=9,
            k_period=3,
            d_period=3,
        )
        
        # Streaming calculation
        streaming = StreamingKDJ(
            rsv_period=9,
            k_period=3,
            d_period=3,
            window_size=100,
        )
        streaming_results = []
        
        for h, l, c in zip(highs, lows, closes):
            streaming.update(h, l, c)
            current = streaming.get_current()
            streaming_results.append(current)
        
        # Compare results
        for i in range(len(batch_results)):
            batch = batch_results[i]
            stream = streaming_results[i]
            
            if batch.k is not None:
                assert stream is not None
                assert abs(batch.k - stream.k) < TOLERANCE
                if batch.d is not None:
                    assert stream.d is not None
                    assert abs(batch.d - stream.d) < TOLERANCE
                    assert abs(batch.j - stream.j) < TOLERANCE


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
