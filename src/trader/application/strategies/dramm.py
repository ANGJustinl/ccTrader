"""DRAMM (Dynamic Regime Adaptive Multi-Factor Model) Strategy.

A regime-based adaptive trading strategy that:
1. Identifies market regimes (Trend, Chop, Squeeze)
2. Adjusts factor weights dynamically based on regime
3. Uses multi-factor scoring for entry/exit decisions
4. Implements ATR-based dynamic stop loss
5. Filters trades based on funding rates
"""
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import List, Dict, Optional
from pydantic import BaseModel, Field
from ..strategy import BaseStrategy
from ...infrastructure.data_repository import BarData
from ...utils.indicators import (
    calculate_adx,
    calculate_atr,
    calculate_bollinger_bands,
    calculate_rsi,
    calculate_zscore,
    BollingerBandsResult,
    ADXResult,
    StreamingADX,
    StreamingBollingerBands,
)
from ..order import Order


class MarketRegime(StrEnum):
    """Market regime classification."""
    TREND = "trend"           # Strong trend (ADX > 25)
    CHOP = "chop"             # Sideways/choppy (ADX < 20, BBW moderate)
    SQUEEZE = "squeeze"       # Low volatility compression (BBW low)
    UNKNOWN = "unknown"       # Insufficient data or transitioning


class RegimeWeights(BaseModel):
    """Factor weights for different market regimes."""
    trend_factor: Decimal = Field(default=Decimal("0.4"), description="Trend factor weight")
    momentum_factor: Decimal = Field(default=Decimal("0.3"), description="Momentum factor weight")
    volatility_factor: Decimal = Field(default=Decimal("0.2"), description="Volatility factor weight")
    microstructure_factor: Decimal = Field(default=Decimal("0.1"), description="Microstructure factor weight")


class DRAMMStrategy(BaseStrategy):
    """DRAMM (Dynamic Regime Adaptive Multi-Factor Model) Strategy.

    Strategy Steps:
    1. Regime Identification: Classify market as Trend/Chop/Squeeze
    2. Dynamic Weighting: Adjust factor weights based on regime
    3. Multi-Factor Scoring: Calculate composite score for entry/exit
    4. Risk Management: ATR-based Chandelier Exit stop loss
    5. Funding Filter: Avoid unfavorable funding rate environments
    
    DRAMM Optimization Steps:
    Step 1: Re-centering (去偏) - Remove market trend bias from scores
    Step 2: Dynamic Thresholds - Adaptive entry/exit thresholds based on score quantiles
    """

    # Regime configuration
    ADX_TREND_THRESHOLD = Decimal("25")       # Reverted to 25 to target strong trends only
    ADX_CHOP_THRESHOLD = Decimal("20")        # Reverted to 20
    # BBW_SQUEEZE_THRESHOLD removed - using dynamic quantile-based detection
    
    # Dynamic regime identification configuration
    BBW_HISTORY_PERIOD = 20  # Days to look back for BBW quantile calculation
    BBW_SQUEEZE_QUANTILE = 0.1  # Bottom 10% quantile for Squeeze detection

    # Default factor weights by regime
    REGIME_WEIGHTS = {
        MarketRegime.TREND: RegimeWeights(
            trend_factor=Decimal("0.5"),
            momentum_factor=Decimal("0.3"),
            volatility_factor=Decimal("0.15"),
            microstructure_factor=Decimal("0.05"),
        ),
        MarketRegime.CHOP: RegimeWeights(
            trend_factor=Decimal("0.15"),
            momentum_factor=Decimal("0.25"),
            volatility_factor=Decimal("0.4"),
            microstructure_factor=Decimal("0.2"),
        ),
        MarketRegime.SQUEEZE: RegimeWeights(
            trend_factor=Decimal("0.1"),
            momentum_factor=Decimal("0.2"),
            volatility_factor=Decimal("0.5"),
            microstructure_factor=Decimal("0.2"),
        ),
    }

    def __init__(
        self,
        adx_period: int = 14,
        bollinger_period: int = 20,
        bollinger_std: Decimal = Decimal("2"),
        rsi_period: int = 14,
        atr_period: int = 14,
        zscore_period: int = 20,
        position_size: float = 0.01,
        atr_multiplier: Decimal = Decimal("2.5"),  # Optimized: Increased from 2.0 to 2.5 for breathing room
        # Rebalanced thresholds based on deep analysis:
        # - entry_threshold: 0.55 (Moderate conviction, balanced)
        # - exit_threshold: -0.5 (Force trend holding)
        entry_score_threshold: Decimal = Decimal("0.55"),
        exit_score_threshold: Decimal = Decimal("-0.5"),
        # DRAMM Step 1: Re-centering parameters
        score_ma_window: int = 120,  # Optimized: Increased back to 120 (30h) to hold trend scores longer
        min_absolute_threshold: Decimal = Decimal("0.25"),  # Adjusted: Lowered to 0.25 to catch easier entries
        # DRAMM Step 2: Dynamic Thresholds parameters
        score_history_size: int = 100,  # Reduced from 200 to 100 (more responsive)
        entry_percentile: Decimal = Decimal("0.85"),  # Adjusted from 0.9 to 0.85
        exit_percentile: Decimal = Decimal("0.15"),  # Adjusted from 0.1 to 0.15
        # DRAMM Step 3: Regime Weights parameters
        trend_entry_multiplier: Decimal = Decimal("0.8"),  # Lower threshold, trend has momentum
        trend_exit_multiplier: Decimal = Decimal("1.2"),  # Wider exit, let profits run
        chop_entry_multiplier: Decimal = Decimal("1.2"),  # Higher threshold, many false signals
        chop_exit_multiplier: Decimal = Decimal("0.8"),  # Tighter exit, take profit quick
        squeeze_time_confirm: int = 2,  # Time confirmation, need 2 consecutive bars
        squeeze_extreme_percentile: Decimal = Decimal("0.95"),  # Require extreme Top 5%
        min_funding_rate: Optional[Decimal] = None,
        max_funding_rate: Optional[Decimal] = None,
        min_atr_percent: Decimal = Decimal("0.0025"),  # Optimized: Balanced at 0.25%
        use_percentage_position_size: bool = False,  # Whether to use percentage-based position sizing
    ):
        super().__init__("DRAMM")
        self.adx_period = adx_period
        self.bollinger_period = bollinger_period
        self.bollinger_std = bollinger_std
        self.rsi_period = rsi_period
        self.atr_period = atr_period
        self.zscore_period = zscore_period
        self.position_size = position_size
        self.use_percentage_position_size = use_percentage_position_size
        self.atr_multiplier = atr_multiplier
        self.entry_score_threshold = entry_score_threshold
        self.exit_score_threshold = exit_score_threshold
        self.min_funding_rate = min_funding_rate
        self.max_funding_rate = max_funding_rate
        self.min_atr_percent = min_atr_percent
        self.score_ma_window = score_ma_window
        self.min_absolute_threshold = min_absolute_threshold
        # DRAMM Step 2: Dynamic Thresholds parameters
        self.score_history_size = score_history_size
        self.entry_percentile = entry_percentile
        self.exit_percentile = exit_percentile
        # DRAMM Step 3: Regime Weights parameters
        self.trend_entry_multiplier = trend_entry_multiplier
        self.trend_exit_multiplier = trend_exit_multiplier
        self.chop_entry_multiplier = chop_entry_multiplier
        self.chop_exit_multiplier = chop_exit_multiplier
        self.squeeze_time_confirm = squeeze_time_confirm
        self.squeeze_extreme_percentile = squeeze_extreme_percentile

        # Data storage
        self.bar_history: List[BarData] = []
        self.current_regime: MarketRegime = MarketRegime.UNKNOWN
        self.current_funding_rate: Optional[Decimal] = None
        self.entry_price: Optional[Decimal] = None

        # DRAMM Step 1: Re-centering variables
        self._score_history: List[Decimal] = []  # Historical adjusted scores (after de-biasing)
        self._adjusted_score_history: List[Decimal] = []  # For dynamic threshold calculation
        self._score_ma: Optional[Decimal] = None  # Moving average of scores
        self._adjusted_score: Optional[Decimal] = None  # De-biased/centered score

        # DRAMM Step 2: Dynamic Thresholds variables
        self._dynamic_entry_threshold: Optional[Decimal] = None  # Dynamic entry threshold based on quantiles
        self._dynamic_exit_threshold: Optional[Decimal] = None  # Dynamic exit threshold based on quantiles

        # DRAMM Step 3: Squeeze time confirmation counter
        self._squeeze_confirm_count = 0  # Counter for consecutive Squeeze bars

        # BBW quantile information for dynamic Squeeze detection debugging
        self._current_bbw_quantile: Optional[Decimal] = None
        self._current_bbw_percentile: Optional[float] = None

        # Trailing stops (symbol -> stop price)
        self.trailing_stops: Dict[str, Decimal] = {}

        # Streaming indicators
        self.streaming_adx = StreamingADX(period=adx_period, window_size=100)
        self.streaming_bb = StreamingBollingerBands(
            period=bollinger_period,
            std_dev=bollinger_std,
            window_size=100,
        )

        # Required history length
        self.min_history = max(
            adx_period * 2 + 1,
            bollinger_period,
            rsi_period,
            atr_period,
            zscore_period,
        ) + 10

    def on_bar(self, bar: BarData) -> None:
        """Bar callback with strategy logic."""
        print(f"[DRAMM] on_bar() called at {bar.timestamp}")
        self.bar_history.append(bar)

        # Keep sufficient history
        if len(self.bar_history) > self.min_history + 50:
            self.bar_history.pop(0)

        # Update streaming indicators
        self.streaming_adx.update(bar.high, bar.low, bar.close)
        self.streaming_bb.update(bar.close)

        # Need enough data
        if len(self.bar_history) < self.min_history:
            print(f"[DRAMM] Not enough data: {len(self.bar_history)}/{self.min_history}")
            return

        # Step 1: Regime Identification
        self._identify_regime()

        # Step 2: Calculate indicators and scores
        closes = [b.close for b in self.bar_history]
        highs = [b.high for b in self.bar_history]
        lows = [b.low for b in self.bar_history]

        adx_results = calculate_adx(highs, lows, closes, self.adx_period)
        bb_results = calculate_bollinger_bands(closes, self.bollinger_period, self.bollinger_std)
        rsi_results = calculate_rsi(closes, self.rsi_period)
        atr_results = calculate_atr(highs, lows, closes, self.atr_period)
        zscore_results = calculate_zscore(closes, self.zscore_period)

        current_adx = adx_results[-1] if adx_results else None
        current_bb = bb_results[-1] if bb_results else None
        current_rsi = rsi_results[-1] if rsi_results else None
        current_atr = atr_results[-1] if atr_results else None
        current_zscore = zscore_results[-1] if zscore_results else None

        # Log current state
        self._log_regime_state(current_adx, current_bb, current_rsi, current_atr, current_zscore)

        # Get position
        position = None
        if self.broker is not None:
            position = self.broker.get_position(bar.symbol)

        if position is None:
            # No position, check entry
            if self._check_entry_conditions(bar, current_adx, current_bb, current_rsi, current_atr, current_zscore):
                self._enter_position(bar, current_adx, current_bb, current_rsi, current_zscore)
        else:
            # In position, check exit and update trailing stop
            self._update_trailing_stop(bar, position, current_atr)
            if self._check_exit_conditions(bar, position, current_adx, current_bb, current_rsi, current_atr, current_zscore):
                self._exit_position(bar, position)

    def on_funding_rate(self, rate: Decimal, timestamp: datetime) -> None:
        """Funding rate callback."""
        self.current_funding_rate = rate
        print(f"[DRAMM] Funding rate updated: {rate:.6%} at {timestamp}")

    def _identify_regime(self) -> None:
        """Identify current market regime using ADX and BBW with dynamic quantile-based Squeeze detection.
        
        Key improvements based on deep analysis:
        - Replaced fixed BBW_SQUEEZE_THRESHOLD (0.01) with dynamic quantile-based detection
        - Squeeze is now identified when BBW is in bottom 10% of past 20 days
        - This addresses the Squeeze over-identification issue in historical analysis
        """
        closes = [b.close for b in self.bar_history]
        highs = [b.high for b in self.bar_history]
        lows = [b.low for b in self.bar_history]

        adx_results = calculate_adx(highs, lows, closes, self.adx_period)
        bb_results = calculate_bollinger_bands(closes, self.bollinger_period, self.bollinger_std)

        current_adx = adx_results[-1] if adx_results else None
        current_bb = bb_results[-1] if bb_results else None

        if current_adx is None or current_adx.adx is None or current_bb is None or current_bb.bandwidth is None:
            self.current_regime = MarketRegime.UNKNOWN
            return

        adx_val = current_adx.adx
        bbw_val = current_bb.bandwidth

        # Dynamic Squeeze detection: check if BBW is in bottom quantile of historical BBW
        is_squeeze = False
        bbw_quantile_value = None
        bbw_percentile = None
        
        if len(bb_results) >= self.BBW_HISTORY_PERIOD:
            # Get BBW history for quantile calculation
            bbw_history = [bb.bandwidth for bb in bb_results[-self.BBW_HISTORY_PERIOD:] if bb.bandwidth is not None]
            
            if bbw_history:
                bbw_history_sorted = sorted(bbw_history)
                # Calculate the quantile threshold value
                quantile_index = int(len(bbw_history_sorted) * self.BBW_SQUEEZE_QUANTILE)
                bbw_quantile_value = bbw_history_sorted[quantile_index]
                
                # Calculate current BBW percentile in history
                bbw_percentile = bbw_history_sorted.index(bbw_val) / len(bbw_history_sorted) if bbw_val in bbw_history_sorted else sum(1 for b in bbw_history if b <= bbw_val) / len(bbw_history)
                
                # Squeeze if current BBW is below the quantile threshold
                is_squeeze = bbw_val <= bbw_quantile_value

        # Regime classification logic with dynamic Squeeze detection
        previous_regime = self.current_regime
        if adx_val > self.ADX_TREND_THRESHOLD:
            self.current_regime = MarketRegime.TREND
        elif is_squeeze:
            self.current_regime = MarketRegime.SQUEEZE
        elif adx_val < self.ADX_CHOP_THRESHOLD:
            self.current_regime = MarketRegime.CHOP
        else:
            # Transitioning, stay in previous or default to CHOP
            if self.current_regime == MarketRegime.UNKNOWN:
                self.current_regime = MarketRegime.CHOP

        # DRAMM Step 3: Reset Squeeze confirmation counter when regime changes
        if previous_regime != self.current_regime:
            self._squeeze_confirm_count = 0

        # Store quantile information for debugging
        self._current_bbw_quantile = bbw_quantile_value
        self._current_bbw_percentile = bbw_percentile

    def _log_regime_state(
        self,
        adx: Optional[ADXResult],
        bb: Optional[BollingerBandsResult],
        rsi: Optional[Decimal],
        atr: Optional[Decimal],
        zscore: Optional[Decimal],
    ) -> None:
        """Log current regime and indicator state with BBW quantile information for debugging."""
        adx_val = adx.adx if adx and adx.adx else None
        plus_di = adx.plus_di if adx and adx.plus_di else None
        minus_di = adx.minus_di if adx and adx.minus_di else None
        bbw_val = bb.bandwidth if bb and bb.bandwidth else None
        percent_b = bb.percent_b if bb and bb.percent_b else None

        log_parts = [
            f"[DRAMM] Regime: {self.current_regime.value.upper()}",
        ]

        # DRAMM Step 3: Add regime weights to log output
        if self.current_regime == MarketRegime.TREND:
            log_parts.append(f"EntryMult={self.trend_entry_multiplier:.2f}/ExitMult={self.trend_exit_multiplier:.2f}")
        elif self.current_regime == MarketRegime.CHOP:
            log_parts.append(f"EntryMult={self.chop_entry_multiplier:.2f}/ExitMult={self.chop_exit_multiplier:.2f}")
        elif self.current_regime == MarketRegime.SQUEEZE:
            log_parts.append(f"SqueezeConf={self._squeeze_confirm_count}/{self.squeeze_time_confirm}")

        if adx_val is not None:
            log_parts.append(f"ADX={adx_val:.2f}")
        if plus_di is not None and minus_di is not None:
            log_parts.append(f"+DI={plus_di:.2f}/-DI={minus_di:.2f}")
        if bbw_val is not None:
            log_parts.append(f"BBW={bbw_val:.4%}")
        # Add BBW quantile information for dynamic Squeeze detection debugging
        if self._current_bbw_quantile is not None:
            log_parts.append(f"BBW_Q={self._current_bbw_quantile:.4%}")
        if self._current_bbw_percentile is not None:
            log_parts.append(f"BBW_Pct={self._current_bbw_percentile:.1%}")
        if percent_b is not None:
            log_parts.append(f"%B={percent_b:.2f}")
        if rsi is not None:
            log_parts.append(f"RSI={rsi:.2f}")
        if atr is not None:
            log_parts.append(f"ATR={atr:.4f}")
        if zscore is not None:
            log_parts.append(f"Z={zscore:.2f}")
        if self.current_funding_rate is not None:
            log_parts.append(f"Funding={self.current_funding_rate:.6%}")

        print(" | ".join(log_parts))

    def _calculate_composite_score(
        self,
        adx: Optional[ADXResult],
        bb: Optional[BollingerBandsResult],
        rsi: Optional[Decimal],
        zscore: Optional[Decimal],
    ) -> Decimal:
        """Calculate multi-factor composite score (-1.0 to +1.0) with DRAMM Step 1: Re-centering.

        Step 1 - Re-centering (去偏):
        - Maintains score history and calculates rolling mean
        - Adjusted Score = Raw Score - Score Mean
        - This eliminates market trend bias, returning signals to neutrality
        """
        # Get regime-specific weights
        weights = self.REGIME_WEIGHTS.get(self.current_regime, self.REGIME_WEIGHTS[MarketRegime.CHOP])

        score = Decimal("0")

        # Trend Factor (based on ADX and DI crossover)
        if adx and adx.adx and adx.plus_di and adx.minus_di:
            adx_normalized = min(adx.adx / Decimal("50"), Decimal("1"))
            di_signal = Decimal("1") if adx.plus_di > adx.minus_di else Decimal("-1")
            trend_score = adx_normalized * di_signal
            score += trend_score * weights.trend_factor

        # Momentum Factor (based on RSI)
        if rsi is not None:
            rsi_normalized = (rsi - Decimal("50")) / Decimal("50")
            momentum_score = -rsi_normalized  # Negative because RSI is contrarian
            score += momentum_score * weights.momentum_factor

        # Volatility Factor (based on %B and Z-Score)
        vol_score = Decimal("0")
        if bb and bb.percent_b:
            bb_score = (bb.percent_b - Decimal("0.5")) * Decimal("2")
            vol_score += bb_score * Decimal("0.6")
        if zscore is not None:
            vol_score += zscore * Decimal("0.4")
        score += vol_score * weights.volatility_factor

        # Microstructure Factor (placeholder - can be expanded with OFI etc.)
        micro_score = Decimal("0")
        score += micro_score * weights.microstructure_factor

        # Clamp raw score to [-1, 1]
        score = max(min(score, Decimal("1")), Decimal("-1"))

        # DRAMM Step 1: Re-centering (去偏) logic
        # Update raw score history for MA calculation
        self._score_history.append(score)
        if len(self._score_history) > self.score_ma_window:
            self._score_history.pop(0)

        # Calculate moving average of scores
        if len(self._score_history) >= 2:
            self._score_ma = sum(self._score_history) / Decimal(str(len(self._score_history)))
        else:
            self._score_ma = Decimal("0")

        # Calculate Adjusted Score = Raw Score - Score Mean (去偏)
        self._adjusted_score = score - self._score_ma
        
        # Update adjusted score history for dynamic threshold calculation
        self._adjusted_score_history.append(self._adjusted_score)
        if len(self._adjusted_score_history) > self.score_history_size:
            self._adjusted_score_history.pop(0)
        
        # DRAMM Step 2: Update dynamic thresholds based on adjusted score history
        self._update_dynamic_thresholds()

        return self._adjusted_score

    def _update_dynamic_thresholds(self) -> None:
        """Update dynamic entry and exit thresholds based on historical score quantiles.
        
        DRAMM Step 2: Dynamic Thresholds
        - Maintains a window of historical adjusted scores
        - Calculates quantiles to determine adaptive entry/exit thresholds
        - Entry threshold = 90th percentile (Top 10%)
        - Exit threshold = 10th percentile (Bottom 10%)
        
        This addresses the issue where fixed thresholds:
        - Fail to trigger in low volatility periods
        - Cause frequent stop-outs in high volatility periods
        """
        # Use adjusted scores for threshold calculation (after re-centering)
        if len(self._adjusted_score_history) < self.score_history_size:
            # Not enough data yet, use default thresholds
            self._dynamic_entry_threshold = self.entry_score_threshold
            self._dynamic_exit_threshold = self.exit_score_threshold
            return

        # Get the most recent adjusted scores for threshold calculation
        recent_scores = self._adjusted_score_history[-self.score_history_size:]
        
        # Sort scores for quantile calculation
        sorted_scores = sorted(recent_scores)
        n = len(sorted_scores)
        
        # Calculate entry percentile (90th percentile)
        entry_index = int(self.entry_percentile * (n - 1))
        self._dynamic_entry_threshold = sorted_scores[entry_index]
        
        # Calculate exit percentile (10th percentile)
        exit_index = int(self.exit_percentile * (n - 1))
        self._dynamic_exit_threshold = sorted_scores[exit_index]

    def _check_entry_conditions(
        self,
        bar: BarData,
        adx: Optional[ADXResult],
        bb: Optional[BollingerBandsResult],
        rsi: Optional[Decimal],
        atr: Optional[Decimal],
        zscore: Optional[Decimal],
    ) -> bool:
        """Check if entry conditions are met."""
        # ATR Volatility Filter (Min Profit Filter)
        if atr is not None and bar.close > 0:
            atr_percent = atr / bar.close
            if atr_percent < self.min_atr_percent:
                print(f"[DRAMM] Low volatility (ATR%={atr_percent:.4f} < {self.min_atr_percent}), skipping entry")
                return False

        # Funding rate filter
        if self.min_funding_rate is not None and self.current_funding_rate is not None:
            if self.current_funding_rate < self.min_funding_rate:
                return False
        if self.max_funding_rate is not None and self.current_funding_rate is not None:
            if self.current_funding_rate > self.max_funding_rate:
                return False

        # Calculate composite score
        score = self._calculate_composite_score(adx, bb, rsi, zscore)

        # DRAMM Step 1: Hard minimum threshold for absolute score
        # This prevents signals that are too weak even after re-centering
        if abs(score) < self.min_absolute_threshold:
            print(f"[DRAMM] Entry score: {score:.3f} (raw={self._score_history[-1]:.3f}, ma={self._score_ma:.3f}) - below min_absolute_threshold {self.min_absolute_threshold}")
            return False

        # DRAMM Step 2: Use dynamic threshold
        entry_threshold = self._dynamic_entry_threshold if self._dynamic_entry_threshold is not None else self.entry_score_threshold

        # DRAMM Step 3: Apply regime weights to entry threshold
        entry_multiplier = Decimal("1.0")  # Default multiplier
        if self.current_regime == MarketRegime.TREND:
            entry_multiplier = self.trend_entry_multiplier
        elif self.current_regime == MarketRegime.CHOP:
            entry_multiplier = self.chop_entry_multiplier
        elif self.current_regime == MarketRegime.SQUEEZE:
            # SQUEEZE regime requires time confirmation (consecutive bars)
            # Check if score is in extreme percentile (Top 5%)
            if len(self._adjusted_score_history) >= 20:
                sorted_scores = sorted(self._adjusted_score_history[-20:])
                extreme_index = int(float(self.squeeze_extreme_percentile) * (len(sorted_scores) - 1))
                extreme_threshold = sorted_scores[extreme_index]
                
                if score >= extreme_threshold:
                    self._squeeze_confirm_count += 1
                    if self._squeeze_confirm_count >= self.squeeze_time_confirm:
                        entry_multiplier = Decimal("1.0")  # Use default when confirmed
                    else:
                        print(f"[DRAMM] SQUEEZE confirmation: {self._squeeze_confirm_count}/{self.squeeze_time_confirm}")
                        return False
                else:
                    self._squeeze_confirm_count = 0  # Reset counter if not extreme
                    return False
            else:
                return False  # Not enough data for SQUEEZE

        # Apply multiplier to threshold
        adjusted_entry_threshold = entry_threshold * entry_multiplier

        print(f"[DRAMM] Entry score: {score:.3f} (raw={self._score_history[-1]:.3f}, ma={self._score_ma:.3f}, dyn_threshold: {entry_threshold:.3f}, regime_mult: {entry_multiplier:.2f}, adjusted_threshold: {adjusted_entry_threshold:.3f})")

        return score >= adjusted_entry_threshold

    def _check_exit_conditions(
        self,
        bar: BarData,
        position,
        adx: Optional[ADXResult],
        bb: Optional[BollingerBandsResult],
        rsi: Optional[Decimal],
        atr: Optional[Decimal],
        zscore: Optional[Decimal],
    ) -> bool:
        """Check if exit conditions are met."""
        # Trailing stop hit
        trailing_stop = self.trailing_stops.get(bar.symbol)
        if trailing_stop is not None:
            if position.side.value == "LONG" and bar.low <= trailing_stop:
                print(f"[DRAMM] Trailing stop hit (LONG): {bar.low} <= {trailing_stop}")
                return True
            if position.side.value == "SHORT" and bar.high >= trailing_stop:
                print(f"[DRAMM] Trailing stop hit (SHORT): {bar.high} >= {trailing_stop}")
                return True

        # Calculate composite score for exit
        score = self._calculate_composite_score(adx, bb, rsi, zscore)
        
        # DRAMM Step 2: Use dynamic threshold
        exit_threshold = self._dynamic_exit_threshold if self._dynamic_exit_threshold is not None else self.exit_score_threshold

        # DRAMM Step 3: Apply regime weights to exit threshold
        exit_multiplier = Decimal("1.0")  # Default multiplier
        
        # Override Exit Logic based on Regime
        if self.current_regime == MarketRegime.TREND:
            # In TREND regime, ignore score-based exit unless it's a major reversal
            # We want to ride the trend and rely primarily on the ATR Trailing Stop
            # Optimized: Relax threshold by 3.0x to avoid premature exits on consolidation
            exit_multiplier = self.trend_exit_multiplier * Decimal("3.0")
            print(f"[DRAMM] TREND Regime: Relaxing exit threshold by 3.0x multiplier")
        elif self.current_regime == MarketRegime.CHOP:
            # In CHOP regime, take profits quickly (tighter exit)
            exit_multiplier = self.chop_exit_multiplier
        elif self.current_regime == MarketRegime.SQUEEZE:
            # SQUEEZE regime: use default exit (no special multiplier)
            exit_multiplier = Decimal("1.0")

        # Apply multiplier to threshold
        adjusted_exit_threshold = exit_threshold * exit_multiplier

        # Additional check for TREND regime:
        # If we are in a strong trend, do not exit just because the score is slightly negative (mean reversion)
        # Only exit if the score crosses the adjusted threshold AND confirms a reversal
        
        print(f"[DRAMM] Exit score: {score:.3f} (raw={self._score_history[-1]:.3f}, ma={self._score_ma:.3f}, dyn_threshold: {exit_threshold:.3f}, regime_mult: {exit_multiplier:.2f}, adjusted_threshold: {adjusted_exit_threshold:.3f})")

        return score <= adjusted_exit_threshold

    def _update_trailing_stop(self, bar: BarData, position, atr: Optional[Decimal]) -> None:
        """Update Chandelier Exit trailing stop."""
        if atr is None:
            return

        stop_distance = atr * self.atr_multiplier
        current_stop = self.trailing_stops.get(bar.symbol)

        if position.side.value == "LONG":
            # Long: trailing stop moves up only
            new_stop = bar.high - stop_distance
            if current_stop is None or new_stop > current_stop:
                self.trailing_stops[bar.symbol] = new_stop
                if current_stop is not None:
                    print(f"[DRAMM] Trailing stop updated (LONG): {current_stop} -> {new_stop}")
        elif position.side.value == "SHORT":
            # Short: trailing stop moves down only
            new_stop = bar.low + stop_distance
            if current_stop is None or new_stop < current_stop:
                self.trailing_stops[bar.symbol] = new_stop
                if current_stop is not None:
                    print(f"[DRAMM] Trailing stop updated (SHORT): {current_stop} -> {new_stop}")

    def _enter_position(
        self,
        bar: BarData,
        adx: Optional[ADXResult],
        bb: Optional[BollingerBandsResult],
        rsi: Optional[Decimal],
        zscore: Optional[Decimal],
    ) -> None:
        """Enter a new position."""
        # Determine side based on score and indicators
        score = self._calculate_composite_score(adx, bb, rsi, zscore)
        side = "buy" if score > Decimal("0") else "sell"

        # Determine quantity
        quantity = self.position_size
        if self.use_percentage_position_size:
            balance = self.broker.get_balance() if self.broker else Decimal("0")
            if balance > 0:
                # Calculate quantity based on percentage of balance
                # position_size is treated as percentage (e.g., 0.1 = 10%)
                target_value = balance * Decimal(str(self.position_size))
                quantity = float(target_value / bar.close)
                print(f"[DRAMM] Dynamic Sizing: Balance=${balance:.2f} | Target=${target_value:.2f} | Qty={quantity:.4f} ETH")
            else:
                print("[DRAMM] Warning: Balance is 0 or broker unavailable, defaulting to fixed size")
                quantity = 0.01  # Fallback

        print(f"[DRAMM] 🔥 ENTERING {side.upper()} POSITION at {bar.close}, score={score:.3f} (raw={self._score_history[-1]:.3f}, ma={self._score_ma:.3f})")
        self.create_market_order(
            symbol=bar.symbol,
            side=side,
            quantity=quantity,
        )
        self.entry_price = bar.close

        # Initialize trailing stop
        closes = [b.close for b in self.bar_history]
        highs = [b.high for b in self.bar_history]
        lows = [b.low for b in self.bar_history]
        atr_results = calculate_atr(highs, lows, closes, self.atr_period)
        current_atr = atr_results[-1] if atr_results else None

        if current_atr is not None:
            stop_distance = current_atr * self.atr_multiplier
            if side == "buy":
                self.trailing_stops[bar.symbol] = bar.close - stop_distance
            else:
                self.trailing_stops[bar.symbol] = bar.close + stop_distance
            print(f"[DRAMM] Initial trailing stop set: {self.trailing_stops[bar.symbol]}")

    def _exit_position(self, bar: BarData, position) -> None:
        """Exit current position."""
        side = "sell" if position.side.value == "LONG" else "buy"
        print(f"[DRAMM] 🔴 EXITING POSITION at {bar.close}")
        self.create_market_order(
            symbol=bar.symbol,
            side=side,
            quantity=float(position.quantity),
        )
        self.entry_price = None
        if bar.symbol in self.trailing_stops:
            del self.trailing_stops[bar.symbol]

    def generate_signals(self, bar: BarData) -> List[dict]:
        """Signal generation interface."""
        signals = []
        # TODO: Implement signal generation for backtest
        return signals
