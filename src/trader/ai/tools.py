"""AI 工具定义"""
from typing import Optional, List, Dict, Any
from enum import StrEnum
from dataclasses import dataclass
from decimal import Decimal
from datetime import datetime


class RiskLevel(StrEnum):
    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"


@dataclass
class ToolParameter:
    """工具参数定义"""
    name: str
    type: str
    description: str
    required: bool = False
    enum: Optional[List[str]] = None


@dataclass
class ToolDefinition:
    """工具定义"""
    name: str
    description: str
    parameters: List[ToolParameter]

    def to_openai_format(self) -> Dict[str, Any]:
        """转换为 OpenAI Function Calling 格式"""
        properties = {}
        required = []
        for param in self.parameters:
            properties[param.name] = {
                "type": param.type,
                "description": param.description
            }
            if param.enum:
                properties[param.name]["enum"] = param.enum
            if param.required:
                required.append(param.name)
        
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required
                }
            }
        }


# 工具 1: 获取市场状态
get_market_state_tool = ToolDefinition(
    name="get_market_state",
    description="获取当前市场的技术面和资金面状态",
    parameters=[
        ToolParameter(
            name="symbol",
            type="string",
            description="交易对，例如 BTC/USDT",
            required=True
        ),
        ToolParameter(
            name="indicators",
            type="array",
            description="技术指标列表，例如 ['RSI', 'MACD', 'MA']",
            required=False
        )
    ]
)

# 工具 2: 调整策略参数
adjust_strategy_params_tool = ToolDefinition(
    name="adjust_strategy_params",
    description="基于市场判断，动态调整策略参数",
    parameters=[
        ToolParameter(
            name="strategy_id",
            type="string",
            description="策略标识符",
            required=True
        ),
        ToolParameter(
            name="risk_level",
            type="string",
            description="风险等级",
            required=True,
            enum=["conservative", "moderate", "aggressive"]
        ),
        ToolParameter(
            name="stop_loss_pct",
            type="number",
            description="止损百分比，例如 0.05 表示 5%",
            required=False
        ),
        ToolParameter(
            name="reasoning",
            type="string",
            description="调整原因的详细说明",
            required=True
        )
    ]
)

# 工具 3: 查询当前仓位
get_position_tool = ToolDefinition(
    name="get_position",
    description="查询当前持仓状态",
    parameters=[
        ToolParameter(
            name="symbol",
            type="string",
            description="交易对，例如 BTC/USDT",
            required=False
        )
    ]
)

# 所有可用工具
ALL_TOOLS = [
    get_market_state_tool,
    adjust_strategy_params_tool,
    get_position_tool
]
