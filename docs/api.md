# API 文档

## 概述

本文档描述了 Trader 系统的核心 API 接口和主要类的使用方法。

## 目录结构

```
trader/
├── domain/              # 领域层
│   ├── position.py    # 仓位聚合根
│   ├── value_objects.py  # 值对象
│   └── services.py   # 领域服务
├── infrastructure/    # 基础设施层
│   ├── clock.py       # 时钟抽象
│   ├── event_bus.py   # 事件总线
│   ├── data_repository.py  # 数据仓库
│   └── data_downloader.py  # 数据下载器
├── application/     # 应用层
│   ├── backtest_engine.py  # 回测引擎
│   ├── simulated_broker.py  # 模拟券商
│   ├── order.py        # 订单管理
│   └── strategy.py     # 策略基类
└── ai/              # AI 层
    ├── agent.py        # AI 代理
    ├── tools.py        # 工具定义
    └── strategy_params.py  # 策略参数
```

## 领域层 API

### Position (仓位聚合根)

```python
from trader.domain.position import Position
from decimal import Decimal
from datetime import datetime, timezone

# 创建仓位
position = Position(
    symbol="BTC/USDT",
    side="long",
    entry_price=Decimal("50000"),
    quantity=Decimal("1.0"),
    leverage=1,
    timestamp=datetime.now(timezone.utc)
)

# 加仓
position.increase(
    price=Decimal("51000"),
    quantity=Decimal("0.5"),
    timestamp=datetime.now(timezone.utc)
)

# 减仓
realized_pnl = position.decrease(
    price=Decimal("52000"),
    quantity=Decimal("0.3"),
    timestamp=datetime.now(timezone.utc)
)

# 计算未结盈亏
unrealized_pnl = position.calculate_unrealized_pnl(Decimal("53000"))

# 更新清算价格
position.update_liquidation_price()
```

### 值对象

```python
from trader.domain.value_objects import (
    Side,
    OrderType,
    FundingInfo,
    TradeFill
)
from decimal import Decimal
from datetime import datetime, timezone

# 买卖方向
side = Side.LONG  # 或 Side.SHORT

# 订单类型
order_type = OrderType.MARKET  # 或 OrderType.LIMIT

# 资金费率信息
funding = FundingInfo(
    symbol="BTC/USDT",
    rate=Decimal("0.0001"),
    timestamp=datetime.now(timezone.utc)
)

# 成交明细
fill = TradeFill(
    symbol="BTC/USDT",
    side=Side.LONG,
    price=Decimal("50000"),
    quantity=Decimal("1.0"),
    commission=Decimal("20"),
    timestamp=datetime.now(timezone.utc)
)
```

## 基础设施层 API

### 时钟抽象

```python
from trader.infrastructure.clock import IClock, BacktestClock, RealtimeClock

# 实时时钟
realtime_clock = RealtimeClock()
current_time = realtime_clock.now()

# 回测时钟（可控制）
backtest_clock = BacktestClock()
backtest_clock.set_time(datetime(2024, 1, 1, tzinfo=timezone.utc))
backtest_clock.advance(timedelta(hours=1))
```

### 事件总线

```python
from trader.infrastructure.event_bus import EventBus, EventType, Event

event_bus = EventBus()

# 订阅事件
def handler(event):
    print(f"Received event: {event.type}")

event_bus.subscribe(EventType.MARKET_DATA, handler)

# 发布事件
event = Event(
    type=EventType.MARKET_DATA,
    data={"symbol": "BTC/USDT"},
    timestamp=datetime.now(timezone.utc)
)
event_bus.publish(event)
```

### 数据仓库

```python
from trader.infrastructure.data_repository import (
    IDataRepository,
    InMemoryDataRepository,
    BarData,
    FundingRateData
)

repo = InMemoryDataRepository()

# 添加 K 线数据
bar = BarData(
    symbol="BTC/USDT",
    timestamp=datetime.now(timezone.utc),
    open=Decimal("50000"),
    high=Decimal("50100"),
    low=Decimal("49900"),
    close=Decimal("50050"),
    volume=Decimal("100")
)
repo.add_bar(bar)

# 添加资金费率数据
funding = FundingRateData(
    symbol="BTC/USDT",
    timestamp=datetime.now(timezone.utc),
    rate=Decimal("0.0001")
)
repo.add_funding_rate(funding)

# 获取数据
bars = repo.get_bars("BTC/USDT")
funding_rates = repo.get_funding_rates("BTC/USDT")
```

### 数据下载器

```python
from trader.infrastructure.data_downloader import DataDownloader
from datetime import datetime, timedelta, timezone

downloader = DataDownloader()

# 下载 K 线数据
end_date = datetime.now(timezone.utc)
start_date = end_date - timedelta(days=30)

bars = downloader.download_ohlcv(
    symbol="BTC/USDT",
    exchange="binance",
    start_date=start_date,
    end_date=end_date,
    timeframe="1h"
)

# 下载资金费率数据
funding_rates = downloader.download_funding_rates(
    symbol="BTC/USDT",
    exchange="binance",
    start_date=start_date,
    end_date=end_date
)
```

## 应用层 API

### 回测引擎

```python
from trader.application.backtest_engine import BacktestEngine
from trader.application.strategies.ma_crossover import MovingAverageCrossover
from decimal import Decimal

# 创建回测引擎
engine = BacktestEngine(
    initial_balance=Decimal("10000"),
    slippage=Decimal("0.0005"),
    commission=Decimal("0.0004")
)

# 下载或加载数据
engine.download_data(
    symbol="BTC/USDT",
    start_date=start_date,
    end_date=end_date,
    timeframe="1h",
    exchange="binance"
)

# 创建策略
strategy = MovingAverageCrossover(
    fast_period=10,
    slow_period=20,
    position_size=Decimal("0.001")
)

# 设置策略并运行回测
engine.set_strategy(strategy)
results = engine.run("BTC/USDT")

# 查看结果
print(f"初始资金: ${results['initial_balance']:.2f}")
print(f"最终资金: ${results['final_balance']:.2f}")
print(f"收益率: {results['total_return']:.2f}%")
print(f"交易次数: {results['total_trades']}")
```

### 模拟券商

```python
from trader.application.simulated_broker import SimulatedBroker
from trader.application.order import Order
from trader.infrastructure.clock import BacktestClock
from trader.infrastructure.event_bus import EventBus
from decimal import Decimal

clock = BacktestClock()
event_bus = EventBus()

broker = SimulatedBroker(
    clock=clock,
    event_bus=event_bus,
    initial_balance=Decimal("10000"),
    slippage_rate=Decimal("0.0005"),
    commission_rate=Decimal("0.0004")
)

# 提交订单
order = Order(
    symbol="BTC/USDT",
    side="buy",
    order_type="market",
    quantity=Decimal("0.1"),
    timestamp=clock.now()
)
broker.submit_order(order)

# 撮合订单
fills = broker.match_orders(
    symbol="BTC/USDT",
    high=Decimal("50100"),
    low=Decimal("49900"),
    close=Decimal("50000")
)

# 获取余额
balance = broker.get_balance()

# 获取仓位
position = broker.get_position("BTC/USDT")
```

## AI 层 API

### AI 代理

```python
from trader.ai.agent import AIAgent
from trader.ai.strategy_params import RiskLevel

# 创建 AI 代理
agent = AIAgent(name="Trading Agent")

# 获取市场状态
market_state = agent.get_market_state(symbol="BTC/USDT")

# 获取仓位信息
position_info = agent.get_position(symbol="BTC/USDT")

# 调整策略参数
new_params = agent.update_strategy_params(
    risk_level=RiskLevel.AGGRESSIVE,
    reasoning="Market conditions warrant aggressive approach"
)

# 获取工具定义（OpenAI 格式）
tool_defs = agent.get_tool_definitions()

# 执行工具调用
result = agent.execute_tool_call(
    tool_name="get_market_state",
    arguments={"symbol": "ETH/USDT"}
)
```

### 策略参数

```python
from trader.ai.strategy_params import StrategyParams, RiskLevel

# 默认参数
params = StrategyParams.default()

# 从风险等级创建
conservative = StrategyParams.from_risk_level(RiskLevel.CONSERVATIVE)
moderate = StrategyParams.from_risk_level(RiskLevel.MODERATE)
aggressive = StrategyParams.from_risk_level(RiskLevel.AGGRESSIVE)

# 自定义参数
custom = StrategyParams(
    strategy_id="custom",
    risk_level=RiskLevel.MODERATE,
    max_position_size=Decimal("0.15"),
    leverage=3,
    stop_loss_pct=Decimal("0.05"),
    take_profit_pct=Decimal("0.10")
)
```

### AI 增强策略

```python
from trader.application.strategies.ai_enhanced import AIEnhancedStrategy

# 创建 AI 增强策略
strategy = AIEnhancedStrategy(
    fast_period=10,
    slow_period=20
)

# 策略会自动使用 AI 代理调整参数，但 AI 只能调整参数，不能直接下单
# 交易逻辑保持规则型，确保安全性高
```
