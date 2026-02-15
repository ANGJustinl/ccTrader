"""AI 增强策略 - AI 智能体调整参数，不直接下单"""
from decimal import Decimal
from typing import List, Optional
from ..strategy import BaseStrategy
from ...infrastructure.data_repository import BarData
from ...ai import AIAgent, StrategyParams, RiskLevel


class AIEnhancedStrategy(BaseStrategy):
    """AI 增强双均线策略
    
    - AI 智能体根据市场状态动态调整策略参数
    - 核心交易逻辑仍是规则型双均线
    - AI 不直接下单，只调整风险/仓位/止损参数
    """
    
    def __init__(
        self,
        fast_period: int = 10,
        slow_period: int = 20,
        base_position_size: float = 0.01
    ):
        super().__init__("AI Enhanced MA Crossover")
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.base_position_size = base_position_size
        self.bar_history: List[BarData] = []
        
        # 初始化 AI 代理
        self.ai_agent = AIAgent()
        
        # 绑定参数更新回调
        self.ai_agent.on_params_updated = self._on_params_updated
        
        # 基础参数
        self.current_params = StrategyParams.default()
        
        # 每 100 根 K 线触发一次 AI 分析
        self.analysis_interval = 100
        self.bar_count = 0
    
    def _on_params_updated(self, params: StrategyParams) -> None:
        """策略参数更新回调"""
        self.current_params = params
    
    def attach_backtest_engine(self, engine) -> None:
        """连接回测引擎"""
        self.ai_agent.attach_backtest_engine(engine)
    
    def trigger_ai_analysis(self) -> None:
        """触发 AI 分析（模拟）"""
        # 在真实场景中，这里会调用 LLM API
        # 这里模拟 AI 根据简单规则给出建议
        
        # 获取当前市场状态
        market_state = self.ai_agent.get_market_state("BTC/USDT")
        position_state = self.ai_agent.get_position()
        
        # 简单的 AI 决策逻辑（模拟）
        if self.bar_count > 150 and len(self.bar_history) > 50:
            # 后期：市场震荡，切换到保守模式
            if self.current_params.risk_level != RiskLevel.CONSERVATIVE:
                self.ai_agent.update_strategy_params(
                    risk_level=RiskLevel.CONSERVATIVE,
                    reasoning="市场进入震荡期，切换保守模式降低风险"
                )
        elif self.bar_count > 100 and len(self.bar_history) > 50:
            # 中期：趋势明显，切换到激进模式
            if self.current_params.risk_level != RiskLevel.AGGRESSIVE:
                self.ai_agent.update_strategy_params(
                    risk_level=RiskLevel.AGGRESSIVE,
                    reasoning="识别到上升趋势，切换激进模式提高收益"
                )
    
    def on_bar(self, bar: BarData) -> None:
        # 保存历史数据
        self.bar_history.append(bar)
        self.bar_count += 1
        
        # 保持足够的历史数据
        if len(self.bar_history) > self.slow_period + 50:
            self.bar_history.pop(0)
        
        # 定期触发 AI 分析
        if self.bar_count % self.analysis_interval == 0 and self.bar_count > 0:
            self.trigger_ai_analysis()
        
        # 需要足够的数据计算均线
        if len(self.bar_history) < self.slow_period:
            return
        
        # 计算均线
        fast_ma = self._calculate_sma(self.fast_period)
        slow_ma = self._calculate_sma(self.slow_period)
        
        # 根据 AI 参数调整仓位大小
        position_size = float(self.current_params.max_position_size) * self.base_position_size
        
        # 获取当前持仓
        position = self.broker.get_position(bar.symbol)
        
        # 核心交易逻辑（规则型，AI 不直接参与）
        if fast_ma > slow_ma:
            # 金叉，看多
            if position is None:
                # 无持仓，开多
                self.create_market_order(
                    symbol=bar.symbol,
                    side="buy",
                    quantity=position_size
                )
        elif fast_ma < slow_ma:
            # 死叉，看空
            if position is not None and position.side.value == "LONG":
                # 持有多仓，平多
                self.create_market_order(
                    symbol=bar.symbol,
                    side="sell",
                    quantity=float(position.quantity)
                )
    
    def _calculate_sma(self, period: int) -> Decimal:
        """计算简单移动平均"""
        recent_bars = self.bar_history[-period:]
        sum_price = sum(bar.close for bar in recent_bars)
        return sum_price / Decimal(str(period))
