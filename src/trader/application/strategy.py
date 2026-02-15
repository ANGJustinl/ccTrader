"""Strategy base class for trading strategies"""
from abc import ABC, abstractmethod
from datetime import datetime
from decimal import Decimal
from typing import Optional, List
from ..infrastructure.data_repository import BarData
from .order import Order


class BaseStrategy(ABC):
    """Strategy base class"""
    
    def __init__(self, name: str = "BaseStrategy"):
        self.name = name
        self.broker = None  # Injected by backtest engine
        self.clock = None   # Injected by backtest engine
        self.event_bus = None  # Injected by backtest engine
        self.trading_enabled = True  # Enable/disable order submission
    
    @abstractmethod
    def on_bar(self, bar: BarData) -> None:
        """Bar callback"""
        pass
    
    def on_start(self) -> None:
        """Called when strategy starts"""
        pass
    
    def on_stop(self) -> None:
        """Called when strategy stops"""
        pass
    
    def on_funding_rate(self, rate: Decimal, timestamp: datetime) -> None:
        """资金费率回调"""
        pass
    
    def on_order_update(self, order: Order) -> None:
        """订单更新回调"""
        pass
    
    def generate_signals(self, bar: BarData) -> List[dict]:
        """信号生成接口
        
        Returns:
            List of signal dicts with keys: type, symbol, side, quantity, price
        """
        return []
    
    def create_market_order(
        self,
        symbol: str,
        side: str,
        quantity: float
    ) -> Optional[Order]:
        """Create market order"""
        if not self.trading_enabled:
            print(f"[Strategy] Trading disabled, skipping order: {side} {quantity} {symbol}")
            return None
            
        order = Order(
            symbol=symbol,
            side=side,
            order_type="market",
            quantity=quantity,
            timestamp=self.clock.now()
        )
        self.broker.submit_order(order)
        return order
    
    def create_limit_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float
    ) -> Optional[Order]:
        """Create limit order"""
        if not self.trading_enabled:
            print(f"[Strategy] Trading disabled, skipping order: {side} {quantity} {symbol} @ {price}")
            return None
            
        order = Order(
            symbol=symbol,
            side=side,
            order_type="limit",
            quantity=quantity,
            price=price,
            timestamp=self.clock.now()
        )
        self.broker.submit_order(order)
        return order
