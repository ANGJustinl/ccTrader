"""Classic crypto strategies backtestback using real Binance data.

Tests:
- RSIBollingerStrategy: Trend + reversal composite
- FundingArbitrageStrategy: Funding rate observer
"""
import sys
from pathlib import Path
from datetime import datetime, timedelta
from decimal import Decimal

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from trader.application.backtest_engine import BacktestEngine
from trader.application.strategies.crypto_classic import (
    RSIBollingerStrategy,
    FundingArbitrageStrategy,
)
from trader.infrastructure.data_downloader import DataDownloader


def run_rsi_bollinger_backtest():
    """Run RSI + Bollinger Bands strategy backtest."""
    print("=" * 70)
    print("RSI + Bollinger Bands 策略回测")
    print("=" * 70)
    
    # Create backtest engine
    engine = BacktestEngine(
        initial_balance=Decimal("10000"),
        slippage=Decimal("0.0005"),  # 0.05%
        commission=Decimal("0.0004")  # 0.04%
    )
    
    # Download real historical data - last 3 months, 15m timeframe
    print("\n[1/5] 准备数据...")
    downloader = DataDownloader(exchange_name="binance")
    symbol = "BTC/USDT:USDT"
    
    # Calculate timestamp 3 months ago (milliseconds)
    three_months_ago = datetime.now() - timedelta(days=90)
    since_timestamp = int(three_months_ago.timestamp() * 1000)
    
    # Download OHLCV data (15m candles)
    print("      正在下载 OHLCV 数据...")
    bars = downloader.download_ohlcv(
        symbol=symbol,
        timeframe="15m",
        since=since_timestamp,
        limit=1000
    )
    
    # Download funding rates
    print("      正在下载资金费率数据...")
    funding_rates = downloader.download_funding_rates(
        symbol=symbol,
        since=since_timestamp,
        limit=100
    )
    print(f"      使用真实 Binance 历史数据")
    
    engine.load_data(bars, funding_rates)
    print(f"      加载 {len(bars)} 根 K 线，{len(funding_rates)} 个资金费率数据")
    
    # Create RSI + Bollinger Bands strategy
    print("\n[2/5] 创建 RSI + Bollinger Bands 策略...")
    strategy = RSIBollingerStrategy(
        bollinger_period=20,
        bollinger_std=Decimal("2"),
        rsi_period=14,
        rsi_overbought=Decimal("70"),
        rsi_oversold=Decimal("30"),
        position_size=0.01,
        stop_loss_pct=Decimal("0.02"),  # 2%
        take_profit_pct=Decimal("0.04"),  # 4%
    )
    engine.set_strategy(strategy)
    print(f"      策略: {strategy.name}")
    print(f"      布林带周期: {strategy.bollinger_period}")
    print(f"      RSI 周期: {strategy.rsi_period}")
    print(f"      止损: {strategy.stop_loss_pct*100:.0f}%")
    print(f"      止盈: {strategy.take_profit_pct*100:.0f}%")
    
    # Run backtest
    print("\n[3/5] 运行回测...")
    results = engine.run(symbol)
    
    # Output results
    print("\n[4/5] 回测结果:")
    print("=" * 70)
    print(f"初始余额: ${results['initial_balance']:,.2f}")
    print(f"最终余额: ${results['final_balance']:,.2f}")
    print(f"总收益率: {results['total_return']:.2f}%")
    print(f"总交易数: {results['total_trades']}")
    print("=" * 70)
    
    # Output equity curve summary
    if results['equity_curve']:
        equity_values = [e['balance'] for e in results['equity_curve']]
        max_equity = max(equity_values)
        min_equity = min(equity_values)
        drawdown = (max_equity - min_equity) / max_equity * 100
        
        print(f"最高权益: ${max_equity:,.2f}")
        print(f"最低权益: ${min_equity:,.2f}")
        print(f"最大回撤: {drawdown:.2f}%")
    
    print("\nRSI + Bollinger Bands 策略回测完成！")
    return results


def run_funding_arbitrage_backtest():
    """Run Funding Arbitrage Observer backtest."""
    print("=" * 70)
    print("资金费率套利观察策略回测 (MVP 观察者)")
    print("=" * 70)
    
    # Create backtest engine
    engine = BacktestEngine(
        initial_balance=Decimal("10000"),
        slippage=Decimal("0.0005"),
        commission=Decimal("0.0004")
    )
    
    # Download data
    print("\n[1/5] 准备数据...")
    downloader = DataDownloader(exchange_name="binance")
    symbol = "BTC/USDT:USDT"
    
    three_months_ago = datetime.now() - timedelta(days=90)
    since_timestamp = int(three_months_ago.timestamp() * 1000)
    
    print("      正在下载 OHLCV 数据...")
    bars = downloader.download_ohlcv(
        symbol=symbol,
        timeframe="15m",
        since=since_timestamp,
        limit=1000
    )
    
    # Download funding rates
    print("      正在下载资金费率数据...")
    funding_rates = downloader.download_funding_rates(
        symbol=symbol,
        since=since_timestamp,
        limit=200  # Get more funding rate data
    )
    
    engine.load_data(bars, funding_rates)
    print(f"      加载 {len(bars)} 根 K 线，{len(funding_rates)} 个资金费率数据")
    
    # Create Funding Arbitrage Observer strategy
    print("\n[2/5] 创建资金费率套利观察策略...")
    strategy = FundingArbitrageStrategy(
        min_funding_spread=Decimal("0.0001")  # 0.01% threshold
    )
    engine.set_strategy(strategy)
    print(f"      策略: {strategy.name}")
    print(f"      最小费率阈值: {strategy.min_funding_spread*100:.2f}%")
    
    # Run backtest
    print("\n[3/5] 运行回测...")
    results = engine.run(symbol)
    
    # Output results
    print("\n[4/5] 回测结果:")
    print("=" * 70)
    print(f"初始余额: ${results['initial_balance']:,.2f}")
    print(f"最终余额: ${results['final_balance']:,.2f}")
    print(f"总收益率: {results['total_return']:.2f}%")
    print(f"总交易数: {results['total_trades']}")
    print("=" * 70)
    
    # Output funding rate opportunities
    if strategy.opportunities:
        print("\n[5/5] 资金费率机会分析:")
        print("=" * 70)
        print(f"检测到 {len(strategy.opportunities)} 个资金费率机会")
        
        significant = [o for o in strategy.opportunities if o['is_significant']]
        print(f"其中 {len(significant)} 个显著机会（绝对值 >= {strategy.min_funding_spread*100:.2f}%）")
        
        if significant:
            print("\n最后 5 个显著机会:")
            for opp in significant[-5:]:
                print(f"  时间: {opp['timestamp']}")
                print(f"  费率: {opp['current_rate']*100:.4f}%")
                print(f"  变化: {opp['change_bps']:.2f} bps")
                print(f"  方向: {'多头' if opp['is_positive'] else '空头'}")
                print(f"  估算日收益: {opp['estimated_daily_yield']:.4f}%")
                print("  ---")
    
    print("\n资金费率套利观察策略回测完成！")
    print("\n说明：")
    print("- 此策略为 MVP 观察者模式，只计算潜在收益，不执行交易")
    print("- 真实套利需要：Long Spot + Short Perpetual 对冲")
    return results


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Classic Crypto Strategies Backtest")
    parser.add_argument(
        "--strategy",
        type=str,
        choices=["rsi-bollinger", "funding-arb"],
        default="rsi-bollinger",
        help="Strategy to backtest"
    )
    
    args = parser.parse_args()
    
    if args.strategy == "rsi-bollinger":
        run_rsi_bollinger_backtest()
    elif args.strategy == "funding-arb":
        run_funding_arbitrage_backtest()


if __name__ == "__main__":
    main()
