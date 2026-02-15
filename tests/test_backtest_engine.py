"""Unit tests for backtest engine components.

Tests for Order model, SimulatedBroker, and BacktestEngine.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from trader.application.backtest_engine import BacktestEngine
from trader.application.order import Order, OrderStatus
from trader.application.simulated_broker import SimulatedBroker
from trader.domain.value_objects import Side
from trader.infrastructure.clock import BacktestClock
from trader.infrastructure.data_repository import BarData, FundingRateData
from trader.infrastructure.event_bus import EventBus, EventType


class TestOrder:
    """Test cases for Order model."""

    def test_create_order(self) -> None:
        """测试创建订单"""
        order = Order(
            symbol="BTC/USDT",
            side="buy",
            order_type="market",
            quantity=Decimal("1.0"),
            price=None,
            timestamp=datetime.now(timezone.utc),
        )

        assert order.symbol == "BTC/USDT"
        assert order.side == "buy"
        assert order.order_type == "market"
        assert order.quantity == Decimal("1.0")
        assert order.price is None
        assert order.status == OrderStatus.PENDING
        assert order.filled_quantity == Decimal("0")
        assert order.avg_fill_price is None
        assert len(order.id) > 0

    def test_remaining_quantity(self) -> None:
        """测试计算剩余数量"""
        order = Order(
            symbol="BTC/USDT",
            side="buy",
            order_type="market",
            quantity=Decimal("1.0"),
            price=None,
            timestamp=datetime.now(timezone.utc),
        )

        assert order.remaining_quantity == Decimal("1.0")

        order.filled_quantity = Decimal("0.5")
        assert order.remaining_quantity == Decimal("0.5")

        order.filled_quantity = Decimal("1.0")
        assert order.remaining_quantity == Decimal("0")

    def test_is_open(self) -> None:
        """测试订单是否开放"""
        order = Order(
            symbol="BTC/USDT",
            side="buy",
            order_type="market",
            quantity=Decimal("1.0"),
            price=None,
            timestamp=datetime.now(timezone.utc),
        )

        assert order.is_open is True

        order.status = OrderStatus.SUBMITTED
        assert order.is_open is True

        order.status = OrderStatus.PARTIAL_FILLED
        assert order.is_open is True

        order.status = OrderStatus.FILLED
        assert order.is_open is False

        order.status = OrderStatus.CANCELLED
        assert order.is_open is False

        order.status = OrderStatus.REJECTED
        assert order.is_open is False


class TestSimulatedBroker:
    """Test cases for SimulatedBroker."""

    @pytest.fixture
    def clock(self) -> BacktestClock:
        """Create backtest clock."""
        return BacktestClock()

    @pytest.fixture
    def event_bus(self) -> EventBus:
        """Create event bus."""
        return EventBus()

    @pytest.fixture
    def broker(self, clock: BacktestClock, event_bus: EventBus) -> SimulatedBroker:
        """Create simulated broker."""
        return SimulatedBroker(
            clock=clock,
            event_bus=event_bus,
            initial_balance=Decimal("10000"),
            slippage_rate=Decimal("0.0005"),
            commission_rate=Decimal("0.0004"),
        )

    def test_submit_order(self, broker: SimulatedBroker) -> None:
        """测试提交订单"""
        order = Order(
            symbol="BTC/USDT",
            side="buy",
            order_type="market",
            quantity=Decimal("1.0"),
            price=None,
            timestamp=datetime.now(timezone.utc),
        )

        broker.submit_order(order)

        assert order.id in broker.orders
        assert order.status == OrderStatus.SUBMITTED
        assert order.id in broker.open_orders["BTC/USDT"]

    def test_match_market_order_buy(self, broker: SimulatedBroker) -> None:
        """测试撮合买单（市价单）"""
        order = Order(
            symbol="BTC/USDT",
            side="buy",
            order_type="market",
            quantity=Decimal("1.0"),
            price=None,
            timestamp=datetime.now(timezone.utc),
        )

        broker.submit_order(order)
        fills = broker.match_orders("BTC/USDT", Decimal("50000"), Decimal("49000"), Decimal("49500"))

        assert len(fills) == 1
        fill = fills[0]
        assert fill.symbol == "BTC/USDT"
        assert fill.side == Side.LONG
        assert fill.quantity == Decimal("1.0")
        assert order.status == OrderStatus.FILLED
        assert order.filled_quantity == Decimal("1.0")
        assert order.avg_fill_price is not None

    def test_match_market_order_sell(self, broker: SimulatedBroker) -> None:
        """测试撮合卖单（市价单）"""
        # 先开仓
        buy_order = Order(
            symbol="BTC/USDT",
            side="buy",
            order_type="market",
            quantity=Decimal("1.0"),
            price=None,
            timestamp=datetime.now(timezone.utc),
        )
        broker.submit_order(buy_order)
        broker.match_orders("BTC/USDT", Decimal("50000"), Decimal("49000"), Decimal("49500"))

        # 平仓
        sell_order = Order(
            symbol="BTC/USDT",
            side="sell",
            order_type="market",
            quantity=Decimal("1.0"),
            price=None,
            timestamp=datetime.now(timezone.utc),
        )
        broker.submit_order(sell_order)
        fills = broker.match_orders("BTC/USDT", Decimal("50000"), Decimal("49000"), Decimal("49500"))

        assert len(fills) == 1
        fill = fills[0]
        assert fill.symbol == "BTC/USDT"
        assert fill.side == Side.SHORT
        assert fill.quantity == Decimal("1.0")
        assert sell_order.status == OrderStatus.FILLED

    def test_match_limit_order(self, broker: SimulatedBroker) -> None:
        """测试撮合限价单"""
        # 买单 - 限价单在低点以下成交
        order = Order(
            symbol="BTC/USDT",
            side="buy",
            order_type="limit",
            quantity=Decimal("1.0"),
            price=Decimal("49500"),
            timestamp=datetime.now(timezone.utc),
        )

        broker.submit_order(order)
        fills = broker.match_orders("BTC/USDT", Decimal("50000"), Decimal("49000"), Decimal("49500"))

        assert len(fills) == 1

        # 卖单 - 限价单在收盘价或更低成交
        order2 = Order(
            symbol="BTC/USDT",
            side="sell",
            order_type="limit",
            quantity=Decimal("1.0"),
            price=Decimal("49500"),
            timestamp=datetime.now(timezone.utc),
        )

        broker.submit_order(order2)
        # 需要更高的 high 才能触发限价卖单成交
        fills2 = broker.match_orders("BTC/USDT", Decimal("50000"), Decimal("49000"), Decimal("49500"))

        assert len(fills2) == 1

    def test_cancel_order(self, broker: SimulatedBroker) -> None:
        """测试取消订单"""
        order = Order(
            symbol="BTC/USDT",
            side="buy",
            order_type="limit",
            quantity=Decimal("1.0"),
            price=Decimal("48000"),
            timestamp=datetime.now(timezone.utc),
        )

        broker.submit_order(order)
        assert order.is_open is True

        result = broker.cancel_order(order.id)
        assert result is True
        assert order.status == OrderStatus.CANCELLED
        assert order.is_open is False
        assert order.id not in broker.open_orders["BTC/USDT"]

    def test_get_balance(self, broker: SimulatedBroker) -> None:
        """测试获取余额"""
        balance = broker.get_balance()
        assert balance == Decimal("10000")

    def test_position_tracking(self, broker: SimulatedBroker) -> None:
        """测试仓位跟踪"""
        # 开仓
        order = Order(
            symbol="BTC/USDT",
            side="buy",
            order_type="market",
            quantity=Decimal("1.0"),
            price=None,
            timestamp=datetime.now(timezone.utc),
        )

        broker.submit_order(order)
        broker.match_orders("BTC/USDT", Decimal("50000"), Decimal("49000"), Decimal("49500"))

        position = broker.get_position("BTC/USDT")
        assert position is not None
        assert position.symbol == "BTC/USDT"
        assert position.side == Side.LONG
        assert position.quantity == Decimal("1.0")


class TestBacktestEngine:
    """Test cases for BacktestEngine."""

    @pytest.fixture
    def engine(self) -> BacktestEngine:
        """Create backtest engine."""
        return BacktestEngine(
            initial_balance=Decimal("10000"),
            slippage=Decimal("0.0005"),
            commission=Decimal("0.0004"),
        )

    @pytest.fixture
    def sample_bars(self) -> list[BarData]:
        """Create sample bar data."""
        base_time = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        bars = []
        for i in range(100):
            bars.append(
                BarData(
                    symbol="BTC/USDT",
                    timestamp=base_time + timedelta(minutes=i * 15),
                    open=Decimal("49500") + Decimal(i * 10),
                    high=Decimal("50000") + Decimal(i * 10),
                    low=Decimal("49000") + Decimal(i * 10),
                    close=Decimal("49500") + Decimal(i * 10),
                    volume=Decimal("100"),
                )
            )
        return bars

    def test_load_data(self, engine: BacktestEngine, sample_bars: list[BarData]) -> None:
        """测试加载数据"""
        engine.load_data(sample_bars)

        assert engine.data_repo is not None
        bars = engine.data_repo._bars.get("BTC/USDT", [])
        assert len(bars) == 100

    def test_set_strategy(self, engine: BacktestEngine) -> None:
        """测试设置策略"""

        def simple_strategy(bar: BarData) -> None:
            pass

        engine.set_strategy(simple_strategy)
        assert engine.strategy is not None

    def test_run_backtest(self, engine: BacktestEngine, sample_bars: list[BarData]) -> None:
        """测试运行回测"""

        def simple_strategy(bar: BarData) -> None:
            # 简单策略：第一根 K 线买入，第 50 根 K 线卖出
            if bar.timestamp.day == 1 and bar.timestamp.hour == 0:
                # 买入
                order = Order(
                    symbol="BTC/USDT",
                    side="buy",
                    order_type="market",
                    quantity=Decimal("1.0"),
                    price=None,
                    timestamp=bar.timestamp,
                )
                broker = simple_strategy.__dict__["broker"]
                broker.submit_order(order)
            elif bar.timestamp.day == 1 and bar.timestamp.hour == 12:
                # 卖出
                position = simple_strategy.__dict__["broker"].get_position("BTC/USDT")
                if position:
                    order = Order(
                        symbol="BTC/USDT",
                        side="sell",
                        order_type="market",
                        quantity=position.quantity,
                        price=None,
                        timestamp=bar.timestamp,
                    )
                    broker = simple_strategy.__dict__["broker"]
                    broker.submit_order(order)

        engine.load_data(sample_bars)
        engine.set_strategy(simple_strategy)

        results = engine.run("BTC/USDT")

        assert "initial_balance" in results
        assert "final_balance" in results
        assert "total_return" in results
        assert "total_trades" in results
        assert "equity_curve" in results
        assert len(results["equity_curve"]) == 100

    def test_on_bar_callback(self, engine: BacktestEngine, sample_bars: list[BarData]) -> None:
        """测试 K 线回调"""
        callback_calls = []

        def callback(bar: BarData) -> None:
            callback_calls.append(bar.timestamp)

        engine.add_on_bar_callback(callback)
        engine.load_data(sample_bars)

        def simple_strategy(bar: BarData) -> None:
            pass

        engine.set_strategy(simple_strategy)
        engine.run("BTC/USDT")

        assert len(callback_calls) == 100

    def test_error_handling(self, engine: BacktestEngine, sample_bars: list[BarData]) -> None:
        """测试错误处理"""
        error_events = []

        def error_handler(event) -> None:
            if event.type == EventType.ERROR:
                error_events.append(event)

        engine.event_bus.subscribe(EventType.ERROR, error_handler)

        def failing_strategy(bar: BarData) -> None:
            raise ValueError("Test error")

        engine.load_data(sample_bars)
        engine.set_strategy(failing_strategy)
        engine.run("BTC/USDT")

        assert len(error_events) > 0
        assert "Test error" in error_events[0].data["error"]
