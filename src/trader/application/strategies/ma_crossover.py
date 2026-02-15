"""Moving Average Crossover Strategy"""
from datetime import datetime
from decimal import Decimal
from typing import List
from ..strategy import BaseStrategy
from ...infrastructure.data_repository import BarData
from ..order import Order


class MovingAverageCrossover(BaseStrategy):
    """Moving Average Crossover Strategy
    
    - Fast MA > Slow MA and no position -> Open long
    - Fast MA < Slow MA and holding long -> Close long
    """
    
    def __init__(
        self,
        fast_period: int = 10,
        slow_period: int = 20,
        position_size: float = 0.01
    ):
        super().__init__("MA Crossover")
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.position_size = position_size
        self.bar_history: List[BarData] = []
    
    def on_bar(self, bar: BarData) -> None:
        # Save historical data
        self.bar_history.append(bar)
        
        # Keep sufficient historical data
        if len(self.bar_history) > self.slow_period + 10:
            self.bar_history.pop(0)
        
        # Need enough data to calculate MA
        if len(self.bar_history) < self.slow_period:
            return
        
        # Calculate fast MA
        fast_ma = self._calculate_sma(self.fast_period)
        
        # Calculate slow MA
        slow_ma = self._calculate_sma(self.slow_period)
        
        # Get current position
        position = self.broker.get_position(bar.symbol)
        
        # Generate trading signals
        if fast_ma > slow_ma:
            # Golden cross, bullish
            if position is None:
                # No position, open long
                self.create_market_order(
                    symbol=bar.symbol,
                    side="buy",
                    quantity=self.position_size
                )
        elif fast_ma < slow_ma:
            # Death cross, bearish
            if position is not None and position.side.value == "LONG":
                # Holding long position, close long
                self.create_market_order(
                    symbol=bar.symbol,
                    side="sell",
                    quantity=float(position.quantity)
                )
    
    def _calculate_sma(self, period: int) -> Decimal:
        """Calculate Simple Moving Average"""
        recent_bars = self.bar_history[-period:]
        sum_price = sum(bar.close for bar in recent_bars)
        return sum_price / Decimal(str(period))
    
    def on_funding_rate(self, rate: Decimal, timestamp: datetime) -> None:
        """资金费率回调实现"""
        # 记录资金费率变化（可用于策略决策）
        pass
    
    def on_order_update(self, order: Order) -> None:
        """订单更新回调实现"""
        # 记录订单状态变化
        pass
    
    def generate_signals(self, bar: BarData) -> List[dict]:
        """信号生成接口实现"""
        signals = []
        
        # 保存历史数据
        self.bar_history.append(bar)
        
        # 保持足够的历史数据
        if len(self.bar_history) > self.slow_period + 10:
            self.bar_history.pop(0)
        
        # 需要足够的数据计算均线
        if len(self.bar_history) < self.slow_period:
            return signals
        
        # 计算均线
        fast_ma = self._calculate_sma(self.fast_period)
        slow_ma = self._calculate_sma(self.slow_period)
        
        # 生成信号
        if fast_ma > slow_ma:
            # 金叉信号
            signals.append({
                "type": "entry",
                "symbol": bar.symbol,
                "side": "buy",
                "quantity": self.position_size,
                "price": float(bar.close)
            })
        elif fast_ma < slow_ma:
            # 死叉信号
            signals.append({
                "type": "exit",
                "symbol": bar.symbol,
                "side": "sell",
                "quantity": self.position_size,
                "price": float(bar.close)
            })
        
        return signals
