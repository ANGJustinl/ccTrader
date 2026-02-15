"""策略参数管理"""
from pydantic import BaseModel, Field
from decimal import Decimal
from typing import Optional
from enum import StrEnum


class RiskLevel(StrEnum):
    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"


class StrategyParams(BaseModel):
    """策略参数"""
    strategy_id: str = "default"
    
    # 风险设置
    risk_level: RiskLevel = RiskLevel.MODERATE
    max_position_size: Decimal = Decimal("0.1")
    stop_loss_pct: Optional[Decimal] = Decimal("0.05")
    take_profit_pct: Optional[Decimal] = Decimal("0.1")
    
    # 交易设置
    leverage: int = 1
    slippage_tolerance: Decimal = Decimal("0.001")
    
    @classmethod
    def default(cls) -> "StrategyParams":
        """获取默认参数"""
        return cls()
    
    @classmethod
    def from_risk_level(cls, risk_level: RiskLevel) -> "StrategyParams":
        """根据风险等级创建参数"""
        if risk_level == RiskLevel.CONSERVATIVE:
            return cls(
                risk_level=RiskLevel.CONSERVATIVE,
                max_position_size=Decimal("0.05"),
                stop_loss_pct=Decimal("0.03"),
                take_profit_pct=Decimal("0.06"),
                leverage=1
            )
        elif risk_level == RiskLevel.AGGRESSIVE:
            return cls(
                risk_level=RiskLevel.AGGRESSIVE,
                max_position_size=Decimal("0.2"),
                stop_loss_pct=Decimal("0.1"),
                take_profit_pct=Decimal("0.2"),
                leverage=5
            )
        else:  # MODERATE
            return cls()
