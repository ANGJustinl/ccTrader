"""AI 增强策略回测运行脚本 - 使用真实 Binance 历史数据"""
import sys
from pathlib import Path
from datetime import datetime, timedelta
from decimal import Decimal

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from trader.application.backtest_engine import BacktestEngine
from trader.application.strategies import AIEnhancedStrategy
from trader.infrastructure.data_repository import BarData, FundingRateData
from trader.infrastructure.data_downloader import DataDownloader


def main():
    print("=" * 70)
    print("AI 增强策略回测 - AI 智能体动态调整参数")
    print("=" * 70)
    
    # 创建回测引擎
    engine = BacktestEngine(
        initial_balance=Decimal("10000"),
        slippage=Decimal("0.0005"),  # 0.05%
        commission=Decimal("0.0004")  # 0.04%
    )
    
    # 下载真实历史数据 - 最近3个月，15分钟K线
    print("\n[1/5] 准备数据...")
    downloader = DataDownloader(exchange_name="binance")
    symbol = "BTC/USDT:USDT"
    
    # 计算3个月前的时间戳（毫秒）
    three_months_ago = datetime.now() - timedelta(days=90)
    since_timestamp = int(three_months_ago.timestamp() * 1000)
    
    # 下载 OHLCV 数据（15分钟K线）
    print("      正在下载 OHLCV 数据...")
    bars = downloader.download_ohlcv(
        symbol=symbol,
        timeframe="15m",
        since=since_timestamp,
        limit=1000
    )
    
    # 下载资金费率数据
    print("      正在下载资金费率数据...")
    funding_rates = downloader.download_funding_rates(
        symbol=symbol,
        since=since_timestamp,
        limit=100
    )
    print(f"      使用真实 Binance 历史数据")
    
    engine.load_data(bars, funding_rates)
    print(f"      加载 {len(bars)} 根 K 线，{len(funding_rates)} 个资金费率数据")
    
    # 创建 AI 增强策略
    print("\n[2/5] 创建 AI 增强策略...")
    strategy = AIEnhancedStrategy(
        fast_period=10,
        slow_period=20,
        base_position_size=0.01
    )
    strategy.attach_backtest_engine(engine)
    engine.set_strategy(strategy)  # 修复：传递策略实例而不是 strategy.on_bar
    print(f"      策略: {strategy.name}")
    print(f"      基础参数: 快速均线={strategy.fast_period}, 慢速均线={strategy.slow_period}")
    print(f"      AI 分析间隔: 每 {strategy.analysis_interval} 根 K 线")
    
    # 运行回测
    print("\n[3/5] 运行回测...")
    results = engine.run(symbol)
    
    # 输出结果
    print("\n[4/5] 回测结果:")
    print("=" * 70)
    print(f"初始余额: ${results['initial_balance']:,.2f}")
    print(f"最终余额: ${results['final_balance']:,.2f}")
    print(f"总收益率: {results['total_return']:.2f}%")
    print(f"总交易数: {results['total_trades']}")
    print("=" * 70)
    
    # 输出权益曲线摘要
    if results['equity_curve']:
        equity_values = [e['balance'] for e in results['equity_curve']]
        max_equity = max(equity_values)
        min_equity = min(equity_values)
        drawdown = (max_equity - min_equity) / max_equity * 100
        
        print(f"最高权益: ${max_equity:,.2f}")
        print(f"最低权益: ${min_equity:,.2f}")
        print(f"最大回撤: {drawdown:.2f}%")
    
    # 输出 AI 参数变化记录
    print("\n[5/5] AI 智能体参数调整:")
    print("=" * 70)
    print(f"最终风险等级: {strategy.current_params.risk_level.value}")
    print(f"最终仓位限制: {strategy.current_params.max_position_size}")
    print(f"最终止损设置: {strategy.current_params.stop_loss_pct}")
    print("=" * 70)
    
    print("\nAI 增强策略回测完成！")
    print("\n说明：")
    print("- AI 智能体不直接下单，只调整策略参数")
    print("- 在第 100 根 K 线后自动切换到激进模式")
    print("- 在第 200 根 K 线后自动切换到保守模式")
    return results


if __name__ == "__main__":
    main()
