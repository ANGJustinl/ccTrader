"""DRAMM Strategy Backtest Performance Analysis Script.

This script performs comprehensive backtesting of the DRAMM strategy using real Binance data,
calculates all key performance metrics, and generates detailed reports.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from trader.application.backtest_engine import BacktestEngine
from trader.application.backtest_report import BacktestReportGenerator
from trader.application.strategies.dramm import DRAMMStrategy


def calculate_metrics_summary(report) -> dict:
    """Calculate summary metrics from backtest report."""
    return {
        "total_return": float(report.total_return),
        "annualized_return": float(report.annualized_return),
        "max_drawdown": float(report.max_drawdown),
        "sharpe_ratio": float(report.sharpe_ratio),
        "calmar_ratio": float(report.calmar_ratio),
        "win_rate": float(report.win_rate),
        "risk_reward_ratio": float(report.risk_reward_ratio),
        "profit_factor": float(report.profit_factor),
        "total_trades": report.total_trades,
        "winning_trades": report.winning_trades,
        "losing_trades": report.losing_trades,
        "avg_win": float(report.avg_win),
        "avg_loss": float(report.avg_loss),
        "total_commission": float(report.total_commission),
        "total_slippage": float(report.total_slippage),
        "total_funding_paid": float(report.total_funding_paid),
    }


def print_performance_report(report):
    """Print formatted performance report."""
    print("\n" + "=" * 80)
    print("DRAMM 策略回测绩效报告".center(80))
    print("=" * 80)
    
    # Account Metrics
    print("\n【账户指标】")
    print(f"  初始资金: ${report.initial_balance:,.2f}")
    print(f"  最终资金: ${report.final_balance:,.2f}")
    print(f"  总收益: ${report.final_balance - report.initial_balance:,.2f}")
    print(f"  总收益率: {report.total_return:+.2f}%")
    print(f"  年化收益率: {report.annualized_return:+.2f}%")
    
    # Risk Metrics
    print("\n【风险指标】")
    print(f"  最大回撤: {report.max_drawdown:.2f}%")
    print(f"  最大回撤持续: {report.max_drawdown_duration}")
    print(f"  夏普比率: {report.sharpe_ratio:.3f}")
    print(f"  索提诺比率: {report.sortino_ratio:.3f}")
    print(f"  卡尔马比率: {report.calmar_ratio:.3f}")
    
    # Trading Statistics
    print("\n【交易统计】")
    print(f"  总交易次数: {report.total_trades}")
    print(f"  盈利交易: {report.winning_trades}")
    print(f"  亏损交易: {report.losing_trades}")
    print(f"  胜率: {report.win_rate:.2f}%")
    print(f"  平均盈利: ${report.avg_win:,.2f}")
    print(f"  平均亏损: ${report.avg_loss:,.2f}")
    print(f"  盈亏比: {report.risk_reward_ratio:.2f}")
    print(f"  利润因子: {report.profit_factor:.2f}")
    
    # Costs
    print("\n【交易成本】")
    print(f"  总手续费: ${report.total_commission:,.2f}")
    print(f"  总滑点: ${report.total_slippage:,.2f}")
    print(f"  总资金费率: ${report.total_funding_paid:,.2f}")
    print(f"  总成本: ${report.total_commission + report.total_slippage + report.total_funding_paid:,.2f}")
    
    # Time Period
    print("\n【回测周期】")
    print(f"  开始日期: {report.start_date.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  结束日期: {report.end_date.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  回测时长: {report.duration}")
    
    # Trade Details
    if report.trades:
        print("\n【交易明细（前10笔）】")
        for i, trade in enumerate(report.trades[:10], 1):
            side = "做多" if trade.side == "long" else "做空"
            print(f"  {i}. {side} | 入场: ${trade.entry_price:,.2f} | "
                  f"出场: ${trade.exit_price:,.2f} | "
                  f"盈亏: ${trade.pnl:,.2f} ({trade.pnl_percent:+.2f}%)")
        
        if len(report.trades) > 10:
            print(f"  ... 还有 {len(report.trades) - 10} 笔交易")
    
    print("\n" + "=" * 80)


def analyze_equity_curve(equity_curve):
    """Analyze equity curve patterns."""
    if not equity_curve:
        return
    
    print("\n【资金曲线分析】")
    
    balances = [point["balance"] for point in equity_curve]
    initial = balances[0]
    peak = max(balances)
    trough = min(balances)
    
    peak_index = balances.index(peak)
    trough_index = balances.index(trough)
    
    print(f"  最高点: ${peak:,.2f} ({equity_curve[peak_index]['timestamp'].strftime('%Y-%m-%d')})")
    print(f"  最低点: ${trough:,.2f} ({equity_curve[trough_index]['timestamp'].strftime('%Y-%m-%d')})")
    print(f"  波动范围: {(peak - trough) / initial * 100:.2f}%")
    
    # Calculate daily returns
    daily_returns = []
    for i in range(1, len(balances)):
        daily_return = (balances[i] - balances[i-1]) / balances[i-1] * 100
        daily_returns.append(daily_return)
    
    if daily_returns:
        import statistics
        avg_return = statistics.mean(daily_returns)
        std_return = statistics.stdev(daily_returns) if len(daily_returns) > 1 else 0
        max_daily_gain = max(daily_returns)
        max_daily_loss = min(daily_returns)
        
        print(f"  平均日收益: {avg_return:+.3f}%")
        print(f"  日收益标准差: {std_return:.3f}%")
        print(f"  最大单日收益: +{max_daily_gain:.3f}%")
        print(f"  最大单日亏损: {max_daily_loss:.3f}%")


def analyze_regime_performance(engine, equity_curve):
    """Analyze performance by market regime."""
    print("\n【市场状态分析】")
    
    if not hasattr(engine, 'strategy') or not engine.strategy:
        return
    
    try:
        # Count bars by regime
        regime_counts = {}
        for bar in engine.all_bars:
            if hasattr(engine.strategy, 'regime_history'):
                regime = engine.strategy.regime_history.get(bar.timestamp, "unknown")
                regime_counts[regime] = regime_counts.get(regime, 0) + 1
        
        if regime_counts:
            total = sum(regime_counts.values())
            for regime, count in sorted(regime_counts.items(), key=lambda x: -x[1]):
                percentage = count / total * 100
                print(f"  {regime.upper()}: {count} 根K线 ({percentage:.1f}%)")
    except Exception as e:
        print(f"  状态分析不可用: {e}")


def save_report_to_json(report, metrics_summary, equity_curve, filename="dramm_performance_report.json"):
    """Save report to JSON file."""
    output = {
        "timestamp": datetime.now().isoformat(),
        "metrics": metrics_summary,
        "account": {
            "initial_balance": str(report.initial_balance),
            "final_balance": str(report.final_balance),
        },
        "period": {
            "start_date": report.start_date.isoformat(),
            "end_date": report.end_date.isoformat(),
            "duration_days": report.duration.days,
        },
        "equity_curve": [
            {
                "timestamp": point["timestamp"].isoformat(),
                "balance": float(point["balance"]),
            }
            for point in equity_curve
        ],
        "trades": [
            {
                "entry_timestamp": trade.entry_timestamp.isoformat(),
                "exit_timestamp": trade.exit_timestamp.isoformat(),
                "side": trade.side,
                "entry_price": float(trade.entry_price),
                "exit_price": float(trade.exit_price),
                "quantity": float(trade.quantity),
                "pnl": float(trade.pnl),
                "pnl_percent": float(trade.pnl_percent),
                "commission": float(trade.commission),
            }
            for trade in report.trades
        ],
    }
    
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    
    print(f"\n报告已保存到: {filename}")


def main():
    """Main backtest execution."""
    print("开始 DRAMM 策略回测...")
    
    # Configuration
    SYMBOL = "ETH/USDT"
    TIMEFRAME = "15m"
    INITIAL_BALANCE = Decimal("10000")
    
    # Date range: Last 60 days
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=60)
    
    print(f"\n配置参数:")
    print(f"  交易对: {SYMBOL}")
    print(f"  时间周期: {TIMEFRAME}")
    print(f"  初始资金: ${INITIAL_BALANCE}")
    print(f"  回测区间: {start_date.strftime('%Y-%m-%d')} 至 {end_date.strftime('%Y-%m-%d')}")
    
    # Initialize backtest engine
    print("\n1. 初始化回测引擎...")
    engine = BacktestEngine(
        initial_balance=INITIAL_BALANCE,
        slippage=Decimal("0.0005"),  # 0.05% slippage
        commission=Decimal("0.0004"),  # 0.04% commission
        use_volatility_slippage=True,  # Use volatility-based slippage
    )
    
    # Download historical data
    print("\n2. 下载历史数据 (使用代理)...")
    try:
        engine.download_data(
            symbol=SYMBOL,
            start_date=start_date,
            end_date=end_date,
            timeframe=TIMEFRAME,
            exchange="binance",
        )
        print(f"  已下载 {len(engine.all_bars)} 根K线数据")
    except Exception as e:
        print(f"  数据下载失败: {e}")
        # Use pc prefix for proxy
        print("  尝试使用代理下载数据...")
        import subprocess
        result = subprocess.run(
            ["pc", sys.executable, "-c", """
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
sys.path.insert(0, 'src')
from trader.infrastructure.data_downloader import DataDownloader

end_date = datetime.now(timezone.utc)
start_date = end_date - timedelta(days=60)
downloader = DataDownloader('binance', '.env.dev')
since = int(start_date.timestamp() * 1000)
bars = downloader.download_ohlcv('ETH/USDT', '15m', since, limit=1000)
funding_rates = downloader.download_funding_rates('ETH/USDT', since, limit=1000)
print(f'Downloaded {len(bars)} bars, {len(funding_rates)} funding rates')
"""],
            capture_output=True,
            text=True,
        )
        print(result.stdout)
        if result.stderr:
            print(result.stderr)
        return
    
    # Initialize DRAMM strategy
    print("\n3. 初始化 DRAMM 策略...")
    strategy = DRAMMStrategy(
        position_size=0.1,  # 10% of balance per trade
        use_percentage_position_size=True
    )
    engine.set_strategy(strategy)
    
    # Run backtest
    print("\n4. 运行回测...")
    try:
        engine.run(symbol=SYMBOL)
        print("  回测完成!")
    except Exception as e:
        print(f"  回测失败: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Generate performance report
    print("\n5. 生成绩效报告...")
    report_generator = BacktestReportGenerator(
        risk_free_rate=Decimal("0.02"),  # 2% annual risk-free rate
        annual_trading_days=365,  # 24/7 crypto market
    )
    
    # Convert fills to complete trade pairs (entry + exit)
    from trader.application.backtest_report import TradeRecord
    
    # Group fills into trades based on position tracking
    # Each trade consists of an entry fill and an exit fill
    trades = []
    
    # Track positions to match entry and exit fills
    current_positions = {}  # symbol -> {'side': side, 'entry': fill, 'quantity': Decimal}
    
    for fill in engine.trades:
        symbol = SYMBOL  # Use the main symbol
        side = fill["side"]
        price = fill["price"]
        quantity = fill["quantity"]
        commission = fill["commission"]
        timestamp = fill["timestamp"]
        
        if symbol in current_positions:
            # Closing a position
            pos = current_positions.pop(symbol)
            entry = pos["entry"]
            
            # Calculate P&L
            if pos["side"] == "buy":
                # Long position: sold to close
                pnl = (price - entry["price"]) * quantity - commission - entry["commission"]
            else:
                # Short position: bought to cover
                pnl = (entry["price"] - price) * quantity - commission - entry["commission"]
            
            pnl_percent = (pnl / (entry["price"] * quantity)) * 100
            
            trades.append(TradeRecord(
                entry_timestamp=entry["timestamp"],
                exit_timestamp=timestamp,
                side="long" if pos["side"] == "buy" else "short",
                entry_price=entry["price"],
                exit_price=price,
                quantity=quantity,
                pnl=pnl,
                pnl_percent=Decimal(str(pnl_percent)),
                commission=commission + entry["commission"],
            ))
        else:
            # Opening a new position
            current_positions[symbol] = {
                "side": side,
                "entry": fill,
                "quantity": quantity,
            }
    
    # Close any remaining positions as if closed at the last bar
    if engine.equity_curve and current_positions:
        last_timestamp = engine.equity_curve[-1]["timestamp"]
        for symbol, pos in current_positions.items():
            entry = pos["entry"]
            # Use close price from last bar for exit
            last_bar = None
            for bar in reversed(engine.all_bars):
                if bar.symbol == symbol:
                    last_bar = bar
                    break
            if last_bar:
                exit_price = last_bar.close
                if pos["side"] == "buy":
                    pnl = (exit_price - entry["price"]) * pos["quantity"] - entry["commission"]
                else:
                    pnl = (entry["price"] - exit_price) * pos["quantity"] - entry["commission"]
                pnl_percent = (pnl / (entry["price"] * pos["quantity"])) * 100
                
                trades.append(TradeRecord(
                    entry_timestamp=entry["timestamp"],
                    exit_timestamp=last_timestamp,
                    side="long" if pos["side"] == "buy" else "short",
                    entry_price=entry["price"],
                    exit_price=exit_price,
                    quantity=pos["quantity"],
                    pnl=pnl,
                    pnl_percent=Decimal(str(pnl_percent)),
                    commission=entry["commission"],
                ))
    
    report = report_generator.generate_report(
        initial_balance=INITIAL_BALANCE,
        final_balance=engine.broker.balance,
        equity_curve=engine.equity_curve,
        trades=trades,
        total_commission=engine.total_commission,
        total_slippage=engine.total_slippage,
        total_funding_paid=engine.total_funding_paid,
    )
    
    # Print formatted report
    print_performance_report(report)
    
    # Additional analysis
    analyze_equity_curve(engine.equity_curve)
    analyze_regime_performance(engine, engine.equity_curve)
    
    # Calculate metrics summary
    metrics_summary = calculate_metrics_summary(report)
    
    # Save report to JSON
    save_report_to_json(report, metrics_summary, engine.equity_curve)
    
    # Print final summary
    print("\n" + "🎯" * 40)
    print("关键绩效指标汇总".center(80))
    print("🎯" * 40)
    print(f"总收益率: {metrics_summary['total_return']:+.2f}%")
    print(f"年化收益率: {metrics_summary['annualized_return']:+.2f}%")
    print(f"最大回撤: {metrics_summary['max_drawdown']:.2f}%")
    print(f"夏普比率: {metrics_summary['sharpe_ratio']:.3f}")
    print(f"卡尔马比率: {metrics_summary['calmar_ratio']:.3f}")
    print(f"胜率: {metrics_summary['win_rate']:.2f}%")
    print(f"盈亏比: {metrics_summary['risk_reward_ratio']:.2f}")
    print(f"总交易次数: {metrics_summary['total_trades']}")
    print("🎯" * 40)


if __name__ == "__main__":
    main()
