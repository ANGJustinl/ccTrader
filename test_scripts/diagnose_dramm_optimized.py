#!/usr/bin/env python3
"""Diagnostic script for DRAMM Strategy optimized parameters (Step 1-3).

This script validates all DRAMM optimization steps:
- Step 1: Re-centering (去偏) - Remove market trend bias from scores
- Step 2: Dynamic Thresholds - Adaptive entry/exit thresholds based on score quantiles
- Step 3: Regime Weights - Apply regime-specific multipliers to thresholds
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


class DRAMMOptimizedDiagnostic:
    """Diagnostic tool for DRAMM Strategy Strategy 1-3 optimization."""
    
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
        
        # DRAMM Optimized Strategy with Step 1-3 parameters
        self.strategy = DRAMMStrategy(
            # Base thresholds
            entry_score_threshold=Decimal("0.4"),
            exit_score_threshold=Decimal("-0.1"),
            # Step 1: Re-centering parameters
            score_ma_window=120,  # Moving average window for score de-biasing
            min_absolute_threshold=Decimal("0.2"),  # Hard minimum threshold
            # Step 2: Dynamic Thresholds parameters
            score_history_size=200,  # Score history window for dynamic thresholds
            entry_percentile=Decimal("0.9"),  # Top 10% quantile (90th percentile)
            exit_percentile=Decimal("0.1"),  # Bottom 10% quantile (10th percentile)
            # Step 3: Regime Weights parameters
            trend_entry_multiplier=Decimal("0.8"),  # Lower threshold, trend has momentum
            trend_exit_multiplier=Decimal("1.2"),  # Wider exit, let profits run
            chop_entry_multiplier=Decimal("1.2"),  # Higher threshold, many false signals
            chop_exit_multiplier=Decimal("0.8"),  # Tighter exit, take profit quick
            squeeze_time_confirm=2,  # Time confirmation, need 2 consecutive bars
            squeeze_extreme_percentile=Decimal("0.95"),  # Require extreme Top 5%
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
        print("\nCalculating composite scores with DRAMM optimizations...")
        
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
                
                # Calculate score (includes Step 1 re-centering and Step 2 dynamic thresholds)
                score = self.strategy._calculate_composite_score(
                    current_adx, current_bb, current_rsi, current_zscore
                )
                
                # Get internal variables for debugging
                raw_score = self.strategy._score_history[-1] if self.strategy._score_history else None
                score_ma = self.strategy._score_ma
                adjusted_score = self.strategy._adjusted_score
                dyn_entry_threshold = self.strategy._dynamic_entry_threshold
                dyn_exit_threshold = self.strategy._dynamic_exit_threshold
                
                # Record score data
                self.scores.append({
                    'timestamp': bar.timestamp,
                    'score': float(score),
                    'raw_score': float(raw_score) if raw_score else None,
                    'score_ma': float(score_ma) if score_ma else None,
                    'adjusted_score': float(adjusted_score) if adjusted_score else None,
                    'dyn_entry_threshold': float(dyn_entry_threshold) if dyn_entry_threshold else None,
                    'dyn_exit_threshold': float(dyn_exit_threshold) if dyn_exit_threshold else None,
                    'regime': self.strategy.current_regime.value,
                    'adx': float(current_adx.adx) if current_adx and current_adx.adx else None,
                    'bbw': float(current_bb.bandwidth) if current_bb and current_bb.bandwidth else None,
                    'rsi': float(current_rsi) if current_rsi else None,
                })
                
                if i % 100 == 0:
                    print(f"  Processed {i}/{len(self.bars)} bars...")
                    
        print(f"Recorded {len(self.scores)} valid score samples")
        
    def print_statistics(self) -> None:
        """Print detailed statistics about score distribution and DRAMM optimizations."""
        if not self.scores:
            print("No score data available")
            return
            
        print("\n" + "="*100)
        print("DRAMM STRATEGY OPTIMIZATION VALIDATION (Step 1-3)")
        print("="*100)
        
        # Extract score values
        score_values = [s['score'] for s in self.scores if s['score'] is not None]
        adjusted_scores = [s['adjusted_score'] for s in self.scores if s['adjusted_score'] is not None]
        raw_scores = [s['raw_score'] for s in self.scores if s['raw_score'] is not None]
        
        # ========== STEP 1: Re-centering (去偏) Analysis ==========
        print("\n" + "-"*100)
        print("STEP 1: Re-centering (去偏) Analysis")
        print("-"*100)
        
        print("\nRaw Score Statistics (Before Re-centering):")
        if raw_scores:
            print(f"  Mean: {statistics.mean(raw_scores):.4f}")
            print(f"  Median: {statistics.median(raw_scores):.4f}")
            if len(raw_scores) > 1:
                print(f"  Std Dev: {statistics.stdev(raw_scores):.4f}")
            print(f"  Min/Max: [{min(raw_scores):.4f}, {max(raw_scores):.4f}]")
        
        print("\nAdjusted Score Statistics (After Re-centering):")
        if adjusted_scores:
            print(f"  Mean: {statistics.mean(adjusted_scores):.4f}")
            print(f"  Median: {statistics.median(adjusted_scores):.4f}")
            if len(adjusted_scores) > 1:
                print(f"  Std Dev: {statistics.stdev(adjusted_scores):.4f}")
            print(f"  Min/Max: [{min(adjusted_scores):.4f}, {max(adjusted_scores):.4f}]")
            
            # Re-centering effectiveness
            mean_bias = abs(statistics.mean(adjusted_scores))
            median_bias = abs(statistics.median(adjusted_scores))
            print(f"\nRe-centering Effectiveness:")
            print(f"  Mean bias removal: {mean_bias:.4f} {'✓ PASS' if mean_bias < 0.05 else '✗ NEED REVIEW'}")
            print(f"  Median bias removal: {median_bias:.4f} {'✓ PASS' if median_bias < 0.05 else '✗ NEED REVIEW'}")
            
        # ========== STEP 2: Dynamic Thresholds Analysis ==========
        print("\n" + "-"*100)
        print("STEP 2: Dynamic Thresholds Analysis")
        print("-"*100)
        
        dyn_entry_thresholds = [s['dyn_entry_threshold'] for s in self.scores if s['dyn_entry_threshold'] is not None]
        dyn_exit_thresholds = [s['dyn_exit_threshold'] for s in self.scores if s['dyn_exit_threshold'] is not None]
        
        if dyn_entry_thresholds:
            print(f"\nDynamic Entry Threshold (Top 10% quantile):")
            print(f"  Min: {min(dyn_entry_thresholds):.4f}")
            print(f"  Max: {max(dyn_entry_thresholds):.4f}")
            print(f"  Mean: {statistics.mean(dyn_entry_thresholds):.4f}")
            if len(dyn_entry_thresholds) > 1:
                print(f"  Std Dev: {statistics.stdev(dyn_entry_thresholds):.4f}")
            
        if dyn_exit_thresholds:
            print(f"\nDynamic Exit Threshold (Bottom 10% quantile):")
            print(f"  Min: {min(dyn_exit_thresholds):.4f}")
            print(f"  Max: {max(dyn_exit_thresholds):.4f}")
            print(f"  Mean: {statistics.mean(dyn_exit_thresholds):.4f}")
            if len(dyn_exit_thresholds) > 1:
                print(f"  Std Dev: {statistics.stdev(dyn_exit_thresholds):.4f}")
            
        # Hard minimum threshold analysis
        print(f"\nHard Minimum Threshold (min_absolute_threshold=0.2):")
        below_threshold = sum(1 for s in self.scores if s['score'] is not None and abs(s['score']) < 0.2)
        print(f"  Scores below 0.2: {below_threshold} ({below_threshold/len(self.scores)*100:.2f}%)")
        print(f"  Hard threshold working: {'✓ PASS' if below_threshold > 0 else '✗ NO FILTERING'}")
        
        # ========== STEP 3: Regime Weights Analysis ==========
        print("\n" + "-"*100)
        print("STEP 3: Regime Weights Analysis")
        print("-"*100)
        
        # Regime distribution
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
            print(f"  {regime.upper()}: {count} bars ({count/len(self.scores)*100:.2f}%)")
            print(f"    Avg score: {avg_score:.4f}, Range: [{min_score:.4f} to {max_score:.4f}]")
            
        # Regime-specific entry/exit analysis
        print(f"\nRegime-Specific Multipliers:")
        print(f"  TREND: Entry={self.strategy.trend_entry_multiplier:.2f}, Exit={self.strategy.trend_exit_multiplier:.2f}")
        print(f"  CHOP:  Entry={self.strategy.chop_entry_multiplier:.2f}, Exit={self.strategy.chop_exit_multiplier:.2f}")
        print(f"  SQUEEZE: TimeConfirm={self.strategy.squeeze_time_confirm}, ExtremePct={self.strategy.squeeze_extreme_percentile:.2%}")
        
        # Entry signal analysis by regime
        print(f"\nEntry Signal Analysis by Regime:")
        for regime in ['trend', 'chop', 'squeeze']:
            entry_mult = float(self.strategy.trend_entry_multiplier if regime == 'trend' else
                              self.strategy.chop_entry_multiplier if regime == 'chop' else 1.0)
            regime_entries = sum(1 for s in self.scores
                               if s['regime'] == regime and s['score'] is not None
                               and s['dyn_entry_threshold'] is not None
                               and s['score'] >= s['dyn_entry_threshold'] * entry_mult)
            total = regime_counts.get(regime, 0)
            if total > 0:
                print(f"  {regime.upper()}: {regime_entries} potential entries ({regime_entries/total*100:.2f}% of bars)")
        
        # ========== Overall Analysis ==========
        print("\n" + "-"*100)
        print("OVERALL ANALYSIS")
        print("-"*100)
        
        print(f"\nKey Metrics:")
        print(f"  Total bars analyzed: {len(self.scores)}")
        print(f"  Symbol/Timeframe: {self.symbol} {self.timeframe}")
        
        # SQUEEZE ratio analysis
        squeeze_count = regime_counts.get('squeeze', 0)
        print(f"\n  SQUEEZE regime ratio: {squeeze_count}/{len(self.scores)} ({squeeze_count/len(self.scores)*100:.2f}%)")
        print(f"  {'✓ REASONABLE' if 5 <= squeeze_count/len(self.scores)*100 <= 25 else '⚠ CHECK'}")
        
        # Parameter summary
        print(f"\nStrategy Parameter Summary:")
        print(f"  score_ma_window: {self.strategy.score_ma_window}")
        print(f"  min_absolute_threshold: {self.strategy.min_absolute_threshold}")
        print(f"  score_history_size: {self.strategy.score_history_size}")
        print(f"  entry_percentile: {self.strategy.entry_percentile}")
        print(f"  exit_percentile: {self.strategy.exit_percentile}")
        print(f"  trend_entry_multiplier: {self.strategy.trend_entry_multiplier}")
        print(f"  trend_exit_multiplier: {self.strategy.trend_exit_multiplier}")
        print(f"  chop_entry_multiplier: {self.strategy.chop_entry_multiplier}")
        print(f"  chop_exit_multiplier: {self.strategy.chop_exit_multiplier}")
        print(f"  squeeze_time_confirm: {self.strategy.squeeze_time_confirm}")
        print(f"  squeeze_extreme_percentile: {self.strategy.squeeze_extreme_percentile}")
        
        print("\n" + "="*100)
        
    def save_results(self, output_file: str = "dramm_optimized_diagnostic_results.txt") -> None:
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
    print("DRAMM Strategy Optimized Validation (Step 1-3)")
    print("="*100)
    
    # Initialize diagnostic
    diagnostic = DRAMMOptimizedDiagnostic(
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
