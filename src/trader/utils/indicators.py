"""Technical indicator calculations for trading strategies.

Provides common technical indicators using Decimal for precision.
All calculations use Decimal for financial calculations to avoid
floating-point precision errors.
"""
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, Field


def calculate_sma(data: List[Decimal], period: int) -> List[Optional[Decimal]]:
    """Calculate Simple Moving Average (SMA).

    Args:
        data: List of price data
        period: SMA period (e.g., 20 for 20-period SMA)

    Returns:
        List of SMA values, with None for the first (period-1) values
    """
    if period <= 0:
        raise ValueError("Period must be positive")

    result: List[Optional[Decimal]] = [None] * len(data)

    if len(data) < period:
        return result

    for i in range(period - 1, len(data)):
        window = data[i - period + 1: i + 1]
        result[i] = sum(window) / Decimal(str(period))

    return result


def calculate_ema(data: List[Decimal], period: int) -> List[Optional[Decimal]]:
    """Calculate Exponential Moving Average (EMA).

    Uses the formula: EMA = Price * multiplier + EMA_prev * (1 - multiplier)
    where multiplier = 2 / (period + 1)

    Args:
        data: List of price data
        period: EMA period (e.g., 12 or 26 for MACD)

    Returns:
        List of EMA values, with None for the first (period-1) values
    """
    if period <= 0:
        raise ValueError("Period must be positive")

    result: List[Optional[Decimal]] = [None] * len(data)

    if len(data) < period:
        return result

    # Calculate initial SMA as starting point
    sma = sum(data[:period]) / Decimal(str(period))
    result[period - 1] = sma

    # Calculate multiplier
    multiplier = Decimal("2") / (Decimal(str(period)) + Decimal("1"))

    # Calculate EMA for remaining data points
    for i in range(period, len(data)):
        prev_ema = result[i - 1]
        if prev_ema is None:
            continue
        result[i] = data[i] * multiplier + prev_ema * (Decimal("1") - multiplier)

    return result


def calculate_rsi(prices: List[Decimal], period: int = 14) -> List[Optional[Decimal]]:
    """Calculate Relative Strength Index (RSI).

    RSI = 100 - (100 / (1 + RS))
    where RS = Average Gain / Average Loss

    Args:
        prices: List of price data
        period: RSI period (default: 14)

    Returns:
        List of RSI values (0-100), with None for the first period values
    """
    if period <= 0:
        raise ValueError("Period must be positive")

    result: List[Optional[Decimal]] = [None] * len(prices)

    if len(prices) <= period:
        return result

    gains: List[Decimal] = []
    losses: List[Decimal] = []

    # Calculate initial price changes
    for i in range(1, period + 1):
        change = prices[i] - prices[i - 1]
        if change > Decimal("0"):
            gains.append(change)
            losses.append(Decimal("0"))
        elif change < Decimal("0"):
            gains.append(Decimal("0"))
            losses.append(abs(change))
        else:
            gains.append(Decimal("0"))
            losses.append(Decimal("0"))

    # Initial averages
    avg_gain = sum(gains) / Decimal(str(period))
    avg_loss = sum(losses) / Decimal(str(period))

    # First RSI value
    if avg_loss == Decimal("0"):
        result[period] = Decimal("100")
    else:
        rs = avg_gain / avg_loss
        result[period] = Decimal("100") - (Decimal("100") / (Decimal("1") + rs))

    # Calculate RSI for remaining data points (smoothed)
    for i in range(period + 1, len(prices)):
        change = prices[i] - prices[i - 1]
        gain = change if change > Decimal("0") else Decimal("0")
        loss = abs(change) if change < Decimal("0") else Decimal("0")

        # Smoothed averages
        avg_gain = (avg_gain * Decimal(str(period - 1)) + gain) / Decimal(str(period))
        avg_loss = (avg_loss * Decimal(str(period - 1)) + loss) / Decimal(str(period))

        if avg_loss == Decimal("0"):
            result[i] = Decimal("100")
        else:
            rs = avg_gain / avg_loss
            result[i] = Decimal("100") - (Decimal("100") / (Decimal("1") + rs))

    return result


def calculate_atr(
    highs: List[Decimal],
    lows: List[Decimal],
    closes: List[Decimal],
    period: int = 14,
) -> List[Optional[Decimal]]:
    """Calculate Average True Range (ATR).

    True Range = max(high - low, abs(high - prev_close), abs(low - prev_close))
    ATR = SMA of True Range over period

    Args:
        highs: List of high prices
        lows: List of low prices
        closes: List of close prices
        period: ATR period (default: 14)

    Returns:
        List of ATR values, with None for the first period values
    """
    if period <= 0:
        raise ValueError("Period must be positive")

    if len(highs) != len(lows) or len(highs) != len(closes):
        raise ValueError("All price lists must have the same length")

    result: List[Optional[Decimal]] = [None] * len(highs)

    if len(highs) <= period:
        return result

    # Calculate True Ranges
    true_ranges: List[Decimal] = []
    for i in range(1, len(highs)):
        high_low = highs[i] - lows[i]
        high_close_prev = abs(highs[i] - closes[i - 1])
        low_close_prev = abs(lows[i] - closes[i - 1])
        true_range = max(high_low, high_close_prev, low_close_prev)
        true_ranges.append(true_range)

    # Calculate initial ATR (simple average of first 'period' TRs)
    if len(true_ranges) >= period:
        initial_atr = sum(true_ranges[:period]) / Decimal(str(period))
        result[period] = initial_atr

        # Calculate remaining ATR values (smoothed)
        for i in range(period + 1, len(highs)):
            prev_atr = result[i - 1]
            if prev_atr is None:
                continue
            tr_index = i - 1  # true_ranges is offset by 1
            if tr_index < len(true_ranges):
                # Smoothed ATR formula
                result[i] = (prev_atr * Decimal(str(period - 1)) + true_ranges[tr_index]) / Decimal(str(period))

    return result


class BollingerBandsResult(BaseModel):
    """Result container for Bollinger Bands."""
    middle: Optional[Decimal] = Field(default=None, description="Middle band (SMA)")
    upper: Optional[Decimal] = Field(default=None, description="Upper band (SMA + 2*std)")
    lower: Optional[Decimal] = Field(default=None, description="Lower band (SMA - 2*std)")
    bandwidth: Optional[Decimal] = Field(default=None, description="Bandwidth (upper - lower)/middle")
    percent_b: Optional[Decimal] = Field(default=None, description="%B indicator")


def calculate_bollinger_bands(
    data: List[Decimal],
    period: int = 20,
    std_dev: Decimal = Decimal("2"),
) -> List[BollingerBandsResult]:
    """Calculate Bollinger Bands.

    Bollinger Bands consist of:
    - Middle band: N-period SMA
    - Upper band: Middle band + (N-period standard deviation * K)
    - Lower band: Middle band - (N-period standard deviation * K)

    Args:
        data: List of price data
        period: Bollinger Bands period (default: 20)
        std_dev: Standard deviation multiplier (default: 2)

    Returns:
        List of BollingerBandsResult objects
    """
    if period <= 0:
        raise ValueError("Period must be positive")

    result = [BollingerBandsResult() for _ in range(len(data))]

    if len(data) < period:
        return result

    # Calculate SMA (middle band)
    sma = calculate_sma(data, period)

    # Calculate standard deviation and bands
    for i in range(period - 1, len(data)):
        middle = sma[i]
        if middle is None:
            continue

        # Calculate standard deviation over the period
        window = data[i - period + 1: i + 1]
        mean = sum(window) / Decimal(str(period))
        variance = sum((x - mean) ** 2 for x in window) / Decimal(str(period))
        std = variance.sqrt()

        upper = middle + std * std_dev
        lower = middle - std * std_dev
        bandwidth = (upper - lower) / middle if middle != Decimal("0") else None
        percent_b = (data[i] - lower) / (upper - lower) if (upper - lower) != Decimal("0") else None

        result[i] = BollingerBandsResult(
            middle=middle,
            upper=upper,
            lower=lower,
            bandwidth=bandwidth,
            percent_b=percent_b,
        )

    return result


class MACDResult(BaseModel):
    """Result container for MACD."""
    macd_line: Optional[Decimal] = Field(default=None, description="MACD line (EMA12 - EMA26)")
    signal_line: Optional[Decimal] = Field(default=None, description="Signal line (EMA of MACD)")
    histogram: Optional[Decimal] = Field(default=None, description="Histogram (MACD - Signal)")


def calculate_macd(
    data: List[Decimal],
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
) -> List[MACDResult]:
    """Calculate Moving Average Convergence Divergence (MACD).

    MACD = EMA(fast) - EMA(slow)
    Signal = EMA(MACD, signal_period)
    Histogram = MACD - Signal

    Args:
        data: List of price data
        fast_period: Fast EMA period (default: 12)
        slow_period: Slow EMA period (default: 26)
        signal_period: Signal line EMA period (default: 9)

    Returns:
        List of MACDResult objects
    """
    if fast_period <= 0 or slow_period <= 0 or signal_period <= 0:
        raise ValueError("All periods must be positive")
    if fast_period >= slow_period:
        raise ValueError("Fast period must be less than slow period")

    result = [MACDResult() for _ in range(len(data))]

    if len(data) < slow_period:
        return result

    # Calculate EMAs
    ema_fast = calculate_ema(data, fast_period)
    ema_slow = calculate_ema(data, slow_period)

    # Calculate MACD line
    macd_line: List[Optional[Decimal]] = [None] * len(data)
    for i in range(len(data)):
        if ema_fast[i] is not None and ema_slow[i] is not None:
            macd_line[i] = ema_fast[i] - ema_slow[i]

    # Calculate signal line (EMA of MACD)
    # Filter out None values for EMA calculation
    macd_values = [v for v in macd_line if v is not None]
    if len(macd_values) >= signal_period:
        signal_values = calculate_ema(macd_values, signal_period)
        # Map back to original indices
        signal_idx = 0
        for i in range(len(data)):
            if macd_line[i] is not None:
                if signal_idx < len(signal_values) and signal_values[signal_idx] is not None:
                    result[i].macd_line = macd_line[i]
                    result[i].signal_line = signal_values[signal_idx]
                    result[i].histogram = macd_line[i] - signal_values[signal_idx]
                signal_idx += 1

    return result


class KDJResult(BaseModel):
    """Result container for KDJ indicator."""
    k: Optional[Decimal] = Field(default=None, description="K value")
    d: Optional[Decimal] = Field(default=None, description="D value")
    j: Optional[Decimal] = Field(default=None, description="J value (3*K - 2*D)")


def calculate_kdj(
    highs: List[Decimal],
    lows: List[Decimal],
    closes: List[Decimal],
    rsv_period: int = 9,
    k_period: int = 3,
    d_period: int = 3,
) -> List[KDJResult]:
    """Calculate KDJ indicator (Stochastic Oscillator variant).

    RSV = (Close - Lowest Low) / (Highest High - Lowest Low) * 100
    K = SMA(RSV, k_period)
    D = SMA(K, d_period)
    J = 3*K - 2*D

    Args:
        highs: List of high prices
        lows: List of low prices
        closes: List of close prices
        rsv_period: RSV calculation period (default: 9)
        k_period: K line SMA period (default: 3)
        d_period: D line SMA period (default: 3)

    Returns:
        List of KDJResult objects
    """
    if rsv_period <= 0 or k_period <= 0 or d_period <= 0:
        raise ValueError("All periods must be positive")

    if len(highs) != len(lows) or len(highs) != len(closes):
        raise ValueError("All price lists must have the same length")

    result = [KDJResult() for _ in range(len(highs))]

    if len(highs) < rsv_period:
        return result

    # Calculate RSV (Raw Stochastic Value)
    rsv: List[Optional[Decimal]] = [None] * len(highs)
    for i in range(rsv_period - 1, len(highs)):
        window_highs = highs[i - rsv_period + 1: i + 1]
        window_lows = lows[i - rsv_period + 1: i + 1]
        highest_high = max(window_highs)
        lowest_low = min(window_lows)

        if highest_high != lowest_low:
            rsv[i] = (closes[i] - lowest_low) / (highest_high - lowest_low) * Decimal("100")
        else:
            rsv[i] = Decimal("50")

    # Calculate K (SMA of RSV)
    k_values = [v for v in rsv if v is not None]
    k_line = calculate_sma(k_values, k_period) if len(k_values) >= k_period else []

    # Calculate D (SMA of K)
    d_values = [v for v in k_line if v is not None]
    d_line = calculate_sma(d_values, d_period) if len(d_values) >= d_period else []

    # Map back to original indices
    k_idx = 0
    d_idx = 0
    for i in range(len(highs)):
        if rsv[i] is not None:
            if k_idx < len(k_line) and k_line[k_idx] is not None:
                result[i].k = k_line[k_idx]

                if d_idx < len(d_line) and d_line[d_idx] is not None:
                    result[i].d = d_line[d_idx]
                    result[i].j = Decimal("3") * k_line[k_idx] - Decimal("2") * d_line[d_idx]
                    d_idx += 1
                k_idx += 1

    return result


class StreamingIndicator:
    """Base class for streaming indicators with incremental updates.
    
    Uses Scheme A: maintains a window of historical data, recalculates
    when new data arrives. Simple and reliable for most use cases.
    """

    def __init__(self, window_size: int = 100):
        """Initialize streaming indicator.
        
        Args:
            window_size: Maximum number of historical data points to keep
        """
        self.window_size = window_size
        self._data: List[Decimal] = []

    def update(self, value: Decimal) -> None:
        """Add a new data point and maintain window size.
        
        Args:
            value: New data point to add
        """
        self._data.append(value)
        if len(self._data) > self.window_size:
            self._data.pop(0)

    @property
    def data(self) -> List[Decimal]:
        """Get the current data window."""
        return self._data.copy()


class StreamingBollingerBands(StreamingIndicator):
    """Streaming Bollinger Bands indicator."""

    def __init__(self, period: int = 20, std_dev: Decimal = Decimal("2"), window_size: int = 100):
        super().__init__(window_size)
        self.period = period
        self.std_dev = std_dev

    def get_current(self) -> Optional[BollingerBandsResult]:
        """Get current Bollinger Bands value.
        
        Returns:
            BollingerBandsResult or None if insufficient data
        """
        if len(self._data) < self.period:
            return None

        results = calculate_bollinger_bands(self._data, self.period, self.std_dev)
        return results[-1] if results else None


class StreamingMACD(StreamingIndicator):
    """Streaming MACD indicator."""

    def __init__(
        self,
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9,
        window_size: int = 100,
    ):
        super().__init__(window_size)
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.signal_period = signal_period

    def get_current(self) -> Optional[MACDResult]:
        """Get current MACD value.
        
        Returns:
            MACDResult or None if insufficient data
        """
        if len(self._data) < self.slow_period:
            return None

        results = calculate_macd(
            self._data,
            self.fast_period,
            self.slow_period,
            self.signal_period,
        )
        return results[-1] if results else None


class StreamingKDJ:
    """Streaming KDJ indicator (requires high/low/close)."""

    def __init__(
        self,
        rsv_period: int = 9,
        k_period: int = 3,
        d_period: int = 3,
        window_size: int = 100,
    ):
        self.rsv_period = rsv_period
        self.k_period = k_period
        self.d_period = d_period
        self.window_size = window_size
        self._highs: List[Decimal] = []
        self._lows: List[Decimal] = []
        self._closes: List[Decimal] = []

    def update(self, high: Decimal, low: Decimal, close: Decimal) -> None:
        """Add new OHLC data.
        
        Args:
            high: High price
            low: Low price
            close: Close price
        """
        self._highs.append(high)
        self._lows.append(low)
        self._closes.append(close)

        if len(self._highs) > self.window_size:
            self._highs.pop(0)
            self._lows.pop(0)
            self._closes.pop(0)

    def get_current(self) -> Optional[KDJResult]:
        """Get current KDJ value.
        
        Returns:
            KDJResult or None if insufficient data
        """
        if len(self._highs) < self.rsv_period:
            return None

        results = calculate_kdj(
            self._highs,
            self._lows,
            self._closes,
            self.rsv_period,
            self.k_period,
            self.d_period,
        )
        return results[-1] if results else None


class TechnicalIndicators(BaseModel):
    """Container for technical indicators."""
    sma_short: Optional[Decimal] = Field(default=None, description="Short-term SMA")
    sma_long: Optional[Decimal] = Field(default=None, description="Long-term SMA")
    ema_short: Optional[Decimal] = Field(default=None, description="Short-term EMA")
    ema_long: Optional[Decimal] = Field(default=None, description="Long-term EMA")
    rsi: Optional[Decimal] = Field(default=None, description="Relative Strength Index")
    atr: Optional[Decimal] = Field(default=None, description="Average True Range")
    bollinger: Optional[BollingerBandsResult] = Field(default=None, description="Bollinger Bands")
    macd: Optional[MACDResult] = Field(default=None, description="MACD")
    kdj: Optional[KDJResult] = Field(default=None, description="KDJ")


def calculate_all_indicators(
    prices: List[Decimal],
    highs: List[Decimal],
    lows: List[Decimal],
    closes: List[Decimal],
    sma_short_period: int = 10,
    sma_long_period: int = 20,
    ema_short_period: int = 12,
    ema_long_period: int = 26,
    rsi_period: int = 14,
    atr_period: int = 14,
    bollinger_period: int = 20,
    bollinger_std: Decimal = Decimal("2"),
    macd_fast: int = 12,
    macd_slow: int = 26,
    macd_signal: int = 9,
    kdj_rsv: int = 9,
    kdj_k: int = 3,
    kdj_d: int = 3,
) -> List[TechnicalIndicators]:
    """Calculate all technical indicators for a price series.

    Args:
        prices: List of prices (typically close prices)
        highs: List of high prices
        lows: List of low prices
        closes: List of close prices
        sma_short_period: Short SMA period (default: 10)
        sma_long_period: Long SMA period (default: 20)
        ema_short_period: Short EMA period (default: 12)
        ema_long_period: Long EMA period (default: 26)
        rsi_period: RSI period (default: 14)
        atr_period: ATR period (default: 14)
        bollinger_period: Bollinger Bands period (default: 20)
        bollinger_std: Bollinger Bands standard deviation multiplier (default: 2)
        macd_fast: MACD fast EMA period (default: 12)
        macd_slow: MACD slow EMA period (default: 26)
        macd_signal: MACD signal line period (default: 9)
        kdj_rsv: KDJ RSV period (default: 9)
        kdj_k: KDJ K line period (default: 3)
        kdj_d: KDJ D line period (default: 3)

    Returns:
        List of TechnicalIndicators objects, one for each data point
    """
    # Calculate individual indicators
    sma_short = calculate_sma(prices, sma_short_period)
    sma_long = calculate_sma(prices, sma_long_period)
    ema_short = calculate_ema(prices, ema_short_period)
    ema_long = calculate_ema(prices, ema_long_period)
    rsi = calculate_rsi(prices, rsi_period)
    atr = calculate_atr(highs, lows, closes, atr_period)
    bollinger = calculate_bollinger_bands(prices, bollinger_period, bollinger_std)
    macd = calculate_macd(prices, macd_fast, macd_slow, macd_signal)
    kdj = calculate_kdj(highs, lows, closes, kdj_rsv, kdj_k, kdj_d)

    # Combine into TechnicalIndicators objects
    indicators_list = []
    for i in range(len(prices)):
        indicators = TechnicalIndicators(
            sma_short=sma_short[i],
            sma_long=sma_long[i],
            ema_short=ema_short[i],
            ema_long=ema_long[i],
            rsi=rsi[i],
            atr=atr[i],
            bollinger=bollinger[i] if i < len(bollinger) else None,
            macd=macd[i] if i < len(macd) else None,
            kdj=kdj[i] if i < len(kdj) else None,
        )
        indicators_list.append(indicators)

    return indicators_list
