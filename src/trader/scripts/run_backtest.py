"""MVP backtest runner script"""
import sys
from pathlib import Path
from datetime import datetime, timedelta
from decimal import Decimal

# Add project root directory to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from trader.application.backtest_engine import BacktestEngine
from trader.application.strategies import MovingAverageCrossover
from trader.infrastructure.data_repository import BarData, FundingRateData


def generate_sample_data() -> tuple[list[BarData], list[FundingRateData]]:
    """生成示例数据用于测试 - 震荡上升行情"""
    bars = []
    funding_rates = []
    
    start_time = datetime(2024, 1, 1, tzinfo=datetime.now().astimezone().tzinfo)
    
    base_price = Decimal("50000")
    current_price = base_price
    
    # 生成 200 根 K 线
    for i in range(200):
        # 第一阶段：从高位快速下跌 (0-60) - 确保MA计算开始时已经在下跌中
        if i < 60:
            trend = Decimal("30000") - Decimal(str((i + 1) * 500))
            volatility = Decimal(str((i % 3) * 50))
        # 第二阶段：底部震荡 (60-90) - 巩固底部
        elif i < 90:
            trend = -Decimal("5000") + Decimal(str((i - 60) * 50))
            volatility = Decimal(str((i % 8 - 4) * 200))
        # 第三阶段：快速上涨 (90-160) - 制造金叉
        elif i < 160:
            trend = Decimal(str((i - 90) * 600)) - Decimal("3000")
            volatility = Decimal(str((i % 5) * 50))
        # 第四阶段：高位震荡 (160-180) - 巩固高位
        elif i < 180:
            trend = Decimal("42000") + Decimal(str((i - 160) * 100))
            volatility = Decimal(str((i % 6 - 3) * 200))
        # 第五阶段：回调 (180-200) - 制造平仓信号
        else:
            trend = Decimal("42000") - Decimal(str((i - 180) * 400))
            volatility = Decimal(str((i) * 50))
        
        noise = Decimal(str((hash(i) % 100 - 50)))
        
        close_price = base_price + trend + volatility + noise
        open_price = close_price + Decimal(str((i % 3 - 1) * 80))
        high_price = max(open_price, close_price) + Decimal("120")
        low_price = min(open_price, close_price) - Decimal("120")
        
        bar = BarData(
            symbol="BTC/USDT",
            timestamp=start_time + timedelta(minutes=15 * i),
            open=open_price,
            high=high_price,
            low=low_price,
            close=close_price,
            volume=Decimal("100")
        )
        bars.append(bar)
        
        # 每 8 小时生成一个资金费率
        if i % 32 == 0:
            funding_rate = FundingRateData(
                symbol="BTC/USDT",
                rate=Decimal(str(0.0001 + (i % 3) * 0.00005)),
                timestamp=start_time + timedelta(minutes=15 * i),
                next_funding_time=start_time + timedelta(hours=8, minutes=15 * i)
            )
            funding_rates.append(funding_rate)
    
    return bars, funding_rates


def main():
    print("=" * 60)
    print("MVP Backtest Run - Moving Average Crossover Strategy")
    print("=" * 60)
    
    # Create backtest engine
    engine = BacktestEngine(
        initial_balance=Decimal("10000"),
        slippage=Decimal("0.0005"),  # 0.05%
        commission=Decimal("0.0004")  # 0.04%
    )
    
    # Load sample data
    print("\n[1/4] Generating sample data...")
    bars, funding_rates = generate_sample_data()
    engine.load_data(bars, funding_rates)
    print(f"      Loaded {len(bars)} bars, {len(funding_rates)} funding rates")
    
    # Create strategy
    print("\n[2/4] Creating strategy...")
    strategy = MovingAverageCrossover(
        fast_period=10,
        slow_period=20,
        position_size=0.01
    )
    engine.set_strategy(strategy)
    print(f"      Strategy: {strategy.name}")
    print(f"      Parameters: fast_period={strategy.fast_period}, slow_period={strategy.slow_period}")
    
    # Run backtest
    print("\n[3/4] Running backtest...")
    results = engine.run("BTC/USDT")
    
    # Output results
    print("\n[4/4] Backtest Results:")
    print("=" * 60)
    print(f"Initial Balance: ${results['initial_balance']:,.2f}")
    print(f"Final Balance: ${results['final_balance']:,.2f}")
    print(f"Total Return: {results['total_return']:.2f}%")
    print(f"Total Trades: {results['total_trades']}")
    print("=" * 60)
    
    # Output equity curve summary
    if results['equity_curve']:
        equity_values = [e['balance'] for e in results['equity_curve']]
        max_equity = max(equity_values)
        min_equity = min(equity_values)
        drawdown = (max_equity - min_equity) / max_equity * 100
        
        print(f"Max Equity: ${max_equity:,.2f}")
        print(f"Min Equity: ${min_equity:,.2f}")
        print(f"Max Drawdown: {drawdown:.2f}%")
    
    print("\nBacktest completed!")
    return results


if __name__ == "__main__":
    main()
