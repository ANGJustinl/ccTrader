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
    symbol = "FHEUSDT" # ETH often oscillates well
    
    # Use recent data (last 7 days)
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=1)
    
    initial_balance = Decimal("5000")
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
            timeframe="1m",
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
        grid_number=20,          # Aligned with live trading
        atr_multiplier=4.0,      # Aligned with live trading
        min_profit_per_grid=0.0005,
        position_size=0.01,      # Fallback only, dynamic calc overrides
        trend_filter_enabled=True,
        trend_ema_period=50,
        grid_spacing="geometric",
        leverage=10,             # Aligned with live trading
        capital_usage=0.8,       # Aligned with live trading
    )
    # Dynamic position sizing will override position_size based on balance/leverage
    
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
