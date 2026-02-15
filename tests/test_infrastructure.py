"""Unit tests for infrastructure layer components."""

import pytest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from trader.infrastructure.clock import IClock, RealtimeClock, BacktestClock
from trader.infrastructure.event_bus import EventBus, Event, EventType
from trader.infrastructure.data_repository import (
    BarData,
    FundingRateData,
    InMemoryDataRepository,
)


# ==================== Clock Tests ====================

class TestRealtimeClock:
    """测试 RealtimeClock"""
    
    def test_returns_current_time(self):
        """RealtimeClock 返回当前时间"""
        clock = RealtimeClock()
        now = clock.now()
        
        assert now.tzinfo is not None
        assert now.tzinfo == timezone.utc
    
    def test_cannot_set_time(self):
        """RealtimeClock 不支持设置时间"""
        clock = RealtimeClock()
        
        with pytest.raises(NotImplementedError):
            clock.set_time(datetime.now(timezone.utc))
    
    def test_cannot_advance_time(self):
        """RealtimeClock 不支持推进时间"""
        clock = RealtimeClock()
        
        with pytest.raises(NotImplementedError):
            clock.advance(60)


class TestBacktestClock:
    """测试 BacktestClock"""
    
    def test_initial_time_default(self):
        """默认初始时间为 2024-01-01"""
        clock = BacktestClock()
        
        assert clock.now() == datetime(2024, 1, 1, tzinfo=timezone.utc)
    
    def test_set_custom_initial_time(self):
        """设置自定义初始时间"""
        custom_time = datetime(2024, 6, 15, 10, 30, tzinfo=timezone.utc)
        clock = BacktestClock(initial_time=custom_time)
        
        assert clock.now() == custom_time
    
    def test_set_time(self):
        """设置时间"""
        clock = BacktestClock()
        new_time = datetime(2024, 3, 1, tzinfo=timezone.utc)
        
        clock.set_time(new_time)
        
        assert clock.now() == new_time
    
    def test_advance_time(self):
        """推进时间"""
        clock = BacktestClock()
        initial_time = clock.now()
        
        clock.advance(3600)  # Advance 1 hour
        
        assert clock.now() == initial_time + timedelta(hours=1)
    
    def test_advance_multiple_times(self):
        """多次推进时间"""
        clock = BacktestClock()
        
        clock.advance(60)  # 1 minute
        clock.advance(300)  # 5 minutes
        clock.advance(3600)  # 1 hour
        
        expected = datetime(2024, 1, 1, 1, 6, tzinfo=timezone.utc)
        assert clock.now() == expected
    
    def test_current_time_property(self):
        """current_time 属性返回当前时间"""
        clock = BacktestClock()
        
        assert clock.current_time == clock.now()


# ==================== EventBus Tests ====================

class TestEventBus:
    """测试 EventBus"""
    
    def test_subscribe_and_publish(self):
        """订阅和发布事件"""
        bus = EventBus()
        received_events = []
        
        def handler(event: Event):
            received_events.append(event)
        
        bus.subscribe(EventType.BAR, handler)
        
        event = Event(
            type=EventType.BAR,
            timestamp=datetime.now(timezone.utc),
            data={"symbol": "BTC/USDT"}
        )
        bus.publish(event)
        
        assert len(received_events) == 1
        assert received_events[0].type == EventType.BAR
        assert received_events[0].data["symbol"] == "BTC/USDT"
    
    def test_multiple_subscribers(self):
        """多个订阅者接收事件"""
        bus = EventBus()
        subscriber1_events = []
        subscriber2_events = []
        
        def handler1(event: Event):
            subscriber1_events.append(event)
        
        def handler2(event: Event):
            subscriber2_events.append(event)
        
        bus.subscribe(EventType.BAR, handler1)
        bus.subscribe(EventType.BAR, handler2)
        
        event = Event(
            type=EventType.BAR,
            timestamp=datetime.now(timezone.utc),
            data={"symbol": "BTC/USDT"}
        )
        bus.publish(event)
        
        assert len(subscriber1_events) == 1
        assert len(subscriber2_events) == 1
    
    def test_different_event_types(self):
        """不同类型的事件"""
        bus = EventBus()
        bar_events = []
        order_events = []
        
        def bar_handler(event: Event):
            bar_events.append(event)
        
        def order_handler(event: Event):
            order_events.append(event)
        
        bus.subscribe(EventType.BAR, bar_handler)
        bus.subscribe(EventType.ORDER_SUBMITTED, order_handler)
        
        bar_event = Event(
            type=EventType.BAR,
            timestamp=datetime.now(timezone.utc),
            data={"symbol": "BTC/USDT"}
        )
        order_event = Event(
            type=EventType.ORDER_SUBMITTED,
            timestamp=datetime.now(timezone.utc),
            data={"order_id": "123"}
        )
        
        bus.publish(bar_event)
        bus.publish(order_event)
        
        assert len(bar_events) == 1
        assert len(order_events) == 1
    
    def test_unsubscribe(self):
        """取消订阅"""
        bus = EventBus()
        received_events = []
        
        def handler(event: Event):
            received_events.append(event)
        
        bus.subscribe(EventType.BAR, handler)
        bus.unsubscribe(EventType.BAR, handler)
        
        event = Event(
            type=EventType.BAR,
            timestamp=datetime.now(timezone.utc),
            data={"symbol": "BTC/USDT"}
        )
        bus.publish(event)
        
        assert len(received_events) == 0
    
    def test_handler_exception_creates_error_event(self):
        """处理器异常会创建错误事件"""
        bus = EventBus()
        error_events = []
        
        def error_handler(event: Event):
            raise ValueError("Test error")
        
        def error_catcher(event: Event):
            if event.type == EventType.ERROR:
                error_events.append(event)
        
        bus.subscribe(EventType.BAR, error_handler)
        bus.subscribe(EventType.ERROR, error_catcher)
        
        event = Event(
            type=EventType.BAR,
            timestamp=datetime.now(timezone.utc),
            data={"symbol": "BTC/USDT"}
        )
        bus.publish(event)
        
        assert len(error_events) == 1
        assert error_events[0].type == EventType.ERROR
        assert "Test error" in error_events[0].data["error"]
    
    def test_clear_subscribers(self):
        """清空所有订阅"""
        bus = EventBus()
        received_events = []
        
        def handler(event: Event):
            received_events.append(event)
        
        bus.subscribe(EventType.BAR, handler)
        bus.clear()
        
        event = Event(
            type=EventType.BAR,
            timestamp=datetime.now(timezone.utc),
            data={"symbol": "BTC/USDT"}
        )
        bus.publish(event)
        
        assert len(received_events) == 0


# ==================== DataRepository Tests ====================

class TestInMemoryDataRepository:
    """测试 InMemoryDataRepository"""
    
    def test_save_and_get_bar(self):
        """保存和获取 BarData"""
        repo = InMemoryDataRepository()
        
        bar = BarData(
            symbol="BTC/USDT",
            timestamp=datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
            open=Decimal("50000"),
            high=Decimal("51000"),
            low=Decimal("49500"),
            close=Decimal("50500"),
            volume=Decimal("100")
        )
        
        repo.save_bar(bar)
        
        start_time = datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)
        end_time = datetime(2024, 1, 1, 23, 59, tzinfo=timezone.utc)
        bars = repo.get_bars("BTC/USDT", start_time, end_time)
        
        assert len(bars) == 1
        assert bars[0].symbol == "BTC/USDT"
        assert bars[0].close == Decimal("50500")
    
    def test_save_multiple_bars(self):
        """保存多个 BarData"""
        repo = InMemoryDataRepository()
        
        bar1 = BarData(
            symbol="BTC/USDT",
            timestamp=datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
            open=Decimal("50000"),
            high=Decimal("51000"),
            low=Decimal("49500"),
            close=Decimal("50500"),
            volume=Decimal("100")
        )
        
        bar2 = BarData(
            symbol="BTC/USDT",
            timestamp=datetime(2024, 1, 1, 10, 15, tzinfo=timezone.utc),
            open=Decimal("50500"),
            high=Decimal("52000"),
            low=Decimal("50000"),
            close=Decimal("51500"),
            volume=Decimal("150")
        )
        
        repo.save_bar(bar1)
        repo.save_bar(bar2)
        
        start_time = datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)
        end_time = datetime(2024, 1, 1, 23, 59, tzinfo=timezone.utc)
        bars = repo.get_bars("BTC/USDT", start_time, end_time)
        
        assert len(bars) == 2
    
    def test_time_range_filter(self):
        """时间范围过滤"""
        repo = InMemoryDataRepository()
        
        for i in range(3):
            bar = BarData(
                symbol="BTC/USDT",
                timestamp=datetime(2024, 1, 1, 10, i * 15, tzinfo=timezone.utc),
                open=Decimal(f"5000{i}0"),
                high=Decimal(f"5100{i}0"),
                low=Decimal(f"4950{i}0"),
                close=Decimal(f"5050{i}0"),
                volume=Decimal(str(100 + i * 10))
            )
            repo.save_bar(bar)
        
        # Get only middle bars (exclude first and last)
        start_time = datetime(2024, 1, 1, 10, 15, tzinfo=timezone.utc)
        end_time = datetime(2024, 1, 1, 10, 15, tzinfo=timezone.utc)
        bars = repo.get_bars("BTC/USDT", start_time, end_time)
        
        assert len(bars) == 1
        assert bars[0].timestamp == datetime(2024, 1, 1, 10, 15, tzinfo=timezone.utc)
    
    def test_different_symbols(self):
        """不同交易对的数据隔离"""
        repo = InMemoryDataRepository()
        
        btc_bar = BarData(
            symbol="BTC/USDT",
            timestamp=datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
            open=Decimal("50000"),
            high=Decimal("51000"),
            low=Decimal("49500"),
            close=Decimal("50500"),
            volume=Decimal("100")
        )
        
        eth_bar = BarData(
            symbol="ETH/USDT",
            timestamp=datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
            open=Decimal("3000"),
            high=Decimal("3100"),
            low=Decimal("2950"),
            close=Decimal("3050"),
            volume=Decimal("1000")
        )
        
        repo.save_bar(btc_bar)
        repo.save_bar(eth_bar)
        
        start_time = datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)
        end_time = datetime(2024, 1, 1, 23, 59, tzinfo=timezone.utc)
        
        btc_bars = repo.get_bars("BTC/USDT", start_time, end_time)
        eth_bars = repo.get_bars("ETH/USDT", start_time, end_time)
        
        assert len(btc_bars) == 1
        assert len(eth_bars) == 1
        assert btc_bars[0].close == Decimal("50500")
        assert eth_bars[0].close == Decimal("3050")
    
    def test_save_and_get_funding_rate(self):
        """保存和获取 FundingRateData"""
        repo = InMemoryDataRepository()
        
        rate = FundingRateData(
            symbol="BTC/USDT",
            rate=Decimal("0.0001"),
            timestamp=datetime(2024, 1, 1, 8, 0, tzinfo=timezone.utc),
            next_funding_time=datetime(2024, 1, 1, 16, 0, tzinfo=timezone.utc)
        )
        
        repo.save_funding_rate(rate)
        
        start_time = datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)
        end_time = datetime(2024, 1, 1, 23, 59, tzinfo=timezone.utc)
        rates = repo.get_funding_rates("BTC/USDT", start_time, end_time)
        
        assert len(rates) == 1
        assert rates[0].symbol == "BTC/USDT"
        assert rates[0].rate == Decimal("0.0001")
    
    def test_save_multiple_funding_rates(self):
        """保存多个 FundingRateData"""
        repo = InMemoryDataRepository()
        
        rate1 = FundingRateData(
            symbol="BTC/USDT",
            rate=Decimal("0.0001"),
            timestamp=datetime(2024, 1, 1, 8, 0, tzinfo=timezone.utc),
            next_funding_time=datetime(2024, 1, 1, 16, 0, tzinfo=timezone.utc)
        )
        
        rate2 = FundingRateData(
            symbol="BTC/USDT",
            rate=Decimal("0.0002"),
            timestamp=datetime(2024, 1, 1, 16, 0, tzinfo=timezone.utc),
            next_funding_time=datetime(2024, 1, 2, 0, 0, tzinfo=timezone.utc)
        )
        
        repo.save_funding_rate(rate1)
        repo.save_funding_rate(rate2)
        
        start_time = datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)
        end_time = datetime(2024, 1, 1, 23, 59, tzinfo=timezone.utc)
        rates = repo.get_funding_rates("BTC/USDT", start_time, end_time)
        
        assert len(rates) == 2
    
    def test_funding_rate_time_filter(self):
        """资金费率时间范围过滤"""
        repo = InMemoryDataRepository()
        
        # Create funding rates at different times
        rate1 = FundingRateData(
            symbol="BTC/USDT",
            rate=Decimal("0.0001"),
            timestamp=datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc),
            next_funding_time=datetime(2024, 1, 1, 8, 0, tzinfo=timezone.utc)
        )
        rate2 = FundingRateData(
            symbol="BTC/USDT",
            rate=Decimal("0.0002"),
            timestamp=datetime(2024, 1, 1, 8, 0, tzinfo=timezone.utc),
            next_funding_time=datetime(2024, 1, 1, 16, 0, tzinfo=timezone.utc)
        )
        rate3 = FundingRateData(
            symbol="BTC/USDT",
            rate=Decimal("0.0003"),
            timestamp=datetime(2024, 1, 1, 16, 0, tzinfo=timezone.utc),
            next_funding_time=datetime(2024, 1, 2, 0, 0, tzinfo=timezone.utc)
        )
        
        repo.save_funding_rate(rate1)
        repo.save_funding_rate(rate2)
        repo.save_funding_rate(rate3)
        
        # Get only middle rate
        start_time = datetime(2024, 1, 1, 8, 0, tzinfo=timezone.utc)
        end_time = datetime(2024, 1, 1, 8, 0, tzinfo=timezone.utc)
        rates = repo.get_funding_rates("BTC/USDT", start_time, end_time)
        
        assert len(rates) == 1
        assert rates[0].rate == Decimal("0.0002")
    
    def test_empty_symbol_returns_empty_list(self):
        """获取不存在的交易对返回空列表"""
        repo = InMemoryDataRepository()
        
        start_time = datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)
        end_time = datetime(2024, 1, 1, 23, 59, tzinfo=timezone.utc)
        
        bars = repo.get_bars("NONEXISTENT/USDT", start_time, end_time)
        rates = repo.get_funding_rates("NONEXISTENT/USDT", start_time, end_time)
        
        assert len(bars) == 0
        assert len(rates) == 0
