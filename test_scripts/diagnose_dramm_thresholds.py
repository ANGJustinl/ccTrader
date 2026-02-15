
#!/usr/bin/env python3
"""Diagnostic script for DRAMM Strategy threshold analysis.

This script analyzes the composite score distribution of the DRAMM Strategy
using real Binance historical data to identify if the threshold settings are too strict.
"""
import sys
from pathlib import Path
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Dict, Any
import statistics
from collections import defaultdict

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.trader.application.strategies.dramm import (
    DRAMMStrategy,
    MarketRegime,
    RegimeWeights,
)
from src.trader.infrastructure.data_repository import BarData
from src.trader.infrastructure.data_downloader import DataDownloader
from src.trader.utils.indicators import (
    calculate_adx,
    calculate_bollinger_bands,
    calculate_rsi,
    calculate_atr,
    calculate_zscore,
)


class DRAMMDiagnostic:
    """Diagnostic tool for DRAMM Strategy."""
    
    def __init__(
        self,
        symbol: str = "BTC/USDT",
        timeframe: str = "15m",
        days: int = 30,
    ):
        """Initialize diagnostic tool.
        
        Args:
            symbol: Trading pair symbol
            timeframe: OHLCV timeframe
            days: Number of days of historical data to use
        """
        self.symbol = symbol
        self.timeframe = timeframe
        self.days = days
        self.bars: List[BarData] = []
        self.scores: List[Dict[str, Any]] = []
        # Optimized parameters after deep analysis:
        # - entry_threshold: 0.6 -> 0.4 (Top ~10% opportunities, more active entries)
        # - exit_threshold: -0.4 -> -0.1 (Exit when returning to neutral, quicker exits)
        self.strategy = DRAMMStrategy(
            entry_score_threshold=Decimal("0.4"),
            exit_score_threshold=Decimal("-0.1"),
        )
        
    def download_data(self) -> None:
        """Download historical data from Binance."""
        print(f"Downloading {self.symbol} {self.timeframe} data for {self.days} days...")
        downloader = DataDownloader("binance")
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=self.days)
        since = int(start_date.timestamp() * 1000)
        
        self.bars = downloader.download_ohlcv(self.symbol, self.timeframe, since)
        print(f"Downloaded {len(self.bars)} bars")
        
    def analyze_scores(self) -> None:
        """Calculate and analyze composite scores for all bars."""
        print("\nCalculating composite scores...")
        
        # Process bars through strategy (without executing trades)
        for i, bar in enumerate(self.bars):
            # Add bar to history without calling on_bar (which tries to trade)
            self.strategy.bar_history.append(bar)
            
            # Keep sufficient history
            if len(self.strategy.bar_history) > self.strategy.min_history + 50:
                self.strategy.bar_history.pop(0)
                
            # Update streaming indicators
            self.strategy.streaming_adx.update(bar.high, bar.low, bar.close)
            self.strategy.streaming_bb.update(bar.close)
            
            # Identify regime
            if len(self.strategy.bar_history) >= self.strategy.min_history:
                self.strategy._identify_regime()
            
            # Only record scores after we have enough history
            if len(self.strategy.bar_history) >= self.strategy.min_history:
                # Get current indicators
                closes = [b.close for b in self.strategy.bar_history]
                highs = [b.high for b in self.strategy.bar_history]
                lows = [b.low for b in self.strategy.bar_history]
                
                adx_results = calculate_adx(
                    highs, lows, closes, self.strategy.adx_period
                )
                bb_results = calculate_bollinger_bands(
                    closes, self.strategy.bollinger_period, self.strategy.bollinger_std
                )
                rsi_results = calculate_rsi(closes, self.strategy.rsi_period)
                zscore_results = calculate_zscore(closes, self.strategy.zscore_period)
                
                current_adx = adx_results[-1] if adx_results else None
                current_bb = bb_results[-1] if bb_results else None
                current_rsi = rsi_results[-1] if rsi_results else None
                current_zscore = zscore_results[-1] if zscore_results else None
                
                # Calculate score
                score = self.strategy._calculate_composite_score(
                    current_adx, current_bb, current_rsi, current_zscore
                )
                
                # Record score data
                self.scores.append({
                    'timestamp': bar.timestamp,
                    'score': float(score),
                    'regime': self.strategy.current_regime.value,
                    'adx': float(current_adx.adx) if current_adx and current_adx.adx else None,
                    'bbw': float(current_bb.bandwidth) if current_bb and current_bb.bandwidth else None,
                    'rsi': float(current_rsi) if current_rsi else None,
                })
                
                if i % 100 == 0:
                    print(f"  Processed {i}/{len(self.bars)} bars...")
                    
        print(f"Recorded {len(self.scores)} valid score samples")
        
    def print_statistics(self) -> None:
        """Print detailed statistics about score distribution."""
        if not self.scores:
            print("No score data available")
            return
            
        print("\n" + "="*80)
        print("DRAMM STRATEGY SCORE DISTRIBUTION ANALYSIS")
        print("="*80)
        
        # Extract score values
        score_values = [s['score'] for s in self.scores]
        
        # Basic statistics
        print(f"\nBasic Statistics:")
        print(f"  Total samples: {len(score_values)}")
        print(f"  Min score: {min(score_values):.4f}")
        print(f"  Max score: {max(score_values):.4f}")
        print(f"  Mean score: {statistics.mean(score_values):.4f}")
        print(f"  Median score: {statistics.median(score_values):.4f}")
        if len(score_values) > 1:
            print(f"  Std dev: {statistics.stdev(score_values):.4f}")
        
        # Percentiles
        print(f"\nPercentiles:")
        sorted_scores = sorted(score_values)
        percentiles = [10, 25, 50, 75, 90, 95, 99]
        for p in percentiles:
            idx = int(len(sorted_scores) * p / 100)
            print(f"  {p}th percentile: {sorted_scores[idx]:.4f}")
        
        # Threshold analysis
        print(f"\nThreshold Analysis (current entry_threshold=0.6, exit_threshold=-0.4):")
        
        entry_threshold = 0.6
        exit_threshold = -0.4
        
        above_entry = sum(1 for s in score_values if s >= entry_threshold)
        below_exit = sum(1 for s in score_values if s <= exit_threshold)
        between = sum(1 for s in score_values if exit_threshold < s < entry_threshold)
        
        print(f"  Scores >= {entry_threshold} (entry): {above_entry} bars ({above_entry/len(score_values)*100:.2f}%)")
        print(f"  Scores <= {exit_threshold} (exit): {below_exit} bars ({below_exit/len(score_values)*100:.2f}%)")
        print(f"  Scores in between: {between} bars ({between/len(score_values)*100:.2f}%)")
        
        # Suggest alternative thresholds
        print(f"\nAlternative Threshold Suggestions:")
        target_percentiles = [5, 10, 15, 20]
        print(f"  Entry thresholds (top X%):")
        for p in target_percentiles:
            idx = int(len(sorted_scores) * (100 - p) / 100)
            threshold = sorted_scores[idx]
            count = sum(1 for s in score_values if s >= threshold)
            print(f"    Top {p}%: {threshold:.4f} ({count} bars)")
            
        print(f"\n  Exit thresholds (bottom X%):")
        for p in target_percentiles:
            idx = int(len(sorted_scores) * p / 100)
            threshold = sorted_scores[idx]
            count = sum(1 for s in score_values if s <= threshold)
            print(f"    Bottom {p}%: {threshold:.4f} ({count} bars)")
            
        # Regime analysis
        print(f"\nRegime Distribution:")
        regime_counts = defaultdict(int)
        regime_scores = defaultdict(list)
        for s in self.scores:
            regime = s['regime']
            regime_counts[regime] += 1
            regime_scores[regime].append(s['score'])
            
        for regime, count in regime_counts.items():
            avg_score = statistics.mean(regime_scores[regime])
            max_score = max(regime_scores[regime])
            min_score = min(regime_scores[regime])
            print(f"  {regime.upper()}: {count} bars")
            print(f"    Avg score: {avg_score:.4f}, Range: [{min_score:.4f} to {max_score:.4f}")
            
        # Parameter analysis
        print(f"\nStrategy Parameter Settings:")
        print(f"  entry_score_threshold: {self.strategy.entry_score_threshold}")
        print(f"  exit_score_threshold: {self.strategy.exit_score_threshold}")
        print(f"  ADX_TREND_THRESHOLD: {self.strategy.ADX_TREND_THRESHOLD}")
        print(f"  ADX_CHOP_THRESHOLD: {self.strategy.ADX_CHOP_THRESHOLD}")
        print(f"  BBW_SQUEEZE_QUANTILE: {self.strategy.BBW_SQUEEZE_QUANTILE}")
        print(f"  BBW_HISTORY_PERIOD: {self.strategy.BBW_HISTORY_PERIOD}")
        
        print("\n" + "="*80)
        
    def save_results(self, output_file: str = "dramm_diagnostic_results.txt") -> None:
        """Save diagnostic results to a file."""
        import sys
        original_stdout = sys.stdout
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                sys.stdout = f
                self.print_statistics()
            sys.stdout = original_stdout
            print(f"\nResults saved to: {output_file}")
        finally:
            sys.stdout = original_stdout


def main():
    """Main entry point."""
    print("DRAMM Strategy Threshold Diagnostic")
    print("="*80)
    
    # Initialize diagnostic
    diagnostic = DRAMMDiagnostic(
        symbol="BTC/USDT",
        timeframe="15m",
        days=30,
    )
    
    # Download data
    diagnostic.download_data()
    
    if len(diagnostic.bars) == 0:
        print("No data downloaded. Exiting.")
        return
        
    # Analyze
    diagnostic.analyze_scores()
    
    # Print and save results
    diagnostic.print_statistics()
    diagnostic.save_results()
    
    print("\nDiagnostic complete!")


if __name__ == "__main__":
    main()

