import sys
import os
from decimal import Decimal
from datetime import datetime

# Ensure project root is in python path
sys.path.append(os.getcwd())

from trader.application.strategies.grid import DynamicGridStrategy
from trader.infrastructure.data_repository import BarData
from trader.domain.position import Position
from trader.domain.value_objects import Side

class MockClock:
    def now(self): return datetime.now()

class MockBroker:
    def get_open_orders(self, symbol): return []
    def get_position(self, symbol): return None
    def submit_order(self, order): 
        print(f"MOCK SUBMIT ORDER: {order.side} {order.quantity} @ {order.price}")
    def cancel_all_orders(self, symbol): 
        print(f"MOCK CANCEL ALL: {symbol}")

def test_strategy():
    print("Initializing Strategy...")
    strategy = DynamicGridStrategy(
        symbol="BTCUSDT",
        grid_number=5,
        atr_multiplier=2.0,
        min_profit_per_grid=0.003
    )
    strategy.broker = MockBroker()
    strategy.clock = MockClock()
    
    # Create dummy bars
    print("Generating Dummy Data (Oscillating)...")
    base_price = Decimal("50000")
    bars = []
    
    # Generate 50 bars
    # Need at least 25 for indicators
    for i in range(60):
        # Oscillate between 49000 and 51000
        import math
        osc = Decimal(str(math.sin(i * 0.5) * 1000))
        price = base_price + osc
        
        # High/Low for ATR
        high = price + Decimal("100")
        low = price - Decimal("100")
        
        bars.append(BarData(
            symbol="BTCUSDT",
            timestamp=datetime.now(),
            open=price,
            high=high,
            low=low,
            close=price,
            volume=Decimal("100")
        ))
        
    print("Feeding bars to strategy...")
    for i, bar in enumerate(bars):
        # Check if indicators are ready
        ready_len = strategy.min_history
        if i == ready_len:
            print(f"--- History should be sufficient now ({len(strategy.bar_history)}) ---")
            
        strategy.on_bar(bar)
        
        if strategy.grid_lines:
            print(f"Bar {i}: Grid Active! Grid Lines: {len(strategy.grid_lines)}")
            break

if __name__ == "__main__":
    test_strategy()
