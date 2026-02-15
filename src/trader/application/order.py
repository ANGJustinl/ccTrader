"""Order models for the trading application layer.

Provides order management with status tracking.
"""
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field

import uuid


class OrderStatus(StrEnum):
    """Order status enumeration."""

    PENDING = "pending"
    SUBMITTED = "submitted"
    PARTIAL_FILLED = "partial_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class Order(BaseModel):
    """订单模型

    Attributes:
        id: Unique order identifier
        symbol: Trading pair symbol
        side: Order side ("buy" or "sell")
        order_type: Order type ("market" or "limit")
        quantity: Order quantity
        price: Limit order price (None for market orders)
        status: Current order status
        filled_quantity: Quantity that has been filled
        avg_fill_price: Average fill price
        timestamp: Order timestamp
        create_time: Creation time
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    symbol: str
    side: str  # "buy" or "sell"
    order_type: str  # "market" or "limit"
    quantity: Decimal
    price: Decimal | None = None  # 市价单为 None
    status: OrderStatus = OrderStatus.PENDING
    filled_quantity: Decimal = Decimal("0")
    avg_fill_price: Decimal | None = None
    timestamp: datetime
    create_time: datetime = Field(default_factory=lambda: datetime.now())

    @property
    def remaining_quantity(self) -> Decimal:
        """Calculate remaining unfilled quantity.

        Returns:
            Remaining quantity to fill
        """
        return self.quantity - self.filled_quantity

    @property
    def is_open(self) -> bool:
        """Check if order is still open.

        Returns:
            True if order is pending, submitted, or partially filled
        """
        return self.status in [
            OrderStatus.PENDING,
            OrderStatus.SUBMITTED,
            OrderStatus.PARTIAL_FILLED,
        ]
