# AI 集成指南

## 概述

Trader 系统采用混合架构设计，AI 只负责策略参数调整，不直接下单交易。这种设计在保持 AI 智能的同时，确保了交易的安全性和可控性。

## 架构设计

### 混合架构优势

```
┌─────────────────────────────────────────┐
│           市场数据流                      │
└──────────────┬──────────────────────────┘
               │
┌──────────────▼──────────────────────────┐
│     规则型交易策略（可信核心）           │
│  - 信号生成                               │
│  - 订单执行                               │
│  - 风险控制                               │
└──────────────┬──────────────────────────┘
               │
┌──────────────▼──────────────────────────┐
│     AI 增强层（参数调整）                │
│  - 市场观察                               │
│  - 参数优化建议                           │
│  - 风险管理调整                           │
└──────────────────────────────────────────┘
```

### 安全边界

- **AI 不能直接下单**：所有交易通过规则型策略执行
- **参数范围限制**：AI 调整的参数有安全边界检查
- **人工可干预**：任何 AI 决策都可以被人工覆写

## AI 代理基础

### 创建 AI 代理

```python
from trader.ai.agent import AIAgent
from trader.ai.strategy_params import RiskLevel, StrategyParams

# 创建基础 AI 代理
agent = AIAgent(name="My Trading Agent")

# 使用自定义参数初始化
custom_params = StrategyParams(
    strategy_id="custom",
    risk_level=RiskLevel.MODERATE,
    max_position_size=Decimal("0.1"),
    leverage=2,
    stop_loss_pct=Decimal("0.03"),
    take_profit_pct=Decimal("0.08")
)

agent = AIAgent(strategy_params=custom_params)
```

### 内置工具

AI 代理内置了以下工具：

#### 1. 获取市场状态

```python
# 获取市场状态
market_state = agent.get_market_state(
    symbol="BTC/USDT",
    indicators=["sma", "rsi", "atr"]
)

print(market_state)
# {
#   "symbol": "BTC/USDT",
#   "timestamp": "...",
#   "indicators": {
#     "sma_10": 50000,
#     "rsi_14": 55,
#     "atr_14": 800
#   }
# }
```

#### 2. 获取仓位信息

```python
# 获取所有仓位
position_info = agent.get_position()

# 获取特定仓位
position_info = agent.get_position(symbol="BTC/USDT")

print(position_info)
# {
#   "has_position": true,
#   "positions": [
#     {
#       "symbol": "BTC/USDT",
#       "side": "long",
#       "quantity": 0.1,
#       "unrealized_pnl": 500
#     }
#   ]
# }
```

#### 3. 调整策略参数

```python
# 调整策略参数
new_params = agent.update_strategy_params(
    strategy_id="adjusted",
    risk_level=RiskLevel.AGGRESSIVE,
    max_position_size=Decimal("0.15"),
    leverage=3,
    reasoning="Market volatility increased, adjusting for higher risk tolerance"
)

print(f"New risk level: {new_params.risk_level}")
print(f"New leverage: {new_params.leverage}")
```

## Function Calling 集成

### OpenAI 格式

```python
from trader.ai.agent import AIAgent
from openai import OpenAI

# 初始化
agent = AIAgent()
client = OpenAI(api_key="your-key")

# 获取工具定义
tools = agent.get_tool_definitions()

# 调用 LLM
response = client.chat.completions.create(
    model="gpt-4",
    messages=[
        {
            "role": "system",
            "content": "You are a trading strategy advisor. Use the provided tools to analyze the market and adjust strategy parameters."
        },
        {
            "role": "user",
            "content": "Analyze the current BTC/USDT market and suggest strategy adjustments."
        }
    ],
    tools=tools
)

# 执行工具调用
if response.choices[0].message.tool_calls:
    for tool_call in response.choices[0].message.tool_calls:
        result = agent.execute_tool_call(
            tool_name=tool_call.function.name,
            arguments=json.loads(tool_call.function.arguments)
        )
        print(result)
```

### DeepSeek 集成

```python
import os
from openai import OpenAI

# DeepSeek 兼容 OpenAI API
client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com/v1"
)

agent = AIAgent()
tools = agent.get_tool_definitions()

response = client.chat.completions.create(
    model="deepseek-chat",
    messages=[...],
    tools=tools
)
```

## 创建 AI 增强策略

### 基础 AI 增强策略

```python
from trader.application.strategies.ai_enhanced import AIEnhancedStrategy
from trader.application.backtest_engine import BacktestEngine
from decimal import Decimal

# 创建 AI 增强策略
strategy = AIEnhancedStrategy(
    fast_period=10,
    slow_period=20
)

# 创建回测引擎
engine = BacktestEngine(
    initial_balance=Decimal("10000")
)

# 加载数据
# ...

# 设置并运行
engine.set_strategy(strategy)
results = engine.run("BTC/USDT")
```

### 自定义 AI 增强策略

```python
from trader.application.strategy import BaseStrategy
from trader.ai.agent import AIAgent
from trader.ai.strategy_params import StrategyParams, RiskLevel
from trader.infrastructure.data_repository import BarData
from datetime import timedelta


class CustomAIStrategy(BaseStrategy):
    """自定义 AI 增强策略"""
    
    def __init__(
        self,
        ai_agent: AIAgent = None,
        ai_update_interval: int = 24  # 每 24 小时更新一次
    ):
        super().__init__()
        self.ai_agent = ai_agent or AIAgent()
        self.ai_update_interval = ai_update_interval
        self.last_ai_update = None
        self.current_params = StrategyParams.default()
        
        # 策略状态
        self.price_history = []
        
        # 注册参数更新回调
        self.ai_agent.on_params_updated = self._on_params_updated
    
    def _on_params_updated(self, params: StrategyParams) -> None:
        """参数更新回调"""
        self.current_params = params
        print(f"Strategy parameters updated: {params.risk_level}")
    
    def on_bar(self, bar: BarData) -> None:
        """K 线回调"""
        self.price_history.append(bar.close)
        
        # 定期让 AI 观察并调整参数
        if (self.last_ai_update is None or 
            bar.timestamp - self.last_ai_update > timedelta(hours=self.ai_update_interval)):
            self._update_from_ai(bar)
            self.last_ai_update = bar.timestamp
        
        # 使用当前参数进行交易（规则型）
        self._execute_trading_logic(bar)
    
    def _update_from_ai(self, bar: BarData) -> None:
        """从 AI 获取更新"""
        # AI 观察市场
        observation = self.ai_agent.observe(
            symbol=bar.symbol,
            price_history=self.price_history[-100:],
            current_params=self.current_params
        )
        
        # AI 推理并调整（通常结合 LLM）
        # 这里可以集成 LLM 调用
        pass
    
    def _execute_trading_logic(self, bar: BarData) -> None:
        """执行实际交易逻辑（规则型，非 AI）"""
        if not self.broker:
            return
        
        # 使用当前参数进行交易
        position_size = self.current_params.max_position_size
        stop_loss = self.current_params.stop_loss_pct
        
        # 这里实现你的规则型交易策略
        # ...
```

## AI 决策流程

### Reflexion Loop 架构

系统实现了 Reflexion 循环，包含四个阶段：

```
Observe（观察） → Reason（推理） → Act（行动） → Execute（执行）
    ↑                                                      │
    └──────────────────────────────────────────────────────┘
```

### 实现自定义 Reflexion

```python
from trader.ai.reflexion import ReflexionLoop

class CustomReflexion(ReflexionLoop):
    """自定义反思循环"""
    
    def observe(self, context: dict) -> dict:
        """观察阶段 - 收集市场信息"""
        return {
            "market_state": self._get_market_state(context),
            "position_info": self._get_position_info(context),
            "recent_performance": self._get_performance(context)
        }
    
    def reason(self, observation: dict) -> dict:
        """推理阶段 - 分析并决策"""
        # 可以调用 LLM 进行推理
        reasoning = self._call_llm_for_reasoning(observation)
        return {
            "adjustments": reasoning.get("adjustments", []),
            "confidence": reasoning.get("confidence", 0.5)
        }
    
    def act(self, reasoning: dict) -> dict:
        """行动阶段 - 生成操作"""
        if reasoning["confidence"] > 0.7:
            return {
                "action": "adjust_params",
                "params": reasoning["adjustments"]
            }
        return {"action": "wait"}
    
    def execute(self, action: dict) -> bool:
        """执行阶段 - 应用操作"""
        if action["action"] == "adjust_params":
            self.agent.update_strategy_params(**action["params"])
            return True
        return False
```

## 测试 AI 集成

### 工具调用测试

```python
import pytest
from trader.ai.agent import AIAgent


def test_all_tools():
    """测试所有工具调用"""
    agent = AIAgent()
    
    # 测试 get_market_state
    state = agent.get_market_state(symbol="BTC/USDT")
    assert state["symbol"] == "BTC/USDT"
    
    # 测试 get_position
    pos = agent.get_position()
    assert "has_position" in pos
    
    # 测试 adjust_strategy_params
    new_params = agent.update_strategy_params(
        risk_level="aggressive",
        reasoning="Test"
    )
    assert new_params.risk_level == "aggressive"


def test_tool_execution():
    """测试工具执行器"""
    agent = AIAgent()
    
    result = agent.execute_tool_call(
        tool_name="get_market_state",
        arguments={"symbol": "ETH/USDT"}
    )
    assert "error" not in result
    
    result = agent.execute_tool_call(
        tool_name="unknown_tool",
        arguments={}
    )
    assert "error" in result
```

## 最佳实践

### 1. 安全第一

```python
# 始终验证参数范围
def safe_update_params(agent, **kwargs):
    """安全地更新参数"""
    # 检查杠杆上限
    if "leverage" in kwargs and kwargs["leverage"] > 10:
        kwargs["leverage"] = 10  # 强制上限
    
    # 检查止损下限
    if "stop_loss_pct" in kwargs and kwargs["stop_loss_pct"] < 0.01:
        kwargs["stop_loss_pct"] = 0.01  # 最小 1%
    
    return agent.update_strategy_params(**kwargs)
```

### 2. 渐进式调整

```python
# 避免剧烈的参数变化
def gradual_adjustment(agent, target_params, steps=5):
    """渐进式调整参数"""
    current = agent.strategy_params
    
    for i in range(steps):
        # 逐步调整
        blend = (i + 1) / steps
        new_risk = blend_risk(current.risk_level, target_params.risk_level, blend)
        
        agent.update_strategy_params(risk_level=new_risk)
        time.sleep(3600)  # 间隔 1 小时
```

### 3. 监控与回测

```python
# 记录所有 AI 决策
import json
from datetime import datetime

class AIDecisionLogger:
    """AI 决策日志记录器"""
    
    def __init__(self, log_file="ai_decisions.jsonl"):
        self.log_file = log_file
    
    def log_decision(self, observation, reasoning, action, result):
        """记录决策"""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "observation": observation,
            "reasoning": reasoning,
            "action": action,
            "result": result
        }
        
        with open(self.log_file, "a") as f:
            f.write(json.dumps(entry) + "\n")
```

## 故障排除

### AI 调用失败

```python
# 重试机制
import time
from functools import wraps

def ai_retry(max_attempts=3, delay=1):
    """AI 调用重试装饰器"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_attempts - 1:
                        raise
                    print(f"AI call failed, retrying ({attempt + 1}/{max_attempts}): {e}")
                    time.sleep(delay * (attempt + 1))
        return wrapper
    return decorator
```

## 下一步

- 查看 [策略开发指南](strategy_dev.md) 了解如何创建策略
- 阅读 [API 文档](api.md) 获取完整的 API 参考
- 查看示例代码了解更多用法
