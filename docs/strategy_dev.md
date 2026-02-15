# 策略开发指南

## 概述

本指南将帮助你开发自己的交易策略。Trader 系统采用灵活的策略架构，支持从简单的技术指标策略到复杂的 AI 增强策略。

## 策略基类

所有策略都应继承自 `BaseStrategy` 或遵循相同的接口模式。

### 基础接口

```python
from datetime import datetime
from decimal import Decimal
from typing import Optional, List

from trader.infrastructure.data_repository import BarData, FundingRateData
from trader.application.order import Order


class BaseStrategy:
    """策略基类 - 所有策略的基础接口"""
    
    def __init__(self):
        self.broker = None  # 会在 attach_backtest_engine 时设置
        self.backtest_engine = None
    
    def attach_backtest_engine(self, engine) -> None:
        """将策略附加到回测引擎"""
        self.backtest_engine = engine
        self.broker = engine.broker
    
    def on_bar(self, bar: BarData) -> None:
        """K 线回调 - 在每个新 K 线时调用"""
        pass
    
    def on_funding_rate(self, rate: Decimal, timestamp: datetime) -> None:
        """资金费率回调 - 在资金费率结算时调用"""
        pass
    
    def on_order_update(self, order: Order) -> None:
        """订单更新回调 - 在订单状态变化时调用"""
        pass
    
    def generate_signals(self, bar: BarData) -> List[dict]:
        """生成交易信号（可选）"""
        return []
```

## 创建简单策略

### 移动平均交叉策略示例

让我们创建一个经典的双均线交叉策略：

```python
from trader.application.strategy import BaseStrategy
from trader.infrastructure.data_repository import BarData
from trader.application.order import Order
from trader.utils.indicators import calculate_sma
from decimal import Decimal
from collections import deque


class MovingAverageCrossover(BaseStrategy):
    """双均线交叉策略"""
    
    def __init__(
        self,
        fast_period: int = 10,
        slow_period: int = 20,
        position_size: Decimal = Decimal("0.001")
    ):
        super().__init__()
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.position_size = position_size
        
        # 价格历史
        self.price_history = deque(maxlen=slow_period + 10)
        self.fast_ma_history = deque(maxlen=10)
        self.slow_ma_history = deque(maxlen=10)
    
    def on_bar(self, bar: BarData) -> None:
        """处理新的 K 线"""
        if not self.broker:
            return
        
        # 添加价格到历史
        self.price_history.append(bar.close)
        
        # 需要足够的数据点
        if len(self.price_history) < self.slow_period:
            return
        
        # 计算均线
        prices = list(self.price_history)
        fast_ma = calculate_sma(prices, self.fast_period)
        slow_ma = calculate_sma(prices, self.slow_period)
        
        self.fast_ma_history.append(fast_ma)
        self.slow_ma_history.append(slow_ma)
        
        # 需要至少两个数据点来判断交叉
        if len(self.fast_ma_history) < 2:
            return
        
        # 获取当前和前一个值
        prev_fast = self.fast_ma_history[-2]
        prev_slow = self.slow_ma_history[-2]
        curr_fast = self.fast_ma_history[-1]
        curr_slow = self.slow_ma_history[-1]
        
        # 获取当前仓位
        position = self.broker.get_position(bar.symbol)
        
        # 金叉：快速均线上穿慢速均线 -> 开多
        if prev_fast <= prev_slow and curr_fast > curr_slow:
            if not position:
                self._open_long(bar)
            elif position.side == "short":
                self._close_short(bar)
                self._open_long(bar)
        
        # 死叉：快速均线下穿慢速均线 -> 平多
        elif prev_fast >= prev_slow and curr_fast < curr_slow:
            if position and position.side == "long":
                self._close_long(bar)
    
    def _open_long(self, bar: BarData) -> None:
        """开多仓"""
        order = Order(
            symbol=bar.symbol,
            side="buy",
            order_type="market",
            quantity=self.position_size,
            timestamp=bar.timestamp
        )
        self.broker.submit_order(order)
    
    def _close_long(self, bar: BarData) -> None:
        """平多仓"""
        position = self.broker.get_position(bar.symbol)
        if position:
            order = Order(
                symbol=bar.symbol,
                side="sell",
                order_type="market",
                quantity=position.quantity,
                timestamp=bar.timestamp
            )
            self.broker.submit_order(order)
    
    def _open_short(self, bar: BarData) -> None:
        """开空仓"""
        order = Order(
            symbol=bar.symbol,
            side="sell",
            order_type="market",
            quantity=self.position_size,
            timestamp=bar.timestamp
        )
        self.broker.submit_order(order)
    
    def _close_short(self, bar: BarData) -> None:
        """平空仓"""
        position = self.broker.get_position(bar.symbol)
        if position:
            order = Order(
                symbol=bar.symbol,
                side="buy",
                order_type="market",
                quantity=position.quantity,
                timestamp=bar.timestamp
            )
            self.broker.submit_order(order)
    
    def generate_signals(self, bar: BarData) -> list[dict]:
        """生成信号列表（用于分析）"""
        signals = []
        if len(self.fast_ma_history) >= 2:
            prev_fast = self.fast_ma_history[-2]
            prev_slow = self.slow_ma_history[-2]
            curr_fast = self.fast_ma_history[-1]
            curr_slow = self.slow_ma_history[-1]
            
            if prev_fast <= prev_slow and curr_fast > curr_slow:
                signals.append({
                    "type": "golden_cross",
                    "timestamp": bar.timestamp,
                    "action": "buy"
                })
            elif prev_fast >= prev_slow and curr_fast < curr_slow:
                signals.append({
                    "type": "death_cross",
                    "timestamp": bar.timestamp,
                    "action": "sell"
                })
        
        return signals
```

## 高级策略开发

### RSI 策略

```python
from trader.utils.indicators import calculate_rsi


class RSIStrategy(BaseStrategy):
    """RSI 超买超卖策略"""
    
    def __init__(
        self,
        rsi_period: int = 14,
        oversold_threshold: Decimal = Decimal("30"),
        overbought_threshold: Decimal = Decimal("70"),
        position_size: Decimal = Decimal("0.001")
    ):
        super().__init__()
        self.rsi_period = rsi_period
        self.oversold_threshold = oversold_threshold
        self.overbought_threshold = overbought_threshold
        self.position_size = position_size
        self.price_history = deque(maxlen=rsi_period + 10)
    
    def on_bar(self, bar: BarData) -> None:
        if not self.broker:
            return
        
        self.price_history.append(bar.close)
        
        if len(self.price_history) < self.rsi_period:
            return
        
        rsi = calculate_rsi(list(self.price_history), self.rsi_period)
        position = self.broker.get_position(bar.symbol)
        
        # RSI 低于超卖线 -> 买入
        if rsi < self.oversold_threshold and not position:
            self._open_long(bar)
        
        # RSI 高于超买线 -> 卖出
        elif rsi > self.overbought_threshold and position:
            self._close_long(bar)
    
    # 省略辅助方法，参考前面的例子
```

### 结合多个指标

```python
from trader.utils.indicators import calculate_sma, calculate_rsi, calculate_atr


class MultiIndicatorStrategy(BaseStrategy):
    """多指标组合策略"""
    
    def __init__(self):
        super().__init__()
        self.price_history = deque(maxlen=100)
        self.high_history = deque(maxlen=100)
        self.low_history = deque(maxlen=100)
    
    def on_bar(self, bar: BarData) -> None:
        if not self.broker:
            return
        
        self.price_history.append(bar.close)
        self.high_history.append(bar.high)
        self.low_history.append(bar.low)
        
        if len(self.price_history) < 50:
            return
        
        prices = list(self.price_history)
        highs = list(self.high_history)
        lows = list(self.low_history)
        
        # 计算多个指标
        ma_short = calculate_sma(prices, 10)
        ma_long = calculate_sma(prices, 30)
        rsi = calculate_rsi(prices, 14)
        atr = calculate_atr(highs, lows, prices, 14)
        
        # 组合信号逻辑
        position = self.broker.get_position(bar.symbol)
        
        # 买入条件：短均线上穿长均线 + RSI < 40
        if (ma_short > ma_long and 
            rsi < 40 and 
            not position):
            self._open_long(bar)
        
        # 卖出条件：短均线下穿长均线 + RSI > 60
        elif (ma_short < ma_long and 
              rsi > 60 and 
              position):
            self._close_long(bar)
```

## 策略最佳实践

### 1. 风险控制

```python
class RiskControlledStrategy(BaseStrategy):
    """带风险控制的策略"""
    
    def __init__(
        self,
        max_position_pct: Decimal = Decimal("0.1"),  # 最大仓位 10%
        stop_loss_pct: Decimal = Decimal("0.02"),   # 止损 2%
        take_profit_pct: Decimal = Decimal("0.05")  # 止盈 5%
    ):
        super().__init__()
        self.max_position_pct = max_position_pct
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.entry_prices = {}  # 记录入场价格
    
    def _calculate_position_size(self, price: Decimal) -> Decimal:
        """计算合理的仓位大小"""
        balance = self.broker.get_balance()
        max_risk = balance * self.max_position_pct
        position_size = max_risk / price
        return position_size
    
    def _check_stop_loss_take_profit(self, bar: BarData) -> None:
        """检查止损止盈"""
        position = self.broker.get_position(bar.symbol)
        if not position:
            return
        
        entry_price = self.entry_prices.get(bar.symbol)
        if not entry_price:
            return
        
        pnl_pct = (bar.close - entry_price) / entry_price
        
        if position.side == "long":
            if pnl_pct <= -self.stop_loss_pct:
                # 止损
                self._close_long(bar)
            elif pnl_pct >= self.take_profit_pct:
                # 止盈
                self._close_long(bar)
```

### 2. 性能优化

```python
from functools import lru_cache
import numpy as np


class OptimizedStrategy(BaseStrategy):
    """性能优化的策略"""
    
    def __init__(self):
        super().__init__()
        self._price_array = None
        self._cache_invalid = True
    
    def on_bar(self, bar: BarData) -> None:
        # 使用 NumPy 数组提高计算速度
        if self._price_array is None:
            self._price_array = np.array([float(bar.close)])
        else:
            self._price_array = np.append(self._price_array, float(bar.close))
        
        self._cache_invalid = True
    
    @lru_cache(maxsize=1)
    def _calculate_indicators(self, array_len: int):
        """缓存指标计算"""
        # 计算逻辑...
        pass
```

### 3. 策略回测与验证

```python
def backtest_strategy(strategy_class, param_ranges):
    """参数网格搜索"""
    best_params = None
    best_sharpe = -float('inf')
    
    for fast in param_ranges['fast']:
        for slow in param_ranges['slow']:
            strategy = strategy_class(fast_period=fast, slow_period=slow)
            engine = BacktestEngine(...)
            # ... 运行回测
            
            if results['sharpe_ratio'] > best_sharpe:
                best_sharpe = results['sharpe_ratio']
                best_params = (fast, slow)
    
    return best_params, best_sharpe
```

## 测试你的策略

```python
import pytest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from trader.application.backtest_engine import BacktestEngine
from your_strategy import YourStrategy


def test_your_strategy():
    """测试你的策略"""
    engine = BacktestEngine(initial_balance=Decimal("10000"))
    
    # 生成测试数据或下载真实数据
    # ...
    
    strategy = YourStrategy()
    engine.set_strategy(strategy)
    
    results = engine.run("BTC/USDT")
    
    # 验证策略逻辑
    assert results['total_trades'] >= 0
    # 更多断言...
```

## 常见模式

### 趋势跟踪

- 移动平均交叉
- 布林带突破
- Donchian 通道突破

### 均值回归

- RSI 超买超卖
- 布林带回归
- 配对交易

### 波动率策略

- ATR 突破
- 波动率压缩/扩张
- 期权策略

## 下一步

- 查看 [AI 集成指南](ai_integration.md) 学习如何增强你的策略
- 参考示例策略代码
- 阅读 [API 文档](api.md) 了解更多细节
