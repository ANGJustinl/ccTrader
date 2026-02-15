"""AI 智能代理"""
from typing import Dict, Any, Optional, List, Callable, TYPE_CHECKING
from datetime import datetime
import json
from .tools import (
    ALL_TOOLS,
    ToolDefinition,
    RiskLevel
)
from .strategy_params import StrategyParams

# 使用类型检查时的导入，避免循环导入
if TYPE_CHECKING:
    from ..application.backtest_engine import BacktestEngine


class AIAgent:
    """AI 智能代理 - LLM 不直接下单，只调整策略参数"""
    
    def __init__(
        self,
        name: str = "Trading AI Agent",
        strategy_params: Optional[StrategyParams] = None
    ):
        self.name = name
        self.strategy_params = strategy_params or StrategyParams.default()
        self.backtest_engine: Optional[Any] = None
        
        # 回调函数
        self.on_params_updated: Optional[Callable[[StrategyParams], None]] = None
    
    def attach_backtest_engine(self, engine: Any) -> None:
        """连接回测引擎"""
        self.backtest_engine = engine
    
    def update_strategy_params(
        self,
        risk_level: RiskLevel,
        stop_loss_pct: Optional[float] = None,
        reasoning: str = ""
    ) -> StrategyParams:
        """调整策略参数（这是 LLM 调用的工具）"""
        self.strategy_params = StrategyParams.from_risk_level(risk_level)
        
        if stop_loss_pct is not None:
            from decimal import Decimal
            self.strategy_params.stop_loss_pct = Decimal(str(stop_loss_pct))
        
        if self.on_params_updated:
            self.on_params_updated(self.strategy_params)
        
        return self.strategy_params
    
    def get_market_state(
        self,
        symbol: str = "BTC/USDT",
        indicators: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """获取市场状态（这是 LLM 调用的工具）"""
        state = {
            "symbol": symbol,
            "timestamp": datetime.now().isoformat(),
            "indicators": {}
        }
        
        if self.backtest_engine and self.backtest_engine.current_bar:
            bar = self.backtest_engine.current_bar
            state["current_price"] = float(bar.close)
            state["high_24h"] = float(bar.high)
            state["low_24h"] = float(bar.low)
        
        return state
    
    def get_position(
        self,
        symbol: Optional[str] = None
    ) -> Dict[str, Any]:
        """查询当前仓位（这是 LLM 调用的工具）"""
        position_info = {
            "has_position": False,
            "positions": {}
        }
        
        if self.backtest_engine and self.backtest_engine.broker:
            broker = self.backtest_engine.broker
            
            if symbol:
                position = broker.get_position(symbol)
                if position:
                    position_info["has_position"] = True
                    position_info["positions"][symbol] = {
                        "side": position.side.value,
                        "quantity": float(position.quantity),
                        "entry_price": float(position.entry_price),
                        "leverage": position.leverage
                    }
            else:
                for sym, pos in broker.positions.items():
                    position_info["has_position"] = True
                    position_info["positions"][sym] = {
                        "side": pos.side.value,
                        "quantity": float(pos.quantity),
                        "entry_price": float(pos.entry_price),
                        "leverage": pos.leverage
                    }
        
        return position_info
    
    def execute_tool_call(
        self,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """执行工具调用"""
        if tool_name == "get_market_state":
            return self.get_market_state(
                symbol=arguments.get("symbol", "BTC/USDT"),
                indicators=arguments.get("indicators")
            )
        elif tool_name == "adjust_strategy_params":
            return {
                "success": True,
                "params": self.update_strategy_params(
                    risk_level=RiskLevel(arguments.get("risk_level", "moderate")),
                    stop_loss_pct=arguments.get("stop_loss_pct"),
                    reasoning=arguments.get("reasoning", "")
                )
            }
        elif tool_name == "get_position":
            return self.get_position(
                symbol=arguments.get("symbol")
            )
        else:
            return {
                "error": f"Unknown tool: {tool_name}"
            }
    
    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """获取所有工具定义（OpenAI 格式）"""
        return [tool.to_openai_format() for tool in ALL_TOOLS]
