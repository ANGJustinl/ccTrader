# 使用手册

## 快速开始

### 环境要求

- Python 3.10+
- uv 包管理器

### 安装

```bash
# 克隆项目
git clone <repository-url>
cd Trader

# 使用 uv 安装依赖
uv sync
```

### 配置

创建 `.env` 文件配置环境变量：

```env
# .env
OPENAI_API_KEY=your_api_key_here
DEEPSEEK_API_KEY=your_deepseek_key_here
```

## 基础使用

### 运行简单回测

```python
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from trader.application.backtest_engine import BacktestEngine
from trader.application.strategies.ma_crossover import MovingAverageCrossover

# 创建回测引擎
engine = BacktestEngine(
    initial_balance=Decimal("10000"),
    slippage=Decimal("0.0005"),
    commission=Decimal("0.0004")
)

# 下载数据
end_date = datetime.now(timezone.utc)
start_date = end_date - timedelta(days=30)

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

# 运行回测
engine.set_strategy(strategy)
results = engine.run("BTC/USDT")

# 打印结果
print(f"初始资金: ${results['initial_balance']:.2f}")
print(f"最终资金: ${results['final_balance']:.2f}")
print(f"收益率: {results['total_return']:.2f}%")
print(f"最大回撤: {results['max_drawdown']:.2f}%")
print(f"夏普比率: {results['sharpe_ratio']:.2f}")
print(f"交易次数: {results['total_trades']}")
```

### 使用 AI 增强策略

```python
from trader.application.strategies.ai_enhanced import AIEnhancedStrategy

# 创建 AI 增强策略
strategy = AIEnhancedStrategy(
    fast_period=10,
    slow_period=20
)

# AI 会在回测过程中自动调整策略参数
# 但 AI 只能调整参数，不能直接下单，确保安全
```

## 脚本使用

### 下载数据脚本

```bash
# 运行数据下载脚本
uv run python -m trader.scripts.download_data
```

### 运行回测脚本

```bash
# 运行基础回测
uv run python -m trader.scripts.run_backtest

# 运行 AI 增强回测
uv run python -m trader.scripts.run_ai_backtest
```

## 测试

### 运行所有测试

```bash
# 运行测试
uv run pytest

# 运行测试并显示详细信息
uv run pytest -v

# 运行特定测试文件
uv run pytest tests/test_domain.py

# 运行特定测试类
uv run pytest tests/test_domain.py::TestPosition
```

### 测试覆盖率

```bash
# 生成覆盖率报告
uv run pytest --cov=src/trader --cov-report=html

# 查看覆盖率报告
# 打开 htmlcov/index.html
```

## 性能优化

### 大数据量回测

对于超过 1 年的数据，建议：

1. 使用 Parquet 格式存储数据
2. 分批加载数据
3. 使用内存映射文件

### 并行回测

可以同时运行多个参数组合的回测：

```python
import concurrent.futures

def run_backtest(params):
    fast, slow = params
    engine = BacktestEngine(...)
    # ... 配置并运行回测
    return results

param_combinations = [(5, 10), (10, 20), (15, 30)]

with concurrent.futures.ProcessPoolExecutor() as executor:
    results = list(executor.map(run_backtest, param_combinations))
```

## 故障排除

### 网络问题

如果遇到网络问题，使用代理：

```bash
# 在命令前加上 pc 使用代理
pc uv run python ...
```

### 内存问题

如果遇到内存不足：

1. 减少回测数据量
2. 使用分批处理
3. 增加系统虚拟内存

### 依赖问题

```bash
# 重新安装依赖
uv sync --reinstall

# 清理缓存
uv cache clean
```

## 常见问题

**Q: 如何添加新的交易所？**

A: CCXT 已支持 100+ 交易所，直接在 `download_data` 时指定 exchange 参数即可。

**Q: AI 会直接下单吗？**

A: 不会。我们采用混合架构，AI 只能调整策略参数，不能直接下单，交易由规则型策略执行。

**Q: 如何自定义滑点模型？**

A: 参考 `utils/slippage.py` 中的 `VolatilitySlippageModel`，继承并实现自定义滑点计算逻辑。

**Q: 回测速度慢怎么办？**

A: 参考性能优化部分，使用数据缓存、减少数据量或并行化处理。
