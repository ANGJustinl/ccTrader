"""Simulated broker for backtesting.

Provides order matching and position management for backtesting.
"""
from decimal import Decimal
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from ..domain.position import Position
from ..domain.services import PositionFactory
from ..domain.value_objects import Side, TradeFill
from ..infrastructure.clock import IClock
from ..infrastructure.event_bus import EventBus, Event, EventType
from .order import Order, OrderStatus


class SimulatedBroker:
    """模拟撮合引擎 - 用于回测

    Provides simulated order execution with slippage and commission.

    Attributes:
        clock: Clock instance for time management
        event_bus: Event bus for publishing events
        balance: Current account balance
        initial_balance: Initial account balance
        slippage_rate: Slippage rate as decimal (e.g., 0.0005 = 0.05%)
        commission_rate: Commission rate as decimal (e.g., 0.0004 = 0.04%)
        positions: Dictionary of symbol -> Position
        orders: Dictionary of order_id -> Order
        open_orders: Dictionary of symbol -> [order_ids]
    """

    def __init__(
        self,
        clock: IClock,
        event_bus: EventBus,
        initial_balance: Decimal = Decimal("10000"),
        slippage_rate: Decimal = Decimal("0.0005"),  # 0.05% 默认滑点
        commission_rate: Decimal = Decimal("0.0004"),  # 0.04% 手续费
    ):
        """Initialize simulated broker.

        Args:
            clock: Clock instance for time management
            event_bus: Event bus for publishing events
            initial_balance: Initial account balance (default: 10000)
            slippage_rate: Slippage rate as decimal (default: 0.0005 = 0.05%)
            commission_rate: Commission rate as decimal (default: 0.0004 = 0.04%)
        """
        self.clock = clock
        self.event_bus = event_bus
        # Ensure all parameters are Decimal
        self.balance = Decimal(str(initial_balance)) if not isinstance(initial_balance, Decimal) else initial_balance
        self.initial_balance = self.balance
        self.slippage_rate = Decimal(str(slippage_rate)) if not isinstance(slippage_rate, Decimal) else slippage_rate
        self.commission_rate = Decimal(str(commission_rate)) if not isinstance(commission_rate, Decimal) else commission_rate

        self.positions: Dict[str, Position] = {}  # symbol -> Position
        self.orders: Dict[str, Order] = {}  # order_id -> Order
        self.open_orders: Dict[str, List[str]] = {}  # symbol -> [order_ids]

    def submit_order(self, order: Order) -> None:
        """提交订单

        Args:
            order: Order to submit
        """
        order.status = OrderStatus.SUBMITTED
        self.orders[order.id] = order

        if order.symbol not in self.open_orders:
            self.open_orders[order.symbol] = []
        self.open_orders[order.symbol].append(order.id)

        # 发布订单提交事件
        self.event_bus.publish(
            Event(
                type=EventType.ORDER_SUBMITTED,
                timestamp=self.clock.now(),
                data={"order_id": order.id, "symbol": order.symbol},
            )
        )

    def match_orders(
        self,
        symbol: str,
        high: Decimal,
        low: Decimal,
        close: Decimal,
    ) -> List[TradeFill]:
        """撮合订单，返回成交列表

        Args:
            symbol: Trading pair symbol
            high: High price for the bar
            low: Low price for the bar
            close: Close price for the bar

        Returns:
            List of trade fills
        """
        fills = []
        order_ids = self.open_orders.get(symbol, []).copy()

        for order_id in order_ids:
            order = self.orders[order_id]

            if not order.is_open:
                continue

            fill = self._match_single_order(order, high, low, close)
            if fill:
                fills.append(fill)
                self._update_position_after_fill(fill)

        return fills

    def _match_single_order(
        self,
        order: Order,
        high: Decimal,
        low: Decimal,
        close: Decimal,
    ) -> Optional[TradeFill]:
        """撮合单个订单

        Args:
            order: Order to match
            high: High price for the bar
            low: Low price for the bar
            close: Close price for the bar

        Returns:
            Trade fill if order is matched, None otherwise
        """
        fill_price = None

        # 判断是否成交
        if order.order_type == "market":
            # 市价单以收盘价成交
            fill_price = close
        elif order.order_type == "limit":
            # 限价单判断
            if order.side == "buy" and low <= order.price:
                fill_price = min(order.price, close)
            elif order.side == "sell" and high >= order.price:
                fill_price = max(order.price, close)

        if fill_price is None:
            return None

        # 应用滑点
        if order.side == "buy":
            fill_price = fill_price * (Decimal("1") + self.slippage_rate)
        else:
            fill_price = fill_price * (Decimal("1") - self.slippage_rate)

        # 计算手续费
        commission = order.remaining_quantity * fill_price * self.commission_rate

        # 创建成交记录
        fill = TradeFill(
            id=str(len(self.orders) + 1),
            order_id=order.id,
            symbol=order.symbol,
            side=Side.LONG if order.side == "buy" else Side.SHORT,
            price=fill_price,
            quantity=order.remaining_quantity,
            commission=commission,
            timestamp=self.clock.now(),
        )

        # 更新订单状态
        order.filled_quantity += fill.quantity
        if order.filled_quantity > Decimal("0"):
            old_quantity = order.filled_quantity - fill.quantity
            order.avg_fill_price = (
                (order.avg_fill_price or Decimal("0")) * old_quantity
                + fill.price * fill.quantity
            ) / order.filled_quantity
        else:
            order.avg_fill_price = fill.price

        if order.filled_quantity >= order.quantity:
            order.status = OrderStatus.FILLED
            self.open_orders[order.symbol].remove(order.id)
        else:
            order.status = OrderStatus.PARTIAL_FILLED

        # 发布订单成交事件
        self.event_bus.publish(
            Event(
                type=EventType.ORDER_FILLED,
                timestamp=self.clock.now(),
                data={
                    "order_id": order.id,
                    "fill_id": fill.id,
                    "price": str(fill.price),
                    "quantity": str(fill.quantity),
                },
            )
        )

        return fill

    def _update_position_after_fill(self, fill: TradeFill) -> None:
        """根据成交更新仓位

        Args:
            fill: Trade fill to apply
        """
        symbol = fill.symbol

        if symbol not in self.positions:
            # 首次开仓
            side = Side.LONG if fill.side == Side.LONG else Side.SHORT
            self.positions[symbol] = PositionFactory.create_position(
                symbol=symbol,
                side=side,
                quantity=fill.quantity,
                entry_price=fill.price,
                leverage=1,
            )

            self.event_bus.publish(
                Event(
                    type=EventType.POSITION_OPENED,
                    timestamp=self.clock.now(),
                    data={"symbol": symbol, "side": side.value, "quantity": str(fill.quantity)},
                )
            )
        else:
            position = self.positions[symbol]

            # 判断是加仓还是减仓
            current_side = position.side
            new_side = fill.side

            if current_side == new_side:
                # 同向加仓
                position.increase(fill)
            else:
                # 反向减仓或平仓 - 创建与 position side 一致的 fill 用于 decrease
                position_side_fill = fill.model_copy(update={"side": current_side})
                realized_pnl = position.decrease(position_side_fill)

                # 更新余额
                self.balance += realized_pnl - fill.commission

                # 发布交易完成事件 (用于回测统计)
                self.event_bus.publish(
                    Event(
                        type=EventType.TRADE_COMPLETED,
                        timestamp=self.clock.now(),
                        data={
                            "symbol": symbol,
                            "side": current_side.value,
                            "entry_price": str(position.entry_price), # Note: this is avg entry price
                            "exit_price": str(fill.price),
                            "quantity": str(fill.quantity),
                            "pnl": str(realized_pnl),
                            "commission": str(fill.commission),
                        },
                    )
                )

                if position.is_closed:
                    # 发布平仓事件
                    self.event_bus.publish(
                        Event(
                            type=EventType.POSITION_CLOSED,
                            timestamp=self.clock.now(),
                            data={
                                "symbol": symbol,
                                "realized_pnl": str(realized_pnl),
                                "commission": str(fill.commission),
                            },
                        )
                    )
                    del self.positions[symbol]

    def cancel_order(self, order_id: str) -> bool:
        """取消订单

        Args:
            order_id: Order ID to cancel

        Returns:
            True if order was cancelled, False otherwise
        """
        if order_id not in self.orders:
            return False

        order = self.orders[order_id]
        if not order.is_open:
            return False

        order.status = OrderStatus.CANCELLED
        self.open_orders[order.symbol].remove(order_id)

        self.event_bus.publish(
            Event(
                type=EventType.ORDER_CANCELLED,
                timestamp=self.clock.now(),
                data={"order_id": order_id},
            )
        )

        return True

    def get_open_orders(self, symbol: str) -> List[Order]:
        """获取未结订单
        
        Args:
            symbol: Trading pair symbol
            
        Returns:
            List of open orders
        """
        order_ids = self.open_orders.get(symbol, [])
        return [self.orders[oid] for oid in order_ids if oid in self.orders]

    def get_position(self, symbol: str) -> Optional[Position]:
        """获取当前仓位

        Args:
            symbol: Trading pair symbol

        Returns:
            Position if exists, None otherwise
        """
        return self.positions.get(symbol)

    def get_balance(self) -> Decimal:
        """获取账户余额

        Returns:
            Current account balance
        """
        balance = self.balance

        # 加上未实现盈亏
        for position in self.positions.values():
            # 使用当前最新价格（需要从外部传入）
            # 这里简化处理，假设价格已知
            pass

        return balance
