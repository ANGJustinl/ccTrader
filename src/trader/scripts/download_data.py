#!/usr/bin/env python3
"""Complete data download script for trading data.

Downloads OHLCV data and funding rates from exchanges using CCXT,
with data validation and storage options.
"""
import argparse
import sys
from pathlib import Path
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Optional, Dict, Any
import json
import csv

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from trader.infrastructure.data_downloader import DataDownloader
from trader.infrastructure.data_repository import BarData, FundingRateData


class DataDownloaderScript:
    """Complete data download and management script."""

    def __init__(self, exchange: str = "binance"):
        """Initialize data downloader.

        Args:
            exchange: Exchange name (default: "binance")
        """
        self.downloader = DataDownloader(exchange)
        self.exchange = exchange

    def download_ohlcv(
        self,
        symbol: str,
        timeframe: str = "15m",
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        days: Optional[int] = None,
    ) -> List[BarData]:
        """Download OHLCV data.

        Args:
            symbol: Trading pair symbol (e.g., "BTC/USDT")
            timeframe: Timeframe (e.g., "1m", "5m", "15m", "1h", "1d")
            start_date: Start date for download
            end_date: End date for download
            days: Number of days to download (alternative to start/end)

        Returns:
            List of BarData objects
        """
        if days is not None:
            end_date = end_date or datetime.utcnow()
            start_date = end_date - timedelta(days=days)

        if start_date is None:
            # Default to last 30 days
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=30)

        since = int(start_date.timestamp() * 1000)

        print(f"Downloading {symbol} {timeframe} data...")
        print(f"From: {start_date.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"To:   {end_date.strftime('%Y-%m-%d %H:%M:%S')}")

        bars = self.downloader.download_ohlcv(symbol, timeframe, since)

        # Filter by end date if provided
        if end_date:
            bars = [bar for bar in bars if bar.timestamp <= end_date]

        print(f"Downloaded {len(bars)} bars")
        return bars

    def download_funding_rates(
        self,
        symbol: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        days: Optional[int] = None,
    ) -> List[FundingRateData]:
        """Download funding rate data.

        Args:
            symbol: Trading pair symbol (e.g., "BTC/USDT")
            start_date: Start date for download
            end_date: End date for download
            days: Number of days to download (alternative to start/end)

        Returns:
            List of FundingRateData objects
        """
        if days is not None:
            end_date = end_date or datetime.utcnow()
            start_date = end_date - timedelta(days=days)

        if start_date is None:
            # Default to last 30 days
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=30)

        since = int(start_date.timestamp() * 1000)

        print(f"\nDownloading {symbol} funding rates...")
        print(f"From: {start_date.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"To:   {end_date.strftime('%Y-%m-%d %H:%M:%S')}")

        rates = self.downloader.download_funding_rates(symbol, since)

        # Filter by end date if provided
        if end_date:
            rates = [rate for rate in rates if rate.timestamp <= end_date]

        print(f"Downloaded {len(rates)} funding rate records")
        return rates

    def save_to_csv(
        self,
        bars: List[BarData],
        filepath: str,
        funding_rates: Optional[List[FundingRateData]] = None,
    ) -> None:
        """Save data to CSV files.

        Args:
            bars: List of BarData objects
            filepath: Base filepath for output (will add _bars.csv and _funding.csv)
            funding_rates: Optional list of FundingRateData objects
        """
        # Save OHLCV data
        bars_path = f"{filepath}_bars.csv"
        with open(bars_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            for bar in bars:
                writer.writerow([
                    bar.timestamp.isoformat(),
                    str(bar.open),
                    str(bar.high),
                    str(bar.low),
                    str(bar.close),
                    str(bar.volume),
                ])
        print(f"Saved OHLCV data to: {bars_path}")

        # Save funding rates if provided
        if funding_rates:
            funding_path = f"{filepath}_funding.csv"
            with open(funding_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['timestamp', 'symbol', 'rate'])
                for rate in funding_rates:
                    writer.writerow([
                        rate.timestamp.isoformat(),
                        rate.symbol,
                        str(rate.rate),
                    ])
            print(f"Saved funding rates to: {funding_path}")

    def save_to_json(
        self,
        bars: List[BarData],
        filepath: str,
        funding_rates: Optional[List[FundingRateData]] = None,
    ) -> None:
        """Save data to JSON files.

        Args:
            bars: List of BarData objects
            filepath: Base filepath for output
            funding_rates: Optional list of FundingRateData objects
        """
        # Save OHLCV data
        bars_path = f"{filepath}_bars.json"
        bars_data = [
            {
                'timestamp': bar.timestamp.isoformat(),
                'open': str(bar.open),
                'high': str(bar.high),
                'low': str(bar.low),
                'close': str(bar.close),
                'volume': str(bar.volume),
            }
            for bar in bars
        ]
        with open(bars_path, 'w', encoding='utf-8') as f:
            json.dump(bars_data, f, indent=2)
        print(f"Saved OHLCV data to: {bars_path}")

        # Save funding rates if provided
        if funding_rates:
            funding_path = f"{filepath}_funding.json"
            funding_data = [
                {
                    'timestamp': rate.timestamp.isoformat(),
                    'symbol': rate.symbol,
                    'rate': str(rate.rate),
                }
                for rate in funding_rates
            ]
            with open(funding_path, 'w', encoding='utf-8') as f:
                json.dump(funding_data, f, indent=2)
            print(f"Saved funding rates to: {funding_path}")

    def validate_data(
        self,
        bars: List[BarData],
        funding_rates: Optional[List[FundingRateData]] = None,
    ) -> Dict[str, Any]:
        """Validate downloaded data quality.

        Args:
            bars: List of BarData objects
            funding_rates: Optional list of FundingRateData objects

        Returns:
            Dictionary with validation results
        """
        results = {
            'bars': {
                'count': len(bars),
                'valid': True,
                'issues': [],
            },
            'funding_rates': {
                'count': len(funding_rates) if funding_rates else 0,
                'valid': True,
                'issues': [],
            },
        }

        # Validate bars
        if len(bars) < 2:
            results['bars']['valid'] = False
            results['bars']['issues'].append("Insufficient data (need at least 2 bars)")

        # Check for gaps in bars
        if len(bars) > 1:
            expected_interval = None
            for i in range(1, len(bars)):
                gap = bars[i].timestamp - bars[i-1].timestamp
                if expected_interval is None:
                    expected_interval = gap
                elif gap > expected_interval * 2:
                    results['bars']['issues'].append(
                        f"Large gap detected at {bars[i].timestamp}: {gap}"
                    )

        # Validate funding rates (every 8 hours expected)
        if funding_rates and len(funding_rates) > 1:
            for i in range(1, len(funding_rates)):
                gap = funding_rates[i].timestamp - funding_rates[i-1].timestamp
                if abs(gap.total_seconds() - 8 * 3600) > 3600:  # 1 hour tolerance
                    results['funding_rates']['issues'].append(
                        f"Unexpected gap at {funding_rates[i].timestamp}: {gap}"
                    )

        return results


def main():
    """Main entry point for the data download script."""
    parser = argparse.ArgumentParser(
        description="Download trading data (OHLCV and funding rates) from exchanges"
    )
    parser.add_argument(
        "--symbol",
        type=str,
        default="BTC/USDT",
        help="Trading pair symbol (default: BTC/USDT)",
    )
    parser.add_argument(
        "--timeframe",
        type=str,
        default="15m",
        help="OHLCV timeframe (default: 15m)",
    )
    parser.add_argument(
        "--exchange",
        type=str,
        default="binance",
        help="Exchange name (default: binance)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="Number of days to download (default: 30)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="data/trading_data",
        help="Output file path base (default: data/trading_data)",
    )
    parser.add_argument(
        "--format",
        type=str,
        choices=["csv", "json", "both"],
        default="csv",
        help="Output format (default: csv)",
    )
    parser.add_argument(
        "--no-funding",
        action="store_true",
        help="Skip downloading funding rates",
    )

    args = parser.parse_args()

    # Create output directory
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Initialize downloader
    downloader = DataDownloaderScript(exchange=args.exchange)

    # Download data
    bars = downloader.download_ohlcv(
        symbol=args.symbol,
        timeframe=args.timeframe,
        days=args.days,
    )

    funding_rates = None
    if not args.no_funding:
        funding_rates = downloader.download_funding_rates(
            symbol=args.symbol,
            days=args.days,
        )

    # Validate data
    print("\nValidating data...")
    validation = downloader.validate_data(bars, funding_rates)
    print(f"Bars: {validation['bars']['count']} records")
    if validation['bars']['issues']:
        print(f"  Issues: {validation['bars']['issues']}")
    print(f"Funding rates: {validation['funding_rates']['count']} records")
    if validation['funding_rates']['issues']:
        print(f"  Issues: {validation['funding_rates']['issues']}")

    # Save data
    print("\nSaving data...")
    if args.format in ["csv", "both"]:
        downloader.save_to_csv(bars, args.output, funding_rates)
    if args.format in ["json", "both"]:
        downloader.save_to_json(bars, args.output, funding_rates)

    print("\nDownload complete!")


if __name__ == "__main__":
    main()
