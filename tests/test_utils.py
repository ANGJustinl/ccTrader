"""Tests for utility modules including indicators and slippage models."""
import pytest
from decimal import Decimal
from datetime import datetime

from trader.utils.indicators import (
    calculate_sma,
    calculate_ema,
    calculate_rsi,
    calculate_atr,
)
from trader.utils.slippage import (
    VolatilitySlippageModel,
    BarDataForSlippage,
    calculate_slippage,
)


class TestSMA:
    """Tests for Simple Moving Average calculation."""

    def test_sma_calculation(self):
        """Test basic SMA calculation."""
        data = [Decimal(str(i)) for i in range(1, 11)]
        result = calculate_sma(data, 3)
        
        assert len(result) == 10
        assert result[0] is None
        assert result[1] is None
        assert result[2] == Decimal("2")  # (1+2+3)/3
        assert result[3] == Decimal("3")  # (2+3+4)/3
        assert result[9] == Decimal("9")  # (8+9+10)/3

    def test_sma_insufficient_data(self):
        """Test SMA with insufficient data."""
        data = [Decimal("1"), Decimal("2")]
        result = calculate_sma(data, 3)
        assert all(x is None for x in result)

    def test_sma_invalid_period(self):
        """Test SMA with invalid period."""
        data = [Decimal("1")]
        with pytest.raises(ValueError):
            calculate_sma(data, 0)


class TestEMA:
    """Tests for Exponential Moving Average calculation."""

    def test_ema_calculation(self):
        """Test basic EMA calculation."""
        data = [Decimal(str(i)) for i in range(1, 11)]
        result = calculate_ema(data, 3)
        
        assert len(result) == 10
        assert result[0] is None
        assert result[1] is None
        assert result[2] is not None  # Initial SMA
        assert result[9] is not None  # EMA for last point

    def test_ema_insufficient_data(self):
        """Test EMA with insufficient data."""
        data = [Decimal("1"), Decimal("2")]
        result = calculate_ema(data, 3)
        assert all(x is None for x in result)


class TestRSI:
    """Tests for Relative Strength Index calculation."""

    def test_rsi_basic(self):
        """Test basic RSI calculation."""
        # Create data with alternating gains and losses
        data = []
        for i in range(20):
            if i % 2 == 0:
                data.append(Decimal("100"))
            else:
                data.append(Decimal("101"))
        
        result = calculate_rsi(data, 14)
        
        assert len(result) == 20
        # First 14 should be None
        for i in range(14):
            assert result[i] is None
        # RSI should be calculated for the rest
        for i in range(14, 20):
            assert result[i] is not None
            assert Decimal("0") <= result[i] <= Decimal("100")

    def test_rsi_insufficient_data(self):
        """Test RSI with insufficient data."""
        data = [Decimal("100") for _ in range(10)]
        result = calculate_rsi(data, 14)
        assert all(x is None for x in result)


class TestATR:
    """Tests for Average True Range calculation."""

    def test_atr_basic(self):
        """Test basic ATR calculation."""
        highs = [Decimal("110"), Decimal("115"), Decimal("112"), Decimal("118"), Decimal("120")]
        lows = [Decimal("100"), Decimal("105"), Decimal("102"), Decimal("108"), Decimal("110")]
        closes = [Decimal("105"), Decimal("110"), Decimal("108"), Decimal("115"), Decimal("118")]
        
        result = calculate_atr(highs, lows, closes, 3)
        
        assert len(result) == 5
        # First 3 should be None
        for i in range(3):
            assert result[i] is None
        # ATR should be calculated for the rest
        for i in range(3, 5):
            assert result[i] is not None
            assert result[i] > Decimal("0")

    def test_atr_length_mismatch(self):
        """Test ATR with mismatched input lengths."""
        highs = [Decimal("110"), Decimal("115")]
        lows = [Decimal("100")]  # Too short
        closes = [Decimal("105"), Decimal("110")]
        
        with pytest.raises(ValueError):
            calculate_atr(highs, lows, closes, 2)


class TestVolatilitySlippageModel:
    """Tests for VolatilitySlippageModel."""

    def test_model_creation(self):
        """Test creating a slippage model with defaults."""
        model = VolatilitySlippageModel()
        assert model.base_slippage == Decimal("0.0005")
        assert model.max_slippage == Decimal("0.005")

    def test_model_with_custom_params(self):
        """Test creating a slippage model with custom parameters."""
        model = VolatilitySlippageModel(
            base_slippage=Decimal("0.001"),
            max_slippage=Decimal("0.01"),
        )
        assert model.base_slippage == Decimal("0.001")
        assert model.max_slippage == Decimal("0.01")

    def test_calculate_volatility(self):
        """Test volatility calculation."""
        model = VolatilitySlippageModel()
        
        bars = [
            BarDataForSlippage(
                open=Decimal("100"),
                high=Decimal("110"),
                low=Decimal("90"),
                close=Decimal("105"),
            ),
            BarDataForSlippage(
                open=Decimal("105"),
                high=Decimal("115"),
                low=Decimal("95"),
                close=Decimal("110"),
            ),
        ]
        
        volatility = model.calculate_volatility(bars)
        assert volatility >= Decimal("0")

    def test_calculate_slippage(self):
        """Test slippage calculation."""
        model = VolatilitySlippageModel()
        
        bars = [
            BarDataForSlippage(
                open=Decimal("100"),
                high=Decimal("102"),
                low=Decimal("98"),
                close=Decimal("101"),
            ),
            BarDataForSlippage(
                open=Decimal("101"),
                high=Decimal("103"),
                low=Decimal("99"),
                close=Decimal("102"),
            ),
        ]
        
        slippage = model.calculate_slippage(bars, "buy")
        assert slippage >= model.base_slippage
        assert slippage <= model.max_slippage

    def test_apply_slippage_buy(self):
        """Test applying slippage to buy orders."""
        model = VolatilitySlippageModel(base_slippage=Decimal("0.01"))
        
        bars = [
            BarDataForSlippage(
                open=Decimal("100"),
                high=Decimal("101"),
                low=Decimal("99"),
                close=Decimal("100"),
            )
        ] * 2
        
        price = Decimal("100")
        result = model.apply_slippage(price, bars, "buy")
        
        # Buy price should be higher with slippage
        assert result > price

    def test_apply_slippage_sell(self):
        """Test applying slippage to sell orders."""
        model = VolatilitySlippageModel(base_slippage=Decimal("0.01"))
        
        bars = [
            BarDataForSlippage(
                open=Decimal("100"),
                high=Decimal("101"),
                low=Decimal("99"),
                close=Decimal("100"),
            )
        ] * 2
        
        price = Decimal("100")
        result = model.apply_slippage(price, bars, "sell")
        
        # Sell price should be lower with slippage
        assert result < price


class TestCalculateSlippageFunction:
    """Tests for the standalone calculate_slippage function."""

    def test_calculate_slippage_buy(self):
        """Test the standalone function for buy orders."""
        price = Decimal("100")
        volatility = Decimal("0.02")
        
        result = calculate_slippage(price, volatility, "buy")
        assert result > price

    def test_calculate_slippage_sell(self):
        """Test the standalone function for sell orders."""
        price = Decimal("100")
        volatility = Decimal("0.02")
        
        result = calculate_slippage(price, volatility, "sell")
        assert result < price

    def test_calculate_slippage_max_clamping(self):
        """Test that slippage is clamped at maximum."""
        price = Decimal("100")
        volatility = Decimal("1.0")  # Very high volatility
        max_slippage = Decimal("0.01")
        
        result = calculate_slippage(
            price, volatility, "buy",
            max_slippage=max_slippage
        )
        
        max_price = price * (Decimal("1") + max_slippage)
        assert result <= max_price
