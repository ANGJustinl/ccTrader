"""
Real Trading Runner Script
=====================

使用币安 Testnet 进行实盘交易
- 连接真实币安模拟盘交易
- 使用 RSIBollingerStrategy 策略
- 实时监听行情并执行交易

Usage:
    python -m src.trader.scripts.run_real_trading
"""

import os
import sys
import time
from datetime import datetime
from decimal import Decimal
from typing import Optional

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))

from src.trader.application.strategies.crypto_classic import (
    RSIBollingerStrategy,
)
from src.trader.infrastructure.event_bus import EventBus
from src.trader.infrastructure.data_downloader import DataDownloader
from src.trader.infrastructure.real_broker import RealBroker
from src.trader.infrastructure.clock import RealtimeClock
from src.trader.infrastructure.data_repository import BarData


def clear_screen() -> None:
    """Clear the console screen."""
    os.system("cls" if os.name == "nt" else "clear")


def print_header(symbol: str, strategy_name: str) -> None:
    """Print the dashboard header."""
    print("=" * 80)
    print("CRYPTO REAL TRADING - BINANCE TESTNET")
    print("=" * 80)
    print(f"Symbol: {symbol}")
    print(f"Strategy: {strategy_name}")
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


def run_real_trading(
    symbol: str = "BTC/USDT:USDT",
    duration_seconds: int = 60,  # 1 minute for testing
) -> None:
    """
    Run real trading with live market data on Binance Testnet.

    Args:
        symbol: Trading symbol (default: BTC/USDT perpetual)
        duration_seconds: How long to run (default: 60 seconds)
    """
    # Initialize components
    event_bus = EventBus()
    clock = RealtimeClock()
    data_downloader = DataDownloader(exchange_name="binance", env_file=".env.dev")
    broker = RealBroker(event_bus, env_file=".env.dev", testnet=True)

    # Create strategy
    strategy = RSIBollingerStrategy(
        name="RSIBollingerReal",
        symbol=symbol,
        rsi_period=14,
        rsi_overbought=70,
        rsi_oversold=30,
        bb_period=20,
        bb_std_dev=Decimal("2"),
        position_size=Decimal("0.001"),  # Smaller size for Testnet
    )

    # Set broker for strategy
    strategy.set_broker(broker)

    print_header(symbol, strategy.name)

    # Verify connection
    print("\nConnecting to Binance Testnet...")
    summary = broker.get_account_summary()
    print("Connected successfully!")
    print_account_summary(broker)

    # Preload initial historical data for indicators
    print("\nPreloading initial historical data...")
    try:
        ohlcv_data = data_downloader.download_ohlcv(
            symbol=symbol,
            timeframe="15m",
            limit=200,
        )
        for bar in ohlcv_data:
            strategy.on_bar(bar)
        print(f"Preloaded {len(ohlcv_data)} bars")
    except Exception as e:
        print(f"Warning: Could not preload historical data: {e}")

    # Main loop
    print("\nStarting real trading loop...")
    print(f"   Duration: {duration_seconds} seconds")
    print(f"   Press Ctrl+C to stop early")
    print("-" * 80)

    start_time = time.time()
    last_bar_time: Optional[datetime] = None
    iteration = 0
    latest_bar = None

    try:
        while time.time() - start_time < duration_seconds:
            iteration += 1

            # Clear screen and print header
            clear_screen()
            print_header(symbol, strategy.name)

            # Get latest market data
            try:
                # Get ticker for current price
                ticker = data_downloader.fetch_ticker(symbol)
                current_price = Decimal(str(ticker.get("last", 0)) if ticker.get("last") else 0)

                # Get order book for bid/ask
                order_book = data_downloader.fetch_order_book(symbol, limit=5)
                bid = Decimal(str(order_book["bids"][0][0])) if order_book.get("bids") else None
                ask = Decimal(str(order_book["asks"][0][0])) if order_book.get("asks") else None

                # Update broker's market prices
                if current_price:
                    broker.market_prices[symbol] = current_price

                # Check for new bar (every 15 minutes)
                try:
                    ohlcv_recent = data_downloader.download_ohlcv(
                        symbol=symbol,
                        timeframe="15m",
                        limit=2,
                    )
                    if ohlcv_recent:
                        latest_bar = ohlcv_recent[-1]
                        if last_bar_time != latest_bar.timestamp:
                            last_bar_time = latest_bar.timestamp
                            print(f"\nNew bar received: {latest_bar.timestamp}")
                            strategy.on_bar(latest_bar)
                except Exception as e:
                    pass

                # Print dashboard
                print_account_summary(broker)
                print_market_data(
                    current_price=current_price,
                    bid=bid,
                    ask=ask,
                    last_bar=latest_bar,
                )
                print_positions(broker, symbol)

                print(f"\nIteration: {iteration} | Elapsed: {int(time.time() - start_time)}s / {duration_seconds}s")

            except Exception as e:
                print(f"\nError: {e}")
                import traceback
                traceback.print_exc()

            # Sleep before next iteration
            time.sleep(2)

    except KeyboardInterrupt:
        print("\n\nStopped by user")

    # Final summary
    print("\n" + "=" * 80)
    print("TRADING SESSION COMPLETE")
    print("=" * 80)
    print_account_summary(broker)
    print_positions(broker, symbol)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run real trading on Binance Testnet")
    parser.add_argument(
        "--symbol",
        type=str,
        default="BTC/USDT:USDT",
        help="Trading symbol (default: BTC/USDT:USDT)",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=60,
        help="Duration in seconds (default: 60)",
    )

    args = parser.parse_args()

    run_real_trading(
        symbol=args.symbol,
        duration_seconds=args.duration,
    )
