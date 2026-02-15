"""Test script for new indicators (ADX and Z-Score)."""
from decimal import Decimal
from src.trader.utils.indicators import calculate_adx, calculate_zscore


def test_adx():
    """Test ADX calculation with sample data."""
    print("Testing ADX calculation...")
    
    # Create sample data (200 points for testing)
    import random
    random.seed(42)
    
    n = 100
    highs = [Decimal(str(100 + random.uniform(-5, 5) + i * 0.1)) for i in range(n)]
    lows = [Decimal(str(95 + random.uniform(-5, 5) + i * 0.1)) for i in range(n)]
    closes = [Decimal(str(97 + random.uniform(-5, 5) + i * 0.1)) for i in range(n)]
    
    results = calculate_adx(highs, lows, closes, period=14)
    
    print(f"Total data points: {n}")
    print(f"Results with ADX: {sum(1 for r in results if r.adx is not None)}")
    print(f"Results with +DI: {sum(1 for r in results if r.plus_di is not None)}")
    
    # Print last 5 results
    print("\nLast 5 results:")
    for i in range(max(0, n - 5), n):
        print(f"  [{i}] ADX={results[i].adx}, +DI={results[i].plus_di}, -DI={results[i].minus_di}")
    
    print("ADX test completed!\n")


def test_zscore():
    """Test Z-Score calculation with sample data."""
    print("Testing Z-Score calculation...")
    
    # Create sample data
    import random
    random.seed(42)
    
    n = 100
    data = [Decimal(str(100 + random.uniform(-10, 10))) for i in range(n)]
    
    results = calculate_zscore(data, period=20)
    
    print(f"Total data points: {n}")
    print(f"Results with Z-Score: {sum(1 for r in results if r is not None)}")
    
    # Print last 10 results
    print("\nLast 10 results:")
    for i in range(max(0, n - 10), n):
        print(f"  [{i}] Z-Score={results[i]}")
    
    print("Z-Score test completed!\n")


if __name__ == "__main__":
    test_adx()
    test_zscore()
    print("All tests passed!")
