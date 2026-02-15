"""Value Objects for the trading domain.

Immutable objects that represent domain concepts without identity.
"""
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field


class Side(StrEnum):
    """Order side - LONG or SHORT."""

    LONG = "LONG"
    SHORT = "SHORT"


class OrderType(StrEnum):
    """Order type - MARKET or LIMIT."""

    MARKET = "MARKET"
    LIMIT = "LIMIT"


class FundingInfo(BaseModel):
    """Immutable value object representing funding rate information.

    Attributes:
        symbol: Trading pair symbol
        rate: Funding rate (e.g., 0.0001 represents 0.01%)
        timestamp: When the rate was recorded
        next_funding_time: When the next funding settlement occurs
    """

    model_config = {"frozen": True}

    symbol: str = Field(..., description="Trading pair symbol")
    rate: Decimal = Field(..., description="Funding rate (e.g., 0.0001 for 0.01%)")
    timestamp: datetime = Field(..., description="When the rate was recorded")
    next_funding_time: datetime = Field(..., description="Next funding settlement time")


class TradeFill(BaseModel):
    """Immutable value object representing a filled trade.

    Attributes:
        id: Unique fill identifier
        order_id: Associated order identifier
        symbol: Trading pair symbol
        side: Order side (LONG or SHORT)
        price: Execution price
        quantity: Executed quantity
        commission: Trading fee
        timestamp: When the fill occurred
    """

    model_config = {"frozen": False}

    id: str = Field(..., description="Unique fill identifier")
    order_id: str = Field(..., description="Associated order identifier")
    symbol: str = Field(..., description="Trading pair symbol")
    side: Side = Field(..., description="Order side")
    price: Decimal = Field(..., gt=0, description="Execution price")
    quantity: Decimal = Field(..., gt=0, description="Executed quantity")
    commission: Decimal = Field(..., ge=0, description="Trading fee")
    timestamp: datetime = Field(..., description="When the fill occurred")
