
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
import math
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
from src.trader.infrastructure.event_bus import EventBus, EventType
from src.trader.infrastructure.data_downloader import DataDownloader
from src.trader.infrastructure.real_broker import RealBroker
from src.trader.infrastructure.state_persistence import StatePersistence
from src.trader.infrastructure.clock import RealtimeClock
from src.trader.infrastructure.data_repository import BarData
from src.trader.infrastructure.live_trading_stats import LiveTradingStats


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
    timeframe: str = "15m",
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
        timeframe: K-line timeframe (default: 15m)
        silent: Silent mode (suppress TUI, run indefinitely by default)
    """
    # Initialize components
    event_bus = EventBus()
    clock = RealtimeClock()
    data_downloader = DataDownloader(exchange_name="binance", env_file=".env.dev")
    
    # Configure DataDownloader for futures if needed
    if market_type == "future":
        data_downloader.exchange.options['defaultType'] = 'future'
    
    # Auto-scale risk limits based on leverage
    # Higher leverage = larger P&L swings, need wider drawdown tolerance
    # Formula: min(3% * leverage + 2%, 30%)
    #   1x  → 5%     5x  → 17%    10x → 30%    20x → 30% (capped)
    auto_max_drawdown = min(Decimal("0.03") * leverage + Decimal("0.02"), Decimal("0.30"))
    auto_daily_loss = min(auto_max_drawdown * 2, Decimal("0.50"))
    
    print(f"📐 [RISK] Auto-scaled limits for {leverage}x leverage:")
    print(f"   Max drawdown: {auto_max_drawdown * 100:.0f}%")
    print(f"   Daily loss limit: {auto_daily_loss * 100:.0f}%")
    
    # Initialize risk manager
    risk_manager = RiskManager(
        initial_balance=Decimal(str(initial_balance)),
        max_drawdown_pct=auto_max_drawdown,
        daily_loss_limit_pct=auto_daily_loss,
        max_order_size=Decimal("1000000000.0"),  # Effectively unlimited quantity, relying on value limits
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
             grid_number=20, 
             atr_multiplier=4.0,
             min_profit_per_grid=0.0005,
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

    # Initialize live trading stats collector
    stats = LiveTradingStats(
        initial_balance=Decimal(str(initial_balance)),
        symbol=symbol,
        leverage=leverage,
    )

    # Wired up event listeners
    def on_order_filled(event):
        try:
            # RealBroker stores orders keyed by exchange_order_id, not internal UUID
            exchange_id = event.data.get("exchange_id")
            if exchange_id:
                order = broker.orders.get(exchange_id)
                if order:
                    strategy.on_order_update(order)
                else:
                    print(f"⚠️ [MAIN] Order not found for exchange_id={exchange_id}")
            # Record fill in stats collector
            stats.on_fill(event.data)
        except Exception as e:
            print(f"❌ [MAIN] Error processing order fill: {e}")
            import traceback
            traceback.print_exc()

    event_bus.subscribe(EventType.ORDER_FILLED, on_order_filled)

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
            timeframe=timeframe,
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
                        timeframe=timeframe,
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

                # Record equity snapshot for Sharpe/drawdown (every ~20s)
                if iteration % 10 == 0:
                    try:
                        equity = broker.get_balance()
                        # Add unrealized P&L
                        for sym, pos in broker.positions.items():
                            mp = broker.market_prices.get(sym)
                            if mp:
                                equity += pos.calculate_unrealized_pnl(mp)
                        stats.record_equity(equity)
                    except Exception:
                        pass

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

    # Compute final equity
    final_balance = broker.get_balance()
    final_equity = final_balance
    for sym, pos in broker.positions.items():
        mp = broker.market_prices.get(sym)
        if mp:
            final_equity += pos.calculate_unrealized_pnl(mp)

    print("\n" + "=" * 80)
    print("TRADING SESSION COMPLETE")
    print("=" * 80)
    print_account_summary(broker)
    print_positions(broker, symbol)

    # Print and save performance statistics
    stats.print_summary(final_balance, final_equity)
    results_path = stats.save_to_file(final_balance, final_equity)
    print(f"\n💾 Results saved to: {results_path}")


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


def run_dry_run(
    symbol: str = "BTC/USDT",
    strategy_name: str = "grid",
    leverage: int = 20,
    capital_usage: int = 50,
    initial_balance: int = 0,
    timeframe: str = "15m",
) -> None:
    """
    Dry-run mode: estimate minimum USDT and optimal position sizing.
    
    Connects to Binance PUBLIC API only (no API key needed for market data).
    Does NOT place any orders.
    
    Args:
        symbol: Trading pair (e.g. BTC/USDT)
        strategy_name: Strategy name (grid recommended)
        leverage: Leverage multiplier
        capital_usage: Capital usage percentage (0-100)
        initial_balance: Override balance for estimation (0 = fetch from exchange)
        timeframe: K-line timeframe (default: 15m)
    """
    from src.trader.utils.indicators import calculate_atr, calculate_bollinger_bands
    
    print("=" * 62)
    print("  DRY-RUN CAPITAL ESTIMATION (No orders will be placed)")
    print("=" * 62)
    
    # --- 1. Initialize exchange (public API only) ---
    data_downloader = DataDownloader(exchange_name="binance", env_file=".env.dev", testnet=False)
    exchange = data_downloader.exchange
    
    # Determine symbols
    futures_symbol = f"{symbol}:USDT" if ":USDT" not in symbol else symbol
    binance_raw = symbol.replace("/", "").replace(":USDT", "")
    
    # --- 2. Load market info ---
    print(f"\n📡 Fetching exchange info for {futures_symbol}...")
    try:
        exchange.options['defaultType'] = 'future'
        exchange.load_markets(True)  # Force reload
    except Exception as e:
        print(f"⚠️ Failed to load markets with future type: {e}")
        print("   Trying spot markets...")
        exchange.options['defaultType'] = 'spot'
        exchange.load_markets(True)
    
    # Find market
    market = exchange.market(futures_symbol) if futures_symbol in exchange.markets else None
    if not market:
        # Fallback: try spot
        market = exchange.market(symbol) if symbol in exchange.markets else None
    
    if not market:
        print(f"❌ Symbol {futures_symbol} not found on exchange.")
        print(f"   Available similar: {[s for s in exchange.markets if binance_raw[:3] in s][:5]}")
        return
    
    # Parse exchange limits
    limits = market.get('limits', {})
    precision = market.get('precision', {})
    info = market.get('info', {})
    
    min_notional = Decimal("5")  # Default
    min_qty = Decimal("0.001")
    step_size = Decimal("0.001")
    tick_size = Decimal("0.01")
    
    # Parse from filters (Binance specific)
    filters = info.get('filters', []) if isinstance(info, dict) else []
    for f in filters:
        ft = f.get('filterType', '')
        if ft == 'MIN_NOTIONAL':
            min_notional = Decimal(str(f.get('notional', f.get('minNotional', '5'))))
        elif ft == 'LOT_SIZE':
            min_qty = Decimal(str(f.get('minQty', '0.001')))
            step_size = Decimal(str(f.get('stepSize', '0.001')))
        elif ft == 'PRICE_FILTER':
            tick_size = Decimal(str(f.get('tickSize', '0.01')))
    
    # Also try CCXT parsed limits
    if limits.get('amount', {}).get('min'):
        min_qty = max(min_qty, Decimal(str(limits['amount']['min'])))
    if limits.get('cost', {}).get('min'):
        min_notional = max(min_notional, Decimal(str(limits['cost']['min'])))
    
    # --- 3. Get current price ---
    print(f"📊 Fetching current price...")
    try:
        ticker = exchange.fetch_ticker(futures_symbol)
        current_price = Decimal(str(ticker['last']))
    except:
        ticker = exchange.fetch_ticker(symbol)
        current_price = Decimal(str(ticker['last']))
    
    # --- 4. Get historical bars for ATR/BB ---
    print(f"📈 Downloading 200 bars of {timeframe} data for indicators...")
    try:
        bars = data_downloader.download_ohlcv(
            symbol=futures_symbol,
            timeframe=timeframe,
            limit=200,
        )
    except Exception as e:
        print(f"   (Failed to download {futures_symbol} data: {e}. Trying spot symbol {symbol} with {timeframe}.)")
        bars = data_downloader.download_ohlcv(symbol=symbol, timeframe=timeframe, limit=200)
    
    if len(bars) < 30:
        print(f"⚠️ Only {len(bars)} bars available. Need at least 30 for reliable estimation.")
        return
    
    closes = [b.close for b in bars]
    highs = [b.high for b in bars]
    lows = [b.low for b in bars]
    
    atr_values = calculate_atr(highs, lows, closes, period=14)
    bb_values = calculate_bollinger_bands(closes, period=20, std_dev=Decimal("2.0"))
    
    atr = atr_values[-1] if atr_values and atr_values[-1] else current_price * Decimal("0.01")
    pivot = bb_values[-1].middle if bb_values and bb_values[-1].middle else current_price
    
    # --- 5. Grid strategy simulation ---
    atr_multiplier = Decimal("4.0")
    grid_number = 20
    min_profit_per_grid = Decimal("0.0005")
    capital_usage_frac = Decimal(str(capital_usage)) / Decimal("100")
    
    range_width = atr * atr_multiplier
    upper_limit = pivot + range_width
    lower_limit = pivot - range_width
    
    if abs(current_price - pivot) > (range_width * Decimal("0.5")):
        pivot = current_price
        upper_limit = pivot + range_width
        lower_limit = pivot - range_width
    
    # Geometric grid count
    min_ratio = Decimal("1") + min_profit_per_grid
    try:
        max_grids = int(math.log(float(upper_limit / lower_limit)) / math.log(float(min_ratio)))
    except (ValueError, ZeroDivisionError):
        max_grids = grid_number
    
    actual_grids = min(grid_number, max_grids)
    if actual_grids < 3:
        actual_grids = 3
    
    # Geometric ratio
    ratio = (upper_limit / lower_limit) ** (Decimal("1") / Decimal(str(actual_grids)))
    grid_spacing_pct = (ratio - Decimal("1")) * Decimal("100")
    
    # --- 6. Capital calculations ---
    # Min qty value in USDT
    min_qty_value = min_qty * current_price
    
    # Min USDT for 1 grid order (must satisfy both min_notional and min_qty * price)
    min_usdt_1_grid = max(min_notional, min_qty_value)
    
    # Min USDT for all grids (bare minimum)
    min_usdt_all_grids_no_lev = min_usdt_1_grid * actual_grids
    
    # With leverage, margin needed is notional / leverage
    min_margin_all_grids = min_usdt_all_grids_no_lev / Decimal(str(leverage))
    
    # Optimal sizing (if balance provided)
    balance = Decimal(str(initial_balance)) if initial_balance > 0 else Decimal("0")
    
    # Try to fetch real balance
    if balance == 0:
        try:
            from dotenv import load_dotenv
            load_dotenv(".env.dev")
            api_key = os.getenv("BINANCE_DEMO_API_KEY") or os.getenv("BINANCE_API_KEY") or ""
            api_secret = os.getenv("BINANCE_DEMO_API_SECRET") or os.getenv("BINANCE_API_SECRET") or ""
            if api_key and api_secret:
                import ccxt
                priv_exchange = ccxt.binance({
                    'apiKey': api_key,
                    'secret': api_secret,
                    'enableRateLimit': True,
                    'options': {'defaultType': 'future'},
                    'urls': {
                        'api': {
                            'fapiPublic': 'https://testnet.binancefuture.com/fapi/v1',
                            'fapiPrivate': 'https://testnet.binancefuture.com/fapi/v1',
                            'fapiPrivateV2': 'https://testnet.binancefuture.com/fapi/v2',
                        },
                    }
                })
                raw_balances = priv_exchange.fapiPrivateV2GetBalance()
                usdt_bal = next((b for b in raw_balances if b['asset'] == 'USDT'), None)
                if usdt_bal:
                    balance = Decimal(str(usdt_bal.get('availableBalance', usdt_bal.get('balance', 0))))
        except Exception as e:
            print(f"   (Could not fetch balance: {e}. Using --initial-balance or default.)")
    
    if balance == 0:
        balance = Decimal("500")  # Default demo
        balance_source = "default (set --initial-balance to override)"
    else:
        balance_source = "exchange (testnet)"
    
    usable_capital = balance * capital_usage_frac * Decimal(str(leverage))
    qty_per_grid = usable_capital / (Decimal(str(actual_grids)) * current_price)
    
    # Round to step size
    qty_per_grid = (qty_per_grid / step_size).to_integral_value(rounding='ROUND_DOWN') * step_size
    value_per_grid = qty_per_grid * current_price
    total_notional = value_per_grid * actual_grids
    
    # Fee estimation
    commission_rate = Decimal("0.0004")  # 0.04% taker
    fee_per_grid_side = value_per_grid * commission_rate
    profit_per_grid = value_per_grid * (ratio - Decimal("1"))
    net_per_grid = profit_per_grid - (fee_per_grid_side * 2)  # buy + sell fees
    
    # Check viability
    viable = qty_per_grid >= min_qty and value_per_grid >= min_notional
    atr = calculate_atr(highs, lows, closes, period=14)[-1]
    
    print(f"\n==============================================================")
    print(f"  📋 DRY-RUN REPORT: {futures_symbol}")
    print(f"==============================================================")
    print(f"")
    print(f"  Symbol:          {futures_symbol}")
    print(f"  Timeframe:       {timeframe}")
    print(f"  Current Price:   ${current_price}")
    print(f"  Leverage:        {leverage}x")
    print(f"  Capital Usage:   {capital_usage}%")
    print(f"  Strategy:        {strategy_name.upper()}")
    print(f"")
    print(f"  --- Exchange Limits ---")
    print(f"  Min Notional:    {min_notional} USDT")
    print(f"  Min Qty:         {min_qty} ({binance_raw.replace('USDT', '')}) (= ${min_qty * current_price:.4f} @ current price)")
    print(f"  Lot Step:        {step_size}")
    print(f"  Price Tick:      {tick_size:.7f}")
    
    print(f"")
    print(f"  --- Grid Strategy Analysis ---")
    print(f"  ATR (14, {timeframe}):    {atr:.4f}")
    print(f"  Pivot (BB Mid):  ${pivot:,.2f}")
    print(f"  Grid Range:      [${lower_limit:,.2f}, ${upper_limit:,.2f}]")
    print(f"  Range Width:     ${range_width:,.2f} ({range_width/current_price*100:.2f}% of price)")
    print(f"  Grid Count:      {actual_grids} (max feasible: {max_grids})")
    print(f"  Grid Spacing:    Geometric (ratio: {ratio:.6f}, ~{grid_spacing_pct:.4f}%)")
    
    print(f"\n  --- Minimum Capital Requirements ---")
    print(f"  Min USDT (1 grid, min qty):         ${min_usdt_1_grid:,.4f}")
    print(f"  Min USDT (all {actual_grids} grids, no lev):   ${min_usdt_all_grids_no_lev:,.4f}")
    print(f"  Min Margin ({actual_grids} grids, {leverage}x lev):  ${min_margin_all_grids:,.4f}")
    
    print(f"\n  --- Optimal Position Sizing ---")
    print(f"  Your Balance:    ${balance:,.2f} ({balance_source})")
    print(f"  Usable Capital:  ${usable_capital:,.2f} (balance × {leverage}x × {capital_usage}%)")
    print(f"  Qty per Grid:    {qty_per_grid} ({binance_raw[:len(binance_raw)-4] if binance_raw.endswith('USDT') else binance_raw})")
    print(f"  Value per Grid:  ${value_per_grid:,.4f}")
    print(f"  Total Notional:  ${total_notional:,.2f}")
    
    print(f"\n  --- Fee Estimate ---")
    print(f"  Commission Rate: {commission_rate*100:.2f}% (taker)")
    print(f"  Fee per Grid:    ${fee_per_grid_side:,.4f} per side")
    print(f"  Profit per Grid: ~${profit_per_grid:,.4f} ({grid_spacing_pct:.4f}% spacing)")
    print(f"  Net per Grid:    ~${net_per_grid:,.4f} (after buy+sell fees)")
    
    print(f"\n  --- Viability Check ---")
    if viable:
        print(f"  ✅ VIABLE: qty_per_grid ({qty_per_grid}) >= min_qty ({min_qty})")
        print(f"  ✅ VIABLE: value_per_grid (${value_per_grid:,.4f}) >= min_notional (${min_notional})")
        if net_per_grid > 0:
            print(f"  ✅ PROFITABLE: net_per_grid (${net_per_grid:,.4f}) > 0")
        else:
            print(f"  ⚠️ WARNING: net_per_grid (${net_per_grid:,.4f}) <= 0. Grid spacing too tight!")
    else:
        print(f"  ❌ NOT VIABLE with current balance/settings:")
        if qty_per_grid < min_qty:
            needed_balance = (min_qty * current_price * actual_grids) / (capital_usage_frac * Decimal(str(leverage)))
            print(f"     qty_per_grid ({qty_per_grid}) < min_qty ({min_qty})")
            print(f"     Minimum balance needed: ${needed_balance:,.2f}")
        if value_per_grid < min_notional:
            needed_balance = (min_notional * actual_grids) / (capital_usage_frac * Decimal(str(leverage)))
            print(f"     value_per_grid (${value_per_grid:,.4f}) < min_notional (${min_notional})")
            print(f"     Minimum balance needed: ${needed_balance:,.2f}")
    
    # Recommendations
    print(f"\n  --- Recommendations ---")
    if actual_grids < grid_number:
        print(f"  💡 Grid count reduced from {grid_number} to {actual_grids} to maintain min profit margin.")
    if not viable:
        suggestions = []
        suggestions.append(f"Increase --initial-balance (try ≥${min_margin_all_grids * 2:,.0f})")
        suggestions.append(f"Increase --leverage (current: {leverage}x)")
        suggestions.append(f"Increase --capital-usage (current: {capital_usage}%)")
        suggestions.append(f"Reduce grid_number (current: {grid_number})")
        for i, s in enumerate(suggestions, 1):
            print(f"  {i}. {s}")
    else:
        print(f"  ✅ Ready to trade! Run without --dry-run to start live trading.")
    
    print("\n" + "=" * 62)


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
        default=5000,
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



    parser.add_argument("--leverage", type=int, default=1, help="Leverage (default: 1)")
    parser.add_argument("--capital-usage", type=int, default=50, help="Capital usage %% (default: 50)")
    parser.add_argument("--timeframe", default="15m", help="K-line timeframe (default: 15m)")
    parser.add_argument("--silent", action="store_true", help="Silent mode (suppress TUI)")
    parser.add_argument("--dry-run", action="store_true", help="Run a dry-run analysis for grid strategy (default: False)")

    args = parser.parse_args()

    # Handle dry-run mode
    if args.dry_run:
        # For dry-run, we need to determine the futures symbol if futures is enabled
        futures_symbol = args.symbol
        if hasattr(args, 'futures') and args.futures:
             if ":USDT" not in args.symbol and "/" in args.symbol:
                  futures_symbol = f"{args.symbol}:USDT"
        
        # Fallback if args.futures is not defined (depending on argparse setup above, which might be missing)
        # Assuming args.futures exists or defaulting logic.
        
        run_dry_run(
            symbol=futures_symbol,
            strategy_name=args.strategy,
            leverage=args.leverage,
            capital_usage=args.capital_usage,
            initial_balance=int(args.initial_balance), # Use 0 by default to autodetect
            timeframe=args.timeframe,
        )
        sys.exit(0)

    # Handle backtest mode
    if args.backtest:
        run_backtest(
            symbol=args.symbol,
            strategy_name=args.strategy,
            backtest_bars=args.backtest_bars,
            backtest_start=args.backtest_start,
            backtest_end=args.backtest_end,
            backtest_initial_balance=int(args.initial_balance),
            backtest_slippage=args.backtest_slippage,
            backtest_commission=args.backtest_commission,
            backtest_timeframe=args.timeframe, # Use CLI arg
        )
    else:
        # Live trading mode
        live_symbol = args.symbol
        market_type = "spot"
        
        # Check for futures arg
        if hasattr(args, 'futures') and args.futures:
            market_type = "future"
            if ":USDT" not in args.symbol and "/" in args.symbol:
                 live_symbol = f"{args.symbol}:USDT"
        elif hasattr(args, 'market_type'):
            market_type = args.market_type
            
        # Handle duration
        duration = args.duration
        if args.silent and duration == 300:
             duration = 0 # Infinite by default in silent mode
             

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
