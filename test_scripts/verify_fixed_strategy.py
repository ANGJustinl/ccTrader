
#!/usr/bin/env python3
"""
Verify fixed DRAMM Strategy with adjusted thresholds.
验证修复后的策略是否能产生交易信号。
"""
import sys
from pathlib import Path
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Dict, Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.trader.application.strategies.dramm import (
    DRAMMStrategy,
    MarketRegime,
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


def main():
    print("="*80)
    print("DRAMM STRATEGY FIX VERIFICATION")
    print("="*80)
    
    # Download data
    print("\n[1/4] Downloading market data...")
    downloader = DataDownloader("binance")
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=30)
    since = int(start_date.timestamp() * 1000)
    
    bars = downloader.download_ohlcv("BTC/USDT", "15m", since)
    print(f"Downloaded {len(bars)} bars")
    
    if len(bars) == 0:
        print("No data available")
        return
    
    # Initialize strategy with FIXED threshold
    print("\n[2/4] Initializing strategy with entry_score_threshold=0.43...")
    strategy = DRAMMStrategy(
        entry_score_threshold=Decimal("0.43"),
        exit_score_threshold=Decimal("-0.4"),
    )
    
    # Track signals
    entry_signals = []
    exit_signals = []
    score_history = []
    regime_history = []
    
    print("\n[3/4] Processing bars through strategy...")
    
    for i, bar in enumerate(bars):
        strategy.bar_history.append(bar)
        
        if len(strategy.bar_history) > strategy.min_history + 50:
            strategy.bar_history.pop(0)
        
        strategy.streaming_adx.update(bar.high, bar.low, bar.close)
        strategy.streaming_bb.update(bar.close)
        
        if len(strategy.bar_history) >= strategy.min_history:
            strategy._identify_regime()
            
            # Calculate indicators
            closes = [b.close for b in strategy.bar_history]
            highs = [b.high for b in strategy.bar_history]
            lows = [b.low for b in strategy.bar_history]
            
            adx_results = calculate_adx(highs, lows, closes, strategy.adx_period)
            bb_results = calculate_bollinger_bands(closes, strategy.bollinger_period, strategy.bollinger_std)
            rsi_results = calculate_rsi(closes, strategy.rsi_period)
            zscore_results = calculate_zscore(closes, strategy.zscore_period)
            
            current_adx = adx_results[-1] if adx_results else None
            current_bb = bb_results[-1] if bb_results else None
            current_rsi = rsi_results[-1] if rsi_results else None
            current_zscore = zscore_results[-1] if zscore_results else None
            
            score = strategy._calculate_composite_score(
                current_adx, current_bb, current_rsi, current_zscore
            )
            
            # Record history
            score_history.append(float(score))
            regime_history.append(strategy.current_regime.value)
            
            # Check signals
            if score >= strategy.entry_score_threshold:
                entry_signals.append({
                    "index": i,
                    "timestamp": bar.timestamp,
                    "score": float(score),
                    "regime": strategy.current_regime.value,
                    "close": float(bar.close),
                })
            
            if score <= strategy.exit_score_threshold:
                exit_signals.append({
                    "index": i,
                    "timestamp": bar.timestamp,
                    "score": float(score),
                    "regime": strategy.current_regime.value,
                    "close": float(bar.close),
                })
    
    # Print results
    print("\n[4/4] Verification Results:")
    print("="*80)
    
    print(f"\nStrategy Configuration:")
    print(f"  entry_score_threshold: {strategy.entry_score_threshold}")
    print(f"  exit_score_threshold: {strategy.exit_score_threshold}")
    
    print(f"\nSignal Generation:")
    print(f"  Entry signals detected: {len(entry_signals)}")
    print(f"  Exit signals detected: {len(exit_signals)}")
    
    if score_history:
        import statistics
        print(f"\nScore Statistics:")
        print(f"  Min score: {min(score_history):.4f}")
        print(f"  Max score: {max(score_history):.4f}")
        print(f"  Mean score: {statistics.mean(score_history):.4f}")
        print(f"  Median score: {statistics.median(score_history):.4f}")
    
    if entry_signals:
        print(f"\nEntry Signal Samples (first 5):")
        for i, signal in enumerate(entry_signals[:5]):
            print(f"  {i+1}. Index={signal['index']}, Score={signal['score']:.4f}, "
                  f"Regime={signal['regime']}, Close={signal['close']:.2f}")
    
    # Regime distribution
    from collections import Counter
    regime_counts = Counter(regime_history)
    print(f"\nRegime Distribution:")
    for regime, count in regime_counts.items():
        print(f"  {regime.upper()}: {count} bars ({count/len(regime_history)*100:.1f}%)")
    
    print("\n" + "="*80)
    print("VERIFICATION COMPLETE")
    print("="*80)
    
    # Summary
    print("\nSUMMARY:")
    if len(entry_signals) > 0:
        print("  ✓ SUCCESS: Strategy generates entry signals with the new threshold!")
        print(f"  ✓ {len(entry_signals)} entry signals detected in the test period")
    else:
        print("  ✗ NO ENTRY SIGNALS DETECTED")
    
    if len(exit_signals) > 0:
        print(f"  ✓ {len(exit_signals)} exit signals detected")


if __name__ == "__main__":
    main()

