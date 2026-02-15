"""Data downloader using CCXT for fetching market data.

Supports downloading OHLCV and funding rate data from various exchanges.
"""
import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional

import ccxt
from dotenv import load_dotenv

from .data_repository import BarData, FundingRateData


class DataDownloader:
    """Use CCXT to download historical data from exchanges."""
    
    def __init__(self, exchange_name: str = "binance", env_file: str = ".env.dev", testnet: bool = False):
        """Initialize data downloader.
        
        Args:
            exchange_name: Name of the exchange (default: "binance" for spot)
            env_file: Path to environment file for proxy configuration
            testnet: Whether to use testnet/sandbox mode (default: False)
        """
        # Load environment variables (this sets HTTP_PROXY/HTTPS_PROXY which requests will use)
        load_dotenv(env_file)
        
        # Initialize exchange - use binance spot
        self.exchange = getattr(ccxt, exchange_name)()
        
        # Enable testnet/sandbox mode if requested
        if testnet:
            self.exchange.set_sandbox_mode(True)
    
    def download_ohlcv(
        self,
        symbol: str,
        timeframe: str = "15m",
        since: Optional[int] = None,
        limit: int = 1000
    ) -> List[BarData]:
        """下载OHLCV数据
        
        Args:
            symbol: Trading pair symbol (e.g., "BTC/USDT:USDT")
            timeframe: Timeframe string (e.g., "1m", "15m", "1h", "1d")
            since: Timestamp in milliseconds to start from
            limit: Maximum number of bars to fetch
        
        Returns:
            List of BarData objects
        """
        ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, since, limit)
        return [
            BarData(
                symbol=symbol,
                timestamp=datetime.fromtimestamp(bar[0] / 1000, tz=timezone.utc),
                open=Decimal(str(bar[1])),
                high=Decimal(str(bar[2])),
                low=Decimal(str(bar[3])),
                close=Decimal(str(bar[4])),
                volume=Decimal(str(bar[5]))
            )
            for bar in ohlcv
        ]
    
    def download_funding_rates(
        self,
        symbol: str,
        since: Optional[int] = None,
        limit: int = 1000
    ) -> List[FundingRateData]:
        """下载资金费率数据
        
        Args:
            symbol: Trading pair symbol (e.g., "BTC/USDT:USDT")
            since: Timestamp in milliseconds to start from
            limit: Maximum number of funding rates to fetch
        
        Returns:
            List of FundingRateData objects
        """
        rates = self.exchange.fetch_funding_rate_history(symbol, since, limit)
        return [
            FundingRateData(
                symbol=symbol,
                rate=Decimal(str(rate["fundingRate"])),
                timestamp=datetime.fromtimestamp(
                    rate["timestamp"] / 1000,
                    tz=timezone.utc
                ),
                next_funding_time=datetime.fromtimestamp(
                    rate["timestamp"] / 1000 + (8 * 60 * 60),  # 8小时后
                    tz=timezone.utc
                )
            )
            for rate in rates
        ]
    
    def fetch_ticker(self, symbol: str) -> dict:
        """获取实时 ticker 数据
        
        Args:
            symbol: Trading pair symbol (e.g., "BTC/USDT:USDT")
        
        Returns:
            Dictionary with ticker data including last price
        """
        ticker = self.exchange.fetch_ticker(symbol)
        return {
            "symbol": symbol,
            "last": Decimal(str(ticker["last"])),
            "bid": Decimal(str(ticker["bid"])) if ticker["bid"] else None,
            "ask": Decimal(str(ticker["ask"])) if ticker["ask"] else None,
            "high": Decimal(str(ticker["high"])),
            "low": Decimal(str(ticker["low"])),
            "volume": Decimal(str(ticker["baseVolume"])),
            "timestamp": datetime.fromtimestamp(ticker["timestamp"] / 1000, tz=timezone.utc),
        }
    
    def fetch_order_book(self, symbol: str, limit: int = 5) -> dict:
        """获取订单簿数据（用于获取 bid/ask 价格）
        
        Args:
            symbol: Trading pair symbol (e.g., "BTC/USDT:USDT")
            limit: Number of orders to fetch
        
        Returns:
            Dictionary with best bid and ask prices
        """
        order_book = self.exchange.fetch_order_book(symbol, limit)
        return {
            "symbol": symbol,
            "bid": Decimal(str(order_book["bids"][0][0])) if order_book["bids"] else None,
            "ask": Decimal(str(order_book["asks"][0][0])) if order_book["asks"] else None,
            "timestamp": datetime.now(timezone.utc),
        }
