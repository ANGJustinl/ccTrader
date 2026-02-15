
#!/usr/bin/env python3
"""
Complete DRAMM Strategy Debugging Script
涵盖调试 2-5 全部任务
"""
import sys
from pathlib import Path
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Dict, Any, Tuple
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
    ADXResult,
    BollingerBandsResult,
)


class DRAMMCompleteDebugger:
    """Complete DRAMM debugger covering tasks 2-5."""
    
    def __init__(
        self,
        symbol: str = "BTC/USDT",
        timeframe: str = "15m",
        days: int = 30,
    ):
        self.symbol = symbol
        self.timeframe = timeframe
        self.days = days
        self.bars: List[BarData] = []
        self.debug_results: Dict[str, Any] = {}
        
        self.strategy = DRAMMStrategy(
            entry_score_threshold=Decimal("0.6"),
            exit_score_threshold=Decimal("-0.4"),
        )
    
    def download_data(self) -> None:
        """Download historical data from Binance."""
        print(f"[Debug 2] Downloading {self.symbol} {self.timeframe} data...")
        downloader = DataDownloader("binance")
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=self.days)
        since = int(start_date.timestamp() * 1000)
        
        self.bars = downloader.download_ohlcv(self.symbol, self.timeframe, since)
        print(f"[Debug 2] Downloaded {len(self.bars)} bars")
    
    def debug_2_market_data(self) -> Dict[str, Any]:
        """
        Debug 2: Verify market data granularity/completeness/accuracy
        """
        print("\n" + "="*80)
        print("DEBUG 2: MARKET DATA VALIDATION")
        print("="*80)
        
        results = {
            "total_bars": len(self.bars),
            "granularity_check": {},
            "completeness_check": {},
            "accuracy_check": {},
        }
        
        if not self.bars:
            print("[Debug 2] No data to validate")
            return results
        
        # Granularity check
        print("\n[Debug 2] Checking granularity...")
        timestamps = [bar.timestamp for bar in self.bars]
        expected_interval = 15 * 60 * 1000  # 15 minutes in ms
        
        intervals = []
        for i in range(1, len(timestamps)):
            intervals.append(timestamps[i] - timestamps[i-1])
        
        avg_interval = statistics.mean(intervals) if intervals else 0
        min_interval = min(intervals) if intervals else 0
        max_interval = max(intervals) if intervals else 0
        
        results["granularity_check"] = {
            "expected_interval_ms": expected_interval,
            "avg_interval_ms": avg_interval,
            "min_interval_ms": min_interval,
            "max_interval_ms": max_interval,
            "interval_consistent": all(abs(iv - expected_interval) < 60000 for iv in intervals),
        }
        
        print(f"  Expected interval: {expected_interval}ms")
        print(f"  Average interval: {avg_interval:.2f}ms")
        print(f"  Min interval: {min_interval}ms")
        print(f"  Max interval: {max_interval}ms")
        print(f"  Intervals consistent: {results['granularity_check']['interval_consistent']}")
        
        # Completeness check
        print("\n[Debug 2] Checking completeness...")
        start_time = datetime.fromtimestamp(timestamps[0] / 1000)
        end_time = datetime.fromtimestamp(timestamps[-1] / 1000)
        total_duration = end_time - start_time
        expected_bars = int(total_duration.total_seconds() / (15 * 60)) + 1
        
        results["completeness_check"] = {
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "duration_days": total_duration.total_seconds() / 86400,
            "expected_bars": expected_bars,
            "actual_bars": len(self.bars),
            "completeness_ratio": len(self.bars) / expected_bars if expected_bars > 0 else 0,
            "missing_bars": expected_bars - len(self.bars),
        }
        
        print(f"  Time range: {start_time} to {end_time}")
        print(f"  Duration: {total_duration.days} days")
        print(f"  Expected bars: {expected_bars}")
        print(f"  Actual bars: {len(self.bars)}")
        print(f"  Completeness ratio: {results['completeness_check']['completeness_ratio']:.2%}")
        print(f"  Missing bars: {results['completeness_check']['missing_bars']}")
        
        # Accuracy check
        print("\n[Debug 2] Checking data accuracy...")
        valid_bars = 0
        invalid_bars = []
        
        for i, bar in enumerate(self.bars):
            valid = True
            if not (bar.low <= bar.open <= bar.high and bar.low <= bar.close <= bar.high):
                valid = False
                invalid_bars.append((i, "Price logic invalid"))
            if bar.volume <= 0:
                valid = False
                invalid_bars.append((i, "Volume <= 0"))
            if valid:
                valid_bars += 1
        
        results["accuracy_check"] = {
            "valid_bars": valid_bars,
            "invalid_bars_count": len(invalid_bars),
            "accuracy_ratio": valid_bars / len(self.bars),
            "sample_invalid_bars": invalid_bars[:5],
        }
        
        print(f"  Valid bars: {valid_bars}/{len(self.bars)}")
        print(f"  Accuracy ratio: {results['accuracy_check']['accuracy_ratio']:.2%}")
        if invalid_bars:
            print(f"  Invalid bars sample: {invalid_bars[:5]}")
        
        self.debug_results["debug_2"] = results
        return results
    
    def debug_3_regime_signal_integration(self) -> Dict[str, Any]:
        """
        Debug 3: Troubleshoot regime identification and signal trigger logic integration
        """
        print("\n" + "="*80)
        print("DEBUG 3: REGIME & SIGNAL INTEGRATION")
        print("="*80)
        
        results = {
            "regime_transitions": [],
            "regime_duration": defaultdict(list),
            "signal_timing": [],
            "regime_signal_alignment": defaultdict(int),
        }
        
        if len(self.bars) < self.strategy.min_history:
            print("[Debug 3] Not enough data for analysis")
            return results
        
        print("\n[Debug 3] Processing bars through strategy...")
        
        prev_regime = MarketRegime.UNKNOWN
        regime_start_idx = 0
        
        for i, bar in enumerate(self.bars):
            self.strategy.bar_history.append(bar)
            
            if len(self.strategy.bar_history) > self.strategy.min_history + 50:
                self.strategy.bar_history.pop(0)
            
            self.strategy.streaming_adx.update(bar.high, bar.low, bar.close)
            self.strategy.streaming_bb.update(bar.close)
            
            if len(self.strategy.bar_history) >= self.strategy.min_history:
                self.strategy._identify_regime()
                
                # Track regime transitions
                if self.strategy.current_regime != prev_regime:
                    if prev_regime != MarketRegime.UNKNOWN:
                        duration = i - regime_start_idx
                        results["regime_duration"][prev_regime.value].append(duration)
                    
                    results["regime_transitions"].append({
                        "index": i,
                        "timestamp": bar.timestamp,
                        "from": prev_regime.value,
                        "to": self.strategy.current_regime.value,
                    })
                    
                    prev_regime = self.strategy.current_regime
                    regime_start_idx = i
                
                # Calculate composite score
                closes = [b.close for b in self.strategy.bar_history]
                highs = [b.high for b in self.strategy.bar_history]
                lows = [b.low for b in self.strategy.bar_history]
                
                adx_results = calculate_adx(highs, lows, closes, self.strategy.adx_period)
                bb_results = calculate_bollinger_bands(closes, self.strategy.bollinger_period, self.strategy.bollinger_std)
                rsi_results = calculate_rsi(closes, self.strategy.rsi_period)
                zscore_results = calculate_zscore(closes, self.strategy.zscore_period)
                
                current_adx = adx_results[-1] if adx_results else None
                current_bb = bb_results[-1] if bb_results else None
                current_rsi = rsi_results[-1] if rsi_results else None
                current_zscore = zscore_results[-1] if zscore_results else None
                
                score = self.strategy._calculate_composite_score(
                    current_adx, current_bb, current_rsi, current_zscore
                )
                
                # Track signal timing relative to regime
                if score >= self.strategy.entry_score_threshold:
                    results["signal_timing"].append({
                        "index": i,
                        "regime": self.strategy.current_regime.value,
                        "score": float(score),
                    })
                    results["regime_signal_alignment"][self.strategy.current_regime.value] += 1
        
        # Record final regime duration
        if prev_regime != MarketRegime.UNKNOWN:
            duration = len(self.bars) - regime_start_idx
            results["regime_duration"][prev_regime.value].append(duration)
        
        # Print results
        print(f"\n  Regime transitions: {len(results['regime_transitions'])}")
        for transition in results["regime_transitions"][:5]:
            print(f"    {transition['from']} -> {transition['to']} at index {transition['index']}")
        
        print(f"\n  Regime durations (bars):")
        for regime, durations in results["regime_duration"].items():
            avg_dur = statistics.mean(durations) if durations else 0
            print(f"    {regime.upper()}: avg={avg_dur:.1f} bars, {len(durations)} periods")
        
        print(f"\n  Signal-regime alignment:")
        for regime, count in results["regime_signal_alignment"].items():
            print(f"    {regime.upper()}: {count} entry signals")
        
        self.debug_results["debug_3"] = results
        return results
    
    def debug_4_indicator_calculation(self) -> Dict[str, Any]:
        """
        Debug 4: Verify indicator calculation results match expectations
        """
        print("\n" + "="*80)
        print("DEBUG 4: INDICATOR CALCULATION VERIFICATION")
        print("="*80)
        
        results = {
            "adx_validation": {},
            "bb_validation": {},
            "rsi_validation": {},
            "atr_validation": {},
            "zscore_validation": {},
            "sample_values": [],
        }
        
        if len(self.bars) < self.strategy.min_history:
            print("[Debug 4] Not enough data for verification")
            return results
        
        closes = [b.close for b in self.bars]
        highs = [b.high for b in self.bars]
        lows = [b.low for b in self.bars]
        
        print("\n[Debug 4] Calculating indicators...")
        
        # Calculate indicators
        adx_results = calculate_adx(highs, lows, closes, self.strategy.adx_period)
        bb_results = calculate_bollinger_bands(closes, self.strategy.bollinger_period, self.strategy.bollinger_std)
        rsi_results = calculate_rsi(closes, self.strategy.rsi_period)
        atr_results = calculate_atr(highs, lows, closes, self.strategy.atr_period)
        zscore_results = calculate_zscore(closes, self.strategy.zscore_period)
        
        # Validate ranges
        print("\n[Debug 4] Validating indicator ranges...")
        
        # ADX validation
        adx_values = [r.adx for r in adx_results if r and r.adx is not None]
        if adx_values:
            results["adx_validation"] = {
                "min": float(min(adx_values)),
                "max": float(max(adx_values)),
                "avg": float(statistics.mean(adx_values)),
                "in_range": all(0 <= v <= 100 for v in adx_values),
            }
            print(f"  ADX: min={results['adx_validation']['min']:.2f}, max={results['adx_validation']['max']:.2f}")
            print(f"  ADX in expected range [0, 100]: {results['adx_validation']['in_range']}")
        
        # RSI validation
        rsi_values = [r for r in rsi_results if r is not None]
        if rsi_values:
            results["rsi_validation"] = {
                "min": float(min(rsi_values)),
                "max": float(max(rsi_values)),
                "avg": float(statistics.mean(rsi_values)),
                "in_range": all(0 <= v <= 100 for v in rsi_values),
            }
            print(f"  RSI: min={results['rsi_validation']['min']:.2f}, max={results['rsi_validation']['max']:.2f}")
            print(f"  RSI in expected range [0, 100]: {results['rsi_validation']['in_range']}")
        
        # Bollinger Bands validation
        bb_values = [r for r in bb_results if r and r.middle is not None]
        if bb_values:
            valid_bb = all(
                r.lower <= r.middle <= r.upper 
                for r in bb_values 
                if r and r.lower and r.middle and r.upper
            )
            results["bb_validation"] = {
                "valid_order": valid_bb,
                "sample_count": len(bb_values),
            }
            print(f"  Bollinger Bands order valid: {valid_bb}")
        
        # ATR validation
        atr_values = [r for r in atr_results if r is not None]
        if atr_values:
            results["atr_validation"] = {
                "min": float(min(atr_values)),
                "max": float(max(atr_values)),
                "avg": float(statistics.mean(atr_values)),
                "positive": all(v > 0 for v in atr_values),
            }
            print(f"  ATR: min={results['atr_validation']['min']:.4f}, max={results['atr_validation']['max']:.4f}")
            print(f"  ATR always positive: {results['atr_validation']['positive']}")
        
        # Z-Score validation
        zscore_values = [r for r in zscore_results if r is not None]
        if zscore_values:
            results["zscore_validation"] = {
                "min": float(min(zscore_values)),
                "max": float(max(zscore_values)),
                "avg": float(statistics.mean(zscore_values)),
            }
            print(f"  Z-Score: min={results['zscore_validation']['min']:.2f}, max={results['zscore_validation']['max']:.2f}")
        
        # Sample values
        print("\n[Debug 4] Sample indicator values (last 5 bars):")
        sample_start = max(0, len(adx_results) - 5)
        for i in range(sample_start, len(adx_results)):
            adx = adx_results[i] if i < len(adx_results) else None
            bb = bb_results[i] if i < len(bb_results) else None
            rsi = rsi_results[i] if i < len(rsi_results) else None
            atr = atr_results[i] if i < len(atr_results) else None
            zscore = zscore_results[i] if i < len(zscore_results) else None
            
            sample = {
