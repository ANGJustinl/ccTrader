# **工程深化报告：基于DDD的永续合约智能体技术规格书**

本报告将之前的架构设计转化为可执行的技术规格，重点解决**数据流转**、**状态管理**和**AI集成**的细节问题。

## ---

**第一部分：核心领域模型深化 (Deep Dive into Domain Models)**

在 DDD 中，**聚合根 (Aggregate Root)** 是保持数据一致性的关键。对于永续合约交易，最核心的聚合根不是“订单”，而是\*\*“账户仓位 (AccountPosition)”\*\*。

### **1.1 核心实体定义 (Python Type Hints)**

我们使用 Pydantic 来强制执行类型安全，确保回测和实盘使用完全相同的数据结构。

Python

from pydantic import BaseModel, Field  
from decimal import Decimal  
from enum import Enum  
from datetime import datetime  
from typing import List, Optional

class Side(str, Enum):  
    LONG \= "LONG"  
    SHORT \= "SHORT"

class OrderType(str, Enum):  
    MARKET \= "MARKET"  
    LIMIT \= "LIMIT"

\# \--- 值对象 (Value Objects) \---  
class FundingInfo(BaseModel):  
    """永续合约特有的资金费率数据"""  
    symbol: str  
    rate: Decimal  \# e.g., 0.0001 (0.01%)  
    timestamp: datetime  
    next\_funding\_time: datetime

class TradeFill(BaseModel):  
    """成交明细 (不可变)"""  
    id: str  
    order\_id: str  
    symbol: str  
    side: Side  
    price: Decimal  
    quantity: Decimal  
    commission: Decimal  
    timestamp: datetime

\# \--- 聚合根 (Aggregate Root) \---  
class Position(BaseModel):  
    """  
    仓位聚合根：负责计算未结盈亏(UPnL)和维持保证金  
    核心逻辑：所有的状态变更必须通过内部方法进行，禁止外部直接修改属性  
    """  
    symbol: str  
    side: Side  
    quantity: Decimal \= Decimal(0)  
    entry\_price: Decimal \= Decimal(0)  \# 平均开仓价  
    leverage: int \= 1  
    liquidation\_price: Optional \= None  
      
    \# 核心业务逻辑：加仓  
    def increase(self, fill: TradeFill):  
        if fill.side\!= self.side and self.quantity \> 0:  
            raise ValueError("Use decrease() to reduce position")  
          
        \# 计算新的平均价格: (OldQty \* OldPrice \+ NewQty \* NewPrice) / TotalQty  
        total\_value \= (self.quantity \* self.entry\_price) \+ (fill.quantity \* fill.price)  
        self.quantity \+= fill.quantity  
        self.entry\_price \= total\_value / self.quantity  
        self.update\_liquidation\_price()

    \# 核心业务逻辑：减仓/平仓  
    def decrease(self, fill: TradeFill) \-\> Decimal:  
        """返回已结盈亏 (Realized PnL)"""  
        if fill.side \== self.side:  
            raise ValueError("Use increase() to add to position")  
          
        close\_qty \= min(fill.quantity, self.quantity)  
          
        \# 计算盈亏: (ExitPrice \- EntryPrice) \* Qty \* Direction  
        pnl \= (fill.price \- self.entry\_price) \* close\_qty  
        if self.side \== Side.SHORT:  
            pnl \= \-pnl  
              
        self.quantity \-= close\_qty  
        if self.quantity \== 0:  
            self.side \= Side.LONG \# 重置默认  
            self.entry\_price \= Decimal(0)  
              
        return pnl

### **1.2 为什么这样设计？**

* **消除“回测幸存者偏差”**：很多简单的回测脚本只计算“买入价”和“卖出价”的差值，忽略了**资金费率扣除**和**保证金维持**。通过 Position 对象，我们强制在回测中也必须模拟这些逻辑。  
* **统一实盘接口**：实盘中，交易所API返回的 JSON 会被立即转化为这个 Position 对象。策略只读取这个对象，完全不关心数据来源。

## ---

**第二部分：统一时钟与事件循环 (The Unified Clock & Event Loop)**

这是实现“回测即实盘”的核心引擎。我们需要一个\*\*IClock\*\* 接口。

### **2.1 时钟抽象**

Python

class IClock(ABC):  
    @abstractmethod  
    def now(self) \-\> datetime: pass

class RealtimeClock(IClock):  
    def now(self) \-\> datetime:  
        return datetime.utcnow()

class BacktestClock(IClock):  
    def \_\_init\_\_(self):  
        self.\_current\_time \= datetime.min  
      
    def update(self, timestamp: datetime):  
        self.\_current\_time \= timestamp  
          
    def now(self) \-\> datetime:  
        return self.\_current\_time

### **2.2 事件总线 (Event Bus) 的运作流**

在回测模式下，BacktestEngine 充当上帝角色，它读取下一条 K 线数据，更新 BacktestClock，然后将 MarketEvent 推送给策略。

**关键流程：**

1. **数据到达**：K线 BTC/USDT 时间戳 12:00。  
2. **时钟更新**：BacktestClock 更新为 12:00。  
3. **策略计算**：策略询问 clock.now()，得到 12:00，基于此时间戳的指标做出决策。  
4. **撮合检查**：SimulatedBroker 检查 12:00 这一分钟内的最高价/最低价，判断之前的挂单是否成交。

## ---

**第三部分：智能体（AI Agent）集成架构**

我们不再让 LLM 直接“控制”交易，而是将其设计为一个**高级信号发生器**。

### **3.1 混合架构：规则卫士 \+ AI 大脑**

* **规则层 (Python Code)**：负责止损、仓位限制、订单执行。这是**硬约束**，LLM 无法逾越。  
* **AI 层 (LLM)**：负责分析市场情绪、宏观新闻、链上异动，并输出**调整建议**。

### **3.2 AI Tool Definitions (JSON Schema)**

这是 AI 与系统交互的唯一接口。我们定义一组工具，让 LLM 通过 **Function Calling** 来调用。

**工具 1：市场诊断 (Market Diagnosis)**

JSON

{  
  "name": "get\_market\_state",  
  "description": "获取当前市场的技术面和资金面状态",  
  "parameters": {  
    "type": "object",  
    "properties": {  
      "symbol": {"type": "string", "enum":},  
      "indicators": {  
        "type": "array",  
        "items": {"type": "string", "enum":}  
      }  
    }  
  }  
}

**工具 2：策略参数调整 (Strategy Tuning)**

*这是 AI 影响交易的主要方式。它不直接下单，而是修改策略参数。*

JSON

{  
  "name": "adjust\_strategy\_params",  
  "description": "基于市场判断，动态调整策略参数",  
  "parameters": {  
    "type": "object",  
    "properties": {  
      "strategy\_id": {"type": "string"},  
      "risk\_level": {"type": "string", "enum":},  
      "stop\_loss\_pct": {"type": "number", "description": "建议的止损百分比，例如 0.02 代表 2%"},  
      "reasoning": {"type": "string", "description": "调整参数的逻辑理由"}  
    },  
    "required": \["strategy\_id", "risk\_level", "reasoning"\]  
  }  
}

### **3.3 AI 工作流 (Reflexion Loop)**

1. **观察 (Observe)**: 系统每 4 小时触发一次 AI 分析任务。  
2. **思考 (Reason)**: LLM 调用 get\_market\_state，发现资金费率飙升，RSI 超买。  
3. **行动 (Act)**: LLM 调用 adjust\_strategy\_params，将 risk\_level 调为 CONSERVATIVE，并将止损收紧。  
4. **执行 (Execute)**: 这里的 Python 策略代码接收到新参数，自动更新止损逻辑。

## ---

**第四部分：回测的高级保真度设计 (High-Fidelity Backtesting)**

为了让回测有意义，必须模拟币圈特有的痛点。

### **4.1 资金费率回测 (Funding Rate Simulation)**

* **数据源**：不仅下载 OHLCV，还要下载每 8 小时的 Funding Rate 历史数据。  
* **模拟逻辑**：在回测引擎中，每当 clock.now() 跨越 00:00, 08:00, 16:00 时，遍历所有持仓：  
  * 多头：扣除 Position Value \* Rate  
  * 空头：获得 Position Value \* Rate (若费率为正)  
* **意义**：很多震荡策略看似赚钱，加上费率后可能是亏损的。

### **4.2 滑点与流动性模拟**

不要使用固定的“万分之五”滑点。建议采用**基于波动率的滑点模型**：

![][image1]

* 在剧烈波动（大K线）时，回测引擎自动加大滑点，模拟真实世界的“追单”损耗。

## ---

**第五部分：推荐的“最小可行产品” (MVP) 开发栈**

基于这份深化报告，您的下一步行动方案：

1. **数据准备**：  
   * 使用 ccxt 下载 BTC/USDT 最近 1 年的 **15分钟K线** 和 **8小时资金费率**。  
   * 存储为 sqlite 或 parquet。  
2. **核心类实现**：  
   * 实现 Position 类（最复杂的逻辑都在这）。  
   * 实现 BacktestClock。  
3. **编写第一个策略**：  
   * **双均线 \+ 资金费率过滤**：只有当资金费率为正（看多情绪浓）时，才允许做多；费率为负时，只做空。  
4. **AI 接入（第二阶段）**：  
   * 当策略跑通后，接入 DeepSeek 或 GPT-4 API，让它每周根据回测的盈亏曲线（PnL Curve）给出一段文本点评。

这份报告将原本“高大上”的架构拆解为了可以一行行代码实现的具体任务。这就构成了您量化系统的**蓝图**。