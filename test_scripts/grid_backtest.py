import sys
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json

# Ensure project root is in python path
sys.path.append(os.getcwd())

from trader.application.backtest_engine import BacktestEngine
from trader.application.strategies.grid import DynamicGridStrategy

def run_grid_backtest():
    """Run backtest for Dynamic Grid Strategy"""
    
    # 1. Configure Backtest
    symbol = "SIRENUSDT" # ETH often oscillates well
    
    # Use recent data (last 7 days)
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=7)
    
    initial_balance = Decimal("10000")
    commission_rate = Decimal("0.0004")  # 0.04%
    slippage = Decimal("0.0001")        # 0.01%
    
    print(f"Starting Grid Backtest for {symbol}")
    print(f"Period: {start_date} to {end_date}")
    
    # 2. Initialize Engine
    engine = BacktestEngine(
        initial_balance=initial_balance,
        commission=commission_rate,
        slippage=slippage,
        use_volatility_slippage=True
    )
    
    # 3. Download/Load Data
    print("Downloading data...")
    try:
        engine.download_data(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            timeframe="15m",
            exchange="binance"
        )
        print(f"Downloaded {len(engine.all_bars)} bars.")
        if engine.all_bars:
            print(f"First: {engine.all_bars[0].timestamp}")
            print(f"Last: {engine.all_bars[-1].timestamp}")
    except Exception as e:
        print(f"Error downloading data: {e}")
        # Try without proxy/env adjustments if straightforward fail, 
        # or hint user to check env. 
        # For now assume it works or fails with clean message.
        return

    # 4. Initialize Strategy
    strategy = DynamicGridStrategy(
        symbol=symbol,
        grid_number=30,
        atr_multiplier=2.0,
        min_profit_per_grid=0.0005, # 0.4%
        position_size=0.1, # Will be updated below
        trend_filter_enabled=True,
        trend_ema_period=50,
        grid_spacing="geometric"
    )
    # Update position size to be reasonable for 10000 USDT
    strategy.position_size = Decimal("0.5") # 0.5 ETH per grid (~$1500)
    
    # 5. Run Backtest
    print("Running backtest...")
    engine.set_strategy(strategy)
    result = engine.run(symbol=symbol)
    
    # 6. Report
    report = result['report']
    
    print("\n" + "="*50)
    print("BACKTEST RESULTS")
    print("="*50)
    print(f"Total Return: {result['total_return']:.2f}%")
    print(f"Total Trades: {result['total_trades']}")
    # Access report attributes safely
    win_rate = getattr(report, 'win_rate', 0)
    profit_factor = getattr(report, 'profit_factor', 0)
    max_drawdown = getattr(report, 'max_drawdown', 0)
    
    print(f"Win Rate: {win_rate:.2f}%")
    print(f"Profit Factor: {profit_factor}")
    print(f"Max Drawdown: {max_drawdown:.2f}%")
    
    # Save detailed report
    output_file = "grid_performance_report.json"
    with open(output_file, "w", encoding='utf-8') as f:
        # Use formatted_report or dump manually
        json.dump(result['formatted_report'], f, indent=2, default=str)
    print(f"\nDetailed report saved to {output_file}")

if __name__ == "__main__":
    run_grid_backtest()
