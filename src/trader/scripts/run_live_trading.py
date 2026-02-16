
"""
Live Trading & Backtest Runner Script
======================================

完整的实盘交易和历史回测入口脚本。
- 实盘模式：使用 RealBroker 连接币安 Testnet
- 回测模式：使用 BacktestEngine 进行历史回测

Usage:
    # 实盘模式
    python -m src.trader.scripts.run_live_trading --strategy dramm --duration 600
    
    # 回测模式
    python -m src.trader.scripts.run_live_trading --backtest --strategy dramm --backtest-bars 2000
"""

import os
import sys
import time
import signal
from datetime import datetime
from decimal import Decimal
from typing import Optional

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))

from src.trader.application.strategies.crypto_classic import (
    RSIBollingerStrategy,
)
from src.trader.application.strategies.crypto_classic import (
    RSIBollingerStrategy,
)
from src.trader.application.strategies.dramm import DRAMMStrategy
from src.trader.application.strategies.grid import DynamicGridStrategy
from src.trader.application.risk_manager import RiskManager
from src.trader.application.backtest_engine import BacktestEngine
from src.trader.application.backtest_report import BacktestReportGenerator
from src.trader.infrastructure.event_bus import EventBus
from src.trader.infrastructure.data_downloader import DataDownloader
from src.trader.infrastructure.real_broker import RealBroker
from src.trader.infrastructure.state_persistence import StatePersistence
from src.trader.infrastructure.clock import RealtimeClock
from src.trader.infrastructure.data_repository import BarData


def clear_screen() -> None:
    """Clear the console screen."""
    os.system("cls" if os.name == "nt" else "clear")


def print_header(symbol: str, strategy_name: str, mode: str = "LIVE") -> None:
    """Print the dashboard header."""
    print("=" * 80)
    if mode.upper() == "BACKTEST":
        print("CRYPTO HISTORICAL BACKTEST")
    else:
        print("CRYPTO LIVE TRADING - BINANCE TESTNET (ORDER SYNC ENABLED)")
    print("=" * 80)
    print(f"Symbol: {symbol}")
    print(f"Strategy: {strategy_name}")
    print(f"Mode: {mode.upper()}")
    print(f"Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print("-" * 80)


def print_account_summary(broker: RealBroker) -> None:
    """Print account summary."""
    summary = broker.get_account_summary()
    print("\nACCOUNT SUMMARY")
    print("-" * 80)
    print(f"| Balance: ${summary['balance']:,.2f} | Equity: ${summary['equity']:,.2f} | Positions: {summary['positions']} |")
    print(f"| Open Orders: {summary['open_orders']} | Return: {summary['return_pct']:.2f}% |")
    print("-" * 80)


def print_market_data(
    current_price: Decimal,
    bid: Optional[Decimal],
    ask: Optional[Decimal],
    last_bar: Optional[BarData],
) -> None:
    """Print market data."""
    print("\nMARKET DATA")
    print("-" * 80)
    print(f"| Current Price: ${current_price:,.2f}")
    if bid and ask:
        print(f"| Bid: ${bid:,.2f} | Ask: ${ask:,.2f} | Spread: ${ask - bid:,.4f}")
    if last_bar:
        print(f"| Last Bar: {last_bar.timestamp.strftime('%H:%M:%S')} | O: ${last_bar.open:,.2f} | H: ${last_bar.high:,.2f} | L: ${last_bar.low:,.2f} | C: ${last_bar.close:,.2f} |")
    print("-" * 80)


def print_positions(broker: RealBroker, symbol: str) -> None:
    """Print current positions."""
    position = broker.get_position(symbol)
    print("\nPOSITIONS")
    print("-" * 80)
    if position:
        current_price = broker.get_market_price(symbol)
        if current_price:
            unrealized_pnl = position.calculate_unrealized_pnl(current_price)
            pnl_indicator = "+" if unrealized_pnl >= 0 else "-"
            print(f"{pnl_indicator} {position.side.value} {position.quantity} {position.symbol}")
            print(f"   Entry: ${position.entry_price:,.2f} | Current: ${current_price:,.2f}")
            print(f"   Unrealized PnL: ${unrealized_pnl:,.2f}")
            print(f"   Liq Price: ${position.liquidation_price:,.2f}")
    else:
        print("No open positions")
    print("-" * 80)


def run_live_trading(
    symbol: str = "BTC/USDT:USDT",
    duration_seconds: int = 300,
    sync_interval: int = 5,
    initial_balance: int = 10000,
    strategy_name: str = "rsi_bollinger",
    market_type: str = "spot",
    leverage: int = 1,
    capital_usage: int = 50,
    silent: bool = False,
) -> None:
    """
    Run live trading with live market data and order sync on Binance Testnet.

    Args:
        symbol: Trading symbol (default: BTC/USDT perpetual)
        duration_seconds: How long to run (default: 300 seconds / 5 minutes). 0 for infinite.
        sync_interval: Order sync interval in seconds (default: 5)
        initial_balance: Initial balance for risk manager (default: 10000)
        strategy_name: Strategy to use ("rsi_bollinger" or "dramm")
        market_type: Market type ("spot" or "future")
        leverage: Leverage value (default: 1)
        silent: Silent mode (suppress TUI, run indefinitely by default)
    """
    # Initialize components
    event_bus = EventBus()
    clock = RealtimeClock()
    data_downloader = DataDownloader(exchange_name="binance", env_file=".env.dev")
    
    # Configure DataDownloader for futures if needed
    if market_type == "future":
        data_downloader.exchange.options['defaultType'] = 'future'
    
    # Initialize risk manager
    risk_manager = RiskManager(
        initial_balance=Decimal(str(initial_balance)),
        max_drawdown_pct=Decimal("0.05"),
        daily_loss_limit_pct=Decimal("0.10"),
        max_order_size=Decimal("100.0"),  # ETH max per order
        max_position_pct=Decimal("0.5"),
    )
    risk_manager._leverage = leverage  # Pass leverage for margin-based position checks
    
    # Initialize state persistence
    state_persistence = StatePersistence()
    
    # Create RealBroker with risk management and persistence
    broker = RealBroker(
        event_bus=event_bus,
        env_file=".env.dev",
        testnet=True,
        risk_manager=risk_manager,
        state_persistence=state_persistence,
        market_type=market_type,
    )

    # Create strategy based on strategy_name parameter
    if strategy_name.lower() == "dramm":
        print("\n[SETUP] Using DRAMM (Dynamic Regime Adaptive Multi-Factor) Strategy")
        strategy = DRAMMStrategy(
            adx_period=14,
            bollinger_period=20,
            bollinger_std=Decimal("2"),
            rsi_period=14,
            atr_period=14,
            zscore_period=20,
            position_size=0.001,
            atr_multiplier=Decimal("3"),
            entry_score_threshold=Decimal("0.8"),
            exit_score_threshold=Decimal("-0.6"),
        )
    elif strategy_name.lower() == "grid":
        print("\n[SETUP] Using Dynamic Grid Strategy (Optimized)")
        strategy = DynamicGridStrategy(
             symbol=symbol,
             grid_number=10, 
             atr_multiplier=20.0,
             min_profit_per_grid=0.003,
             stop_loss_buffer=0.005,
             position_size=0.01, # Fallback only, dynamic calc overrides this
             trend_filter_enabled=True,
             grid_spacing="geometric",
             leverage=leverage,
             capital_usage=capital_usage / 100,  # Convert percentage to fraction
        )
    else:
        print("\n[SETUP] Using RSI Bollinger Strategy")
        strategy = RSIBollingerStrategy(
            bollinger_period=20,
            bollinger_std=Decimal("2"),
            rsi_period=14,
            rsi_overbought=Decimal("55"),
            rsi_oversold=Decimal("45"),
            position_size=0.001,
            stop_loss_pct=Decimal("0.02"),
            take_profit_pct=Decimal("0.04"),
        )

    # Inject broker, clock, and event_bus into strategy
    strategy.broker = broker
    strategy.clock = clock
    strategy.event_bus = event_bus

    # Signal handler for graceful shutdown
    running = True
    def signal_handler(signum, frame):
        nonlocal running
        print("\n\n🛑 Received shutdown signal...")
        running = False

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    print_header(symbol, strategy.name, mode="LIVE")

    # Verify connection
    print("\nConnecting to Binance Testnet...")
    summary = broker.get_account_summary()
    print("Connected successfully!")
    print_account_summary(broker)

    # Set leverage if futures
    if market_type == "future":
        print(f"\nSetting leverage to {leverage}x...")
        broker.set_leverage(symbol, leverage)

    # Preload initial historical data for indicators
    print("\nPreloading initial historical data...")
    try:
        strategy.trading_enabled = False
        print("   Trading disabled during preload")
        
        ohlcv_data = data_downloader.download_ohlcv(
            symbol=symbol,
            timeframe="1m",
            limit=200,
        )
        for bar in ohlcv_data:
            strategy.on_bar(bar)
        print(f"Preloaded {len(ohlcv_data)} bars")
        
        strategy.trading_enabled = True
        print("   Trading enabled for live trading")
        
        # Reset grid state after preload so live trading can initialize fresh grids
        if hasattr(strategy, 'grid_lines'):
            strategy.grid_lines = []
            strategy.grid_orders = {}
            strategy.upper_limit = None
            strategy.lower_limit = None
            strategy.pivot_price = None
            print("   Grid state reset for live trading (preload complete)")
    except Exception as e:
        print(f"Warning: Could not preload historical data: {e}")
        strategy.trading_enabled = True

    # Start order sync
    print(f"\nStarting order synchronization (interval: {sync_interval}s)...")
    broker.start_order_sync(interval=sync_interval)

    # Main loop
    print(f"\nStarting live trading loop... (Silent: {silent})")
    if duration_seconds > 0:
        print(f"   Duration: {duration_seconds} seconds")
    else:
        print(f"   Duration: Infinite")
    print(f"   Press Ctrl+C to stop early")
    print("-" * 80)

    start_time = time.time()
    last_bar_time: Optional[datetime] = None
    iteration = 0
    latest_bar = None

    try:
        while running:
            # Check duration
            if duration_seconds > 0 and (time.time() - start_time >= duration_seconds):
                 break
            
            iteration += 1

            if not silent:
                clear_screen()
                print_header(symbol, strategy.name, mode="LIVE")

            try:
                ticker = data_downloader.fetch_ticker(symbol)
                current_price = Decimal(str(ticker.get("last", 0)) if ticker.get("last") else 0)

                order_book = data_downloader.fetch_order_book(symbol, limit=5)
                bid = Decimal(str(order_book["bids"][0][0])) if order_book.get("bids") else None
                ask = Decimal(str(order_book["asks"][0][0])) if order_book.get("asks") else None

                if current_price:
                    broker.market_prices[symbol] = current_price

                try:
                    ohlcv_recent = data_downloader.download_ohlcv(
                        symbol=symbol,
                        timeframe="1m",
                        limit=2,
                    )
                    if ohlcv_recent:
                        latest_bar = ohlcv_recent[-1]
                        if last_bar_time != latest_bar.timestamp:
                            last_bar_time = latest_bar.timestamp
                            if not silent:
                                print(f"\nNew bar received: {latest_bar.timestamp}")
                            else:
                                print(f"[{datetime.now().strftime('%H:%M:%S')}] New Bar: {latest_bar.timestamp} | Price: {latest_bar.close}")
                            try:
                                strategy.on_bar(latest_bar)
                            except Exception as bar_err:
                                print(f"❌ [STRATEGY] on_bar error: {bar_err}")
                                import traceback; traceback.print_exc()
                except Exception as e:
                    pass

                if not silent:
                    print_account_summary(broker)
                    print_market_data(
                        current_price=current_price,
                        bid=bid,
                        ask=ask,
                        last_bar=latest_bar,
                    )
                    print_positions(broker, symbol)

                    print(f"\nIteration: {iteration} | Elapsed: {int(time.time() - start_time)}s / {duration_seconds}s")
                    print(f"Order Sync: RUNNING (interval: {sync_interval}s)")
                else:
                    # Silent heartbeat
                    elapsed = int(time.time() - start_time)
                    print(f"\r[{datetime.now().strftime('%H:%M:%S')}] Iter: {iteration} | Price: {current_price} | Positions: {len(broker.positions)} | Balance: {broker.get_balance():.2f} | Elapsed: {elapsed}s", end="")

                save_interval = 100 if silent else 10
                if iteration % save_interval == 0:
                    broker._save_state_periodically()

            except Exception as e:
                print(f"\nError: {e}")
                import traceback
                traceback.print_exc()

            time.sleep(2)

    except KeyboardInterrupt:
        print("\n\nStopped by user")
    finally:
        # Cancel all open orders before exiting
        print("\n📤 Cancelling all open orders...")
        try:
            broker.cancel_all_orders(symbol)
            print("✅ All open orders cancelled")
        except Exception as e:
            print(f"⚠️ Failed to cancel orders: {e}")

        print("Stopping order synchronization...")
        broker.stop_order_sync()
        print("\nSaving final state...")
        broker._save_state_periodically()

    print("\n" + "=" * 80)
    print("TRADING SESSION COMPLETE")
    print("=" * 80)
    print_account_summary(broker)
    print_positions(broker, symbol)


def run_backtest(
    symbol: str,
    strategy_name: str,
    backtest_bars: int,
    backtest_start: Optional[str],
    backtest_end: Optional[str],
    backtest_initial_balance: int,
    backtest_slippage: float,
    backtest_commission: float,
    backtest_timeframe: str,
) -> None:
    """
    Run historical backtest using BacktestEngine.

    Args:
        symbol: Trading symbol
        strategy_name: Strategy to use ("rsi_bollinger" or "dramm")
        backtest_bars: Number of bars to backtest
        backtest_start: Backtest start time (ISO format)
        backtest_end: Backtest end time (ISO format)
        backtest_initial_balance: Initial balance for backtest
        backtest_slippage: Slippage rate (default 0.0005)
        backtest_commission: Commission rate (default 0.0004)
        backtest_timeframe: K-line timeframe (default 1m)
    """
    print_header(symbol, strategy_name, mode="BACKTEST")

    # Initialize data downloader
    print("\n[SETUP] Initializing data downloader...")
    data_downloader = DataDownloader(exchange_name="binance", env_file=".env.dev", testnet=False)

    # Download historical data
    print("\n[DATA] Downloading historical data...")
    try:
        # For simplicity, always use limit for now
        bars = data_downloader.download_ohlcv(
            symbol=symbol,
            timeframe=backtest_timeframe,
            limit=backtest_bars,
        )
        funding_rates = []  # No funding rates for spot
        print(f"[OK] Downloaded {len(bars)} bars of {backtest_timeframe} data")
        if bars:
            print(f"  Date range: {bars[0].timestamp} to {bars[-1].timestamp}")
            print(f"  Price range: ${bars[0].close:.2f} -> ${bars[-1].close:.2f}")
    except Exception as e:
        print(f"\n[ERROR] Failed to download historical data: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    # Create backtest engine
    print("\n[ENGINE] Initializing backtest engine...")
    engine = BacktestEngine(
        initial_balance=Decimal(str(backtest_initial_balance)),
        slippage=Decimal(str(backtest_slippage)),
        commission=Decimal(str(backtest_commission)),
    )
    print(f"[OK] Initial balance: ${backtest_initial_balance:,.2f}")
    print(f"[OK] Slippage: {backtest_slippage*100:.4f}%")
    print(f"[OK] Commission: {backtest_commission*100:.4f}%")

    # Load data
    engine.load_data(bars, funding_rates)

    # Create strategy
    print(f"\n[STRATEGY] Creating {strategy_name.upper()} strategy...")
    if strategy_name.lower() == "dramm":
        strategy = DRAMMStrategy(
            adx_period=14,
            bollinger_period=20,
            bollinger_std=Decimal("2"),
            rsi_period=14,
            atr_period=14,
            zscore_period=20,
            position_size=0.01,  # 增加头寸规模
            atr_multiplier=Decimal("3"),
            entry_score_threshold=Decimal("0.3"),  # 降低入场阈值
            exit_score_threshold=Decimal("-0.2"),  # 降低出场阈值
        )
    else:
        strategy = RSIBollingerStrategy(
            bollinger_period=20,
            bollinger_std=Decimal("2"),
            rsi_period=14,
            rsi_overbought=Decimal("55"),
            rsi_oversold=Decimal("45"),
            position_size=0.01,  # 增加头寸规模
            stop_loss_pct=Decimal("0.02"),
            take_profit_pct=Decimal("0.04"),
        )
    print(f"[OK] Strategy initialized: {strategy.name}")

    # Set strategy in engine
    engine.set_strategy(strategy)

    # Run backtest
    print("\n[BACKTEST] Running backtest...")
    print("-" * 80)
    result = engine.run(symbol)
    print("-" * 80)

    # Print report from engine result
    print("\n[REPORT] Backtest Results:")
    print(result["formatted_report"])

    # Final summary
    print("\n" + "=" * 80)
    print("BACKTEST COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Run live trading or historical backtest on Binance"
    )

    # Common arguments
    parser.add_argument(
        "--symbol",
        type=str,
        default="BTC/USDT",
        help="Trading symbol (default: BTC/USDT)",
    )
    parser.add_argument(
        "--strategy",
        type=str,
        default="rsi_bollinger",
        choices=["rsi_bollinger", "dramm", "grid"],
        help="Strategy to use (default: rsi_bollinger, options: rsi_bollinger, dramm)",
    )

    # Mode switch
    parser.add_argument(
        "--backtest",
        action="store_true",
        help="Enable backtest mode (default: live trading mode)",
    )

    # Live trading specific arguments
    parser.add_argument(
        "--duration",
        type=int,
        default=300,
        help="Live trading duration in seconds (default: 300 / 5 minutes)",
    )
    parser.add_argument(
        "--sync-interval",
        type=int,
        default=5,
        help="Order sync interval in seconds (default: 5)",
    )
    parser.add_argument(
        "--initial-balance",
        type=int,
        default=10000,
        help="Initial balance for risk manager (default: 10000)",
    )

    # Backtest specific arguments
    parser.add_argument(
        "--backtest-bars",
        type=int,
        default=1000,
        help="Number of bars for backtest (default: 1000)",
    )
    parser.add_argument(
        "--backtest-start",
        type=str,
        default=None,
        help="Backtest start time (ISO format, optional)",
    )
    parser.add_argument(
        "--backtest-end",
        type=str,
        default=None,
        help="Backtest end time (ISO format, optional)",
    )
    parser.add_argument(
        "--backtest-initial-balance",
        type=int,
        default=10000,
        help="Initial balance for backtest (default: 10000)",
    )
    parser.add_argument(
        "--backtest-slippage",
        type=float,
        default=0.0005,
        help="Slippage rate for backtest (default: 0.0005 = 0.05%%)",
    )
    parser.add_argument(
        "--backtest-commission",
        type=float,
        default=0.0004,
        help="Commission rate for backtest (default: 0.0004 = 0.04%%)",
    )
    parser.add_argument(
        "--backtest-timeframe",
        type=str,
        default="1m",
        help="K-line timeframe for backtest (default: 1m)",
    )

    parser.add_argument(
        "--futures",
        action="store_true",
        help="Use futures market (default: spot)",
    )

    parser.add_argument(
        "--leverage",
        type=int,
        default=20,
        help="Leverage for futures (default: 20)",
    )

    parser.add_argument(
        "--capital-usage",
        type=int,
        default=50,
        help="Capital usage percentage for grid strategy (default: 50)",
    )

    parser.add_argument(
        "--silent",
        action="store_true",
        help="Silent mode (suppress TUI, run indefinitely by default)",
    )

    args = parser.parse_args()

    if args.backtest:
        # Backtest mode
        run_backtest(
            symbol=args.symbol,
            strategy_name=args.strategy,
            backtest_bars=args.backtest_bars,
            backtest_start=args.backtest_start,
            backtest_end=args.backtest_end,
            backtest_initial_balance=args.backtest_initial_balance,
            backtest_slippage=args.backtest_slippage,
            backtest_commission=args.backtest_commission,
            backtest_timeframe=args.backtest_timeframe,
        )
    else:
        # Live trading mode
        # For live trading, use perpetual symbol if not specified
        live_symbol = args.symbol
        market_type = "spot"
        
        if args.futures:
            market_type = "future"
            if ":USDT" not in args.symbol and "/" in args.symbol:
                 live_symbol = f"{args.symbol}:USDT"
        
        # Handle duration default
        duration = args.duration
        if args.silent and duration == 300:
             # If silent is on and duration is default, set to 0 (infinite)
             # Assumption: user didn't explicitly set --duration 300 if they wanted silent infinite
             duration = 0

        run_live_trading(
            symbol=live_symbol,
            duration_seconds=duration,
            sync_interval=args.sync_interval,
            initial_balance=args.initial_balance,
            strategy_name=args.strategy,
            market_type=market_type,
            leverage=args.leverage,
            capital_usage=args.capital_usage,
            silent=args.silent,
        )
