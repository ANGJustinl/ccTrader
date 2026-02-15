"""Paper trading runner script.

Runs trading strategies in real-time simulation with live market data.
"""
import argparse
import time
from decimal import Decimal
from datetime import datetime, timedelta

from trader.infrastructure.event_bus import EventBus, Event, EventType
from trader.infrastructure.clock import SystemClock
from trader.infrastructure.paper_broker import PaperBroker
from trader.infrastructure.data_repository import BarData
from trader.application.strategies.crypto_classic import RSIBollingerStrategy
from trader.infrastructure.data_downloader import DataDownloader


def run_paper_trading():
    """Run paper trading with live market data."""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Paper Trading Runner")
    parser.add_argument("--symbol", default="BTC/USDT:USDT", help="Trading pair symbol (default: BTC/USDT:USDT)")
    parser.add_argument("--interval", default="1m", help="Interval for market data updates (default: 1m)")
    parser.add_argument("--initial-balance", type=float, default=10000.0, help="Initial balance (default: 10000.0)")
    parser.add_argument("--strategy", choices=["rsi-bollinger"], default="rsi-bollinger", 
                       help="Strategy to run (default: rsi-bollinger)")
    parser.add_argument("--duration", type=int, default=180, 
                       help="Run duration in seconds (default: 60, set 0 for infinite)")
    args = parser.parse_args()

    print("=" * 70)
    print("Paper Trading Started")
    print("=" * 70)
    print(f"Symbol: {args.symbol}")
    print(f"Interval: {args.interval}")
    print(f"Strategy: {args.strategy}")
    print(f"Initial Balance: ${args.initial_balance:,.2f}")
    print(f"Duration: {'Infinite' if (args.duration == 0) else f'{args.duration} seconds'}")
    print("=" * 70)

    # Initialize components
    event_bus = EventBus()
    clock = SystemClock()
    
    # Create paper broker
    paper_broker = PaperBroker(
        event_bus=event_bus,
        initial_balance=Decimal(str(args.initial_balance)),
    )
    
    # Create strategy
    strategy = None
    if args.strategy == "rsi-bollinger":
        strategy = RSIBollingerStrategy(
            bollinger_period=20,
            bollinger_std=Decimal("2"),
            rsi_period=14,
            rsi_overbought=Decimal("70"),
            rsi_oversold=Decimal("30"),
            position_size=0.1,  # 增大仓位到 0.1 BTC
            stop_loss_pct=Decimal("0.02"),
            take_profit_pct=Decimal("0.04"),
        )
    
    if strategy is None:
        print(f"Error: Strategy '{args.strategy}' not implemented")
        return
    
    # Inject broker, clock, and event_bus into strategy
    strategy.broker = paper_broker
    strategy.clock = clock
    strategy.event_bus = event_bus
    
    # Setup order update listener
    def on_order_update(order):
        if order.is_open:
            print(f"⏳ [PAPER] 订单状态更新: {order.id} - {order.status.value}")
    
    event_bus.subscribe(EventType.ORDER_SUBMITTED, lambda e: print(f"📋 [PAPER] 订单已提交: {e.data.get('order_id')}"))
    event_bus.subscribe(EventType.ORDER_FILLED, lambda e: print(f"✅ [PAPER] 订单已成交: {e.data.get('order_id')} @ ${e.data.get('price')}"))
    
    # Initialize data downloader
    downloader = DataDownloader("binance")
    
    # Subscribe to symbol
    print(f"\nConnecting to Binance for {args.symbol}...")
    
    # Pre-load initial history to give strategy enough data to generate signals
    print("Pre-loading initial historical data for strategy...")
    initial_since = int((datetime.now() - timedelta(days=3)).timestamp() * 1000)
    initial_bars = downloader.download_ohlcv(args.symbol, args.interval, initial_since, limit=200)
    
    if initial_bars:
        print(f"Pre-loaded {len(initial_bars)} initial bars for warm-up")
        for bar in initial_bars:
            strategy.bar_history.append(bar)
            strategy.streaming_bb.update(bar.close)
        print("Strategy warm-up complete")
    
    # Run paper trading loop
    start_time = time.time()
    iteration = 0
    
    try:
        while True:
            iteration += 1
            current_time = time.time()
            elapsed = current_time - start_time
            
            # Check duration
            if args.duration > 0 and elapsed >= args.duration:
                print(f"\nReached duration limit ({args.duration}s). Stopping...")
                break
            
            try:
                # Fetch latest data
                print(f"\n--- Iteration {iteration} (Elapsed: {elapsed:.1f}s) ---")
                
                # Download latest K-line for strategy (use most recent completed bar)
                bars = downloader.download_ohlcv(args.symbol, args.interval, limit=2)
                
                # Fetch real-time ticker for current price
                ticker = downloader.fetch_ticker(args.symbol)
                
                # Fetch order book for bid/ask prices
                order_book = downloader.fetch_order_book(args.symbol)
                
                if bars and len(bars) >= 1 and ticker and order_book:
                    # Use most recent bar for strategy
                    latest_bar = bars[-1]
                    
                    # Create a hybrid bar using real-time ticker price for close
                    from trader.infrastructure.data_repository import BarData
                    hybrid_bar = BarData(
                        symbol=args.symbol,
                        timestamp=ticker["timestamp"],
                        open=latest_bar.open,
                        high=max(latest_bar.high, ticker["last"]),
                        low=min(latest_bar.low, ticker["last"]),
                        close=ticker["last"],
                        volume=latest_bar.volume,
                    )
                    
                    # Update PaperBroker's market prices with real-time ticker
                    paper_broker.market_prices[args.symbol] = ticker["last"]
                    
                    bid_str = f"${order_book['bid']:,.2f}" if order_book['bid'] else "N/A"
                    ask_str = f"${order_book['ask']:,.2f}" if order_book['ask'] else "N/A"
                    print(f"📊 [MARKET] {args.symbol} | "
                          f"Last: ${ticker['last']:,.2f} | "
                          f"Bid: {bid_str} | "
                          f"Ask: {ask_str} | "
                          f"24h High: ${ticker['high']:,.2f} | "
                          f"24h Low: ${ticker['low']:,.2f}")
                    
                    # Publish bar event with real-time price
                    event_bus.publish(
                        Event(
                            type=EventType.BAR,
                            timestamp=hybrid_bar.timestamp,
                            data={
                                "symbol": hybrid_bar.symbol,
                                "open": str(hybrid_bar.open),
                                "high": str(hybrid_bar.high),
                                "low": str(hybrid_bar.low),
                                "close": str(hybrid_bar.close),
                                "volume": str(hybrid_bar.volume),
                            },
                        )
                    )
                    
                    # Call strategy with hybrid bar
                    if hasattr(strategy, 'on_bar'):
                        strategy.on_bar(hybrid_bar)
                    
                    # Display account summary
                    summary = paper_broker.get_account_summary()
                    print(f"\n💰 [ACCOUNT] Balance: ${summary['balance']:,.2f} | "
                          f"Equity: ${summary['total_equity']:,.2f} | "
                          f"Positions: {summary['positions']} | "
                          f"Open Orders: {summary['open_orders']} | "
                          f"Return: {summary['total_return']:.2f}%")
                else:
                    print(f"⚠️ No data received for {args.symbol}")
                
                # Wait before next iteration
                time.sleep(10)  # 10 second interval
                
            except KeyboardInterrupt:
                print("\n\nInterrupted by user. Stopping...")
                break
            except Exception as e:
                print(f"❌ Error in iteration {iteration}: {e}")
                time.sleep(5)  # Wait before retry
    finally:
        # Print final summary
        print("\n" + "=" * 70)
        print("Paper Trading Summary")
        print("=" * 70)
        
        final_summary = paper_broker.get_account_summary()
        print(f"Initial Balance: ${paper_broker.initial_balance:,.2f}")
        print(f"Final Balance: ${final_summary['balance']:,.2f}")
        print(f"Final Equity: ${final_summary['total_equity']:,.2f}")
        print(f"Total Return: {final_summary['total_return']:.2f}%")
        print(f"Unrealized PnL: ${final_summary['unrealized_pnl']:,.2f}")
        print(f"Open Positions: {final_summary['positions']}")
        print(f"Open Orders: {final_summary['open_orders']}")
        
        # Print position details
        if paper_broker.positions:
            print("\nOpen Positions:")
            for symbol, position in paper_broker.positions.items():
                current_price = paper_broker.get_market_price(symbol)
                unrealized_pnl = position.calculate_unrealized_pnl(current_price) if current_price else Decimal("0")
                print(f"  {symbol}: {position.side.value} {position.quantity} @ ${position.entry_price:,.2f} | "
                      f"PnL: ${unrealized_pnl:,.2f}")
        
        print("=" * 70)
        print("Paper Trading Stopped")
        print("=" * 70)


if __name__ == "__main__":
    run_paper_trading()
