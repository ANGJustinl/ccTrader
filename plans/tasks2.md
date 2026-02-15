**DRAMM (动态体制自适应多因子模型)** 是一个基于研报的综合策略框架，核心思想是通过**体制识别**来动态调整多因子模型的权重，从而适应不同的市场环境。以下是将研报内容落地到我们系统中的详细计划。

### 1. 基础设施层升级 (Infrastructure Upgrade)

现有的 `indicators.py` 和 `DataDownloader` 需要扩展，以支持研报中的核心指标。

#### A. 指标库扩容 (`src/trader/utils/indicators.py`)

我们需要增加研报中提到的“体制识别”和“风控”指标。

* **新增指标**：
* `ADX` (平均趋向指标)：用于判断趋势强度（体制识别核心）。
* `Bollinger Bandwidth (BBW)`：布林带宽度，用于判断波动率压缩/爆发。
* `ATR` (平均真实波幅)：用于动态止损计算。
* `Z-Score`：用于因子归一化评分。


#### B. 数据源增强 (Data Reality Check)

研报提到了 **OFI (订单流失衡)** 和 **Coinbase 溢价**。

* **现实问题**：我们的 `DataDownloader` 目前只拉取单一交易所的 OHLCV。OFI 需要 L2 逐笔数据（数据量极大），Coinbase 溢价需要跨交易所同步。
* **MVP 替代方案**：
* **OFI 替代**：使用 **“主动买入成交量 (Taker Buy Volume)”**。Binance K线数据包含此字段，可以近似代替订单流压力。
* **溢价替代**：暂时忽略跨交易所溢价，或者仅使用 **“现货-合约价差”** (Basis) 作为替代。



---

### 2. 策略层实现 (Application Layer)

这是核心工作。我们需要创建一个新的策略类 `DRAMMStrategy`，它不再是简单的 `if/else`，而是一个 **状态机**。

建议创建文件：`src/trader/application/strategies/dramm.py`

#### 核心逻辑架构

```python
from decimal import Decimal
from trader.application.strategy import BaseStrategy
from trader.utils.indicators import calculate_sma, calculate_rsi, calculate_bollinger_bands

class DRAMMStrategy(BaseStrategy):
    def __init__(self, ...):
        super().__init__()
        # 定义权重（初始值）
        self.w_trend = Decimal("0.5")
        self.w_vol = Decimal("0.3")
        self.w_micro = Decimal("0.2")
        
        # 缓存状态
        self.current_regime = "UNKNOWN" 

    def on_bar(self, bar):
        # 1. 计算基础指标
        # 均线, 布林带, RSI, ADX, BBW
        
        # 2. 体制识别 (Regime Identification)
        self._update_regime(adx, bbw)
        
        # 3. 动态调整权重 (Dynamic Weighting)
        self._adjust_weights()
        
        # 4. 计算综合得分 (Composite Score)
        score = self._calculate_score()
        
        # 5. 风控检查 (熔断/资金费率)
        if self._check_risk_triggers():
            self.close_all_positions()
            return

        # 6. 执行逻辑
        if score > 80:
            self.entry_long()
        elif score < -80:
            self.entry_short()
            
    def _update_regime(self, adx, bbw):
        """
        体制识别逻辑:
        - Trend: BBW扩张 + ADX > 25
        - Chop: BBW走平 + ADX < 20
        - Squeeze: BBW极低
        """
        # ... 实现研报 3.2 节逻辑 ...

```

---

### 3. 风控层集成 (Risk Layer)

研报中提到的 **ATR 动态止损** 和 **熔断机制** 需要直接嵌入到策略或 `RiskManager` 中。

* **ATR 动态止损 (Chandelier Exit)**：
* 在 `Position` 对象中不方便直接存，建议在策略内部维护一个字典 `self.trailing_stops = {symbol: price}`。
* 每次 `on_bar` 更新时，根据当前最高价（High）和 ATR 更新止损线。
* `Stop Price = Max(High_since_entry) - (ATR * Multiplier)`。


* **资金费率过滤**：
* 利用我们已经修复的 `on_funding_rate` 回调。
* 逻辑：`if funding_rate > 0.03%: self.long_banned = True`。



---

### 📅 下一步行动计划 (Action Plan)

为了将这份研报“回归”到系统，建议分三步走：

#### Step 1: 基础设施铺路 (Infrastructure)

* **任务**：在 `src/trader/utils/indicators.py` 中实现 `ADX`, `ATR`, `BBW` 计算逻辑。
* **验证**：编写单元测试，确保计算结果与 `pandas_ta` 或标准库一致。

#### Step 2: 策略骨架搭建 (Strategy Skeleton)

* **任务**：创建 `DRAMMStrategy` 类，实现“体制识别”逻辑。暂时先不交易，只在日志中输出：“当前体制：震荡 / 趋势 / 压缩”。
* **验证**：用回测跑一段历史数据，观察日志中的体制分类是否准确（比如大暴涨时是否识别为“趋势”）。

#### Step 3: 完整逻辑与回测 (Full Logic)

* **任务**：填充评分模型，加入 ATR 止损。
* **验证**：运行 `run_backtest.py`，对比纯均线策略，看夏普比率是否有提升。
