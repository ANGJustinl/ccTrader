"""Paper trading broker for real-time simulation.

Provides real-time order matching with live market data simulation.
"""
from decimal import Decimal
from datetime import datetime
from typing import Dict, List, Optional

from ..domain.position import Position
from ..domain.services import PositionFactory
from ..domain.value_objects import Side, TradeFill
from .clock import SystemClock, IClock
from .event_bus import EventBus, Event, EventType
from ..application.order import Order, OrderStatus


class PaperBroker:
    """Paper trading broker for real-time simulation

    Provides real-time order matching with live market data simulation.
    Monitors market data updates and matches orders accordingly.

    Attributes:
        clock: System clock instance
        event_bus: Event bus for publishing/subscribing events
        balance: Current account balance
        initial_balance: Initial account balance
        slippage_rate: Slippage rate as decimal (e.g., 0.0005 = 0.05%)
        commission_rate: Commission rate as decimal (e.g., 0.0004 = 0.04%)
        positions: Dictionary of symbol -> Position
        orders: Dictionary of order_id -> Order
        open_orders: Dictionary of symbol -> [order_ids]
        market_prices: Dictionary of symbol -> current price
    """

    def __init__(
        self,
        event_bus: EventBus,
        initial_balance: Decimal = Decimal("10000"),
        slippage_rate: Decimal = Decimal("0.0005"),  # 0.05% default slippage
        commission_rate: Decimal = Decimal("0.0004"),  # 0.04% commission
    ):
        """Initialize paper trading broker.

        Args:
            event_bus: Event bus for publishing/subscribing events
            initial_balance: Initial account balance (default: 10000)
            slippage_rate: Slippage rate as decimal (default: 0.0005 = 0.05%)
            commission_rate: Commission rate as decimal (default: 0.0004 = 0.04%)
        """
        self.clock = SystemClock()
        self.event_bus = event_bus
        
        # Ensure all parameters are Decimal
        self.balance = Decimal(str(initial_balance)) if not isinstance(initial_balance, Decimal) else initial_balance
        self.initial_balance = self.balance
        self.slippage_rate = Decimal(str(slippage_rate)) if not isinstance(slippage_rate, Decimal) else slippage_rate
        self.commission_rate = Decimal(str(commission_rate)) if not isinstance(commission_rate, Decimal) else commission_rate
        
        self.positions: Dict[str, Position] = {}  # symbol -> Position
        self.orders: Dict[str, Order] = {}  # order_id -> Order
        self.open_orders: Dict[str, List[str]] = {}  # symbol -> [order_ids]
        self.market_prices: Dict[str, Decimal] = {}  # symbol -> current price
        
        # Subscribe to market data updates
        self._setup_event_listeners()

    def _setup_event_listeners(self) -> None:
        """Setup event listeners for market data updates."""
        # Subscribe to market data updates
        def on_market_data_update(event: Event):
            symbol = event.data.get("symbol")
            price = event.data.get("close")
            high = event.data.get("high")
            low = event.data.get("low")
            
            if symbol and price:
                # Update market price
                self.market_prices[symbol] = Decimal(str(price))
                
                # Try to match pending limit orders
                if high and low:
                    self._match_limit_orders(
                        symbol=symbol,
                        high=Decimal(str(high)),
                        low=Decimal(str(low)),
                        current_price=Decimal(str(price))
                    )
        
        self.event_bus.subscribe(EventType.BAR, on_market_data_update)

    def submit_order(self, order: Order) -> None:
        """Submit order for execution.

        Args:
            order: Order to submit
        """
        order.status = OrderStatus.SUBMITTED
        order.timestamp = self.clock.now()
        self.orders[order.id] = order
        
        if order.symbol not in self.open_orders:
            self.open_orders[order.symbol] = []
        self.open_orders[order.symbol].append(order.id)
        
        # For market orders, try to fill immediately
        if order.order_type == "market":
            current_price = self.market_prices.get(order.symbol)
            if current_price:
                self._fill_market_order(order, current_price)
        
        # Publish order submitted event
        self.event_bus.publish(
            Event(
                type=EventType.ORDER_SUBMITTED,
                timestamp=self.clock.now(),
                data={"order_id": order.id, "symbol": order.symbol, "type": order.order_type},
                source="PAPER",
            )
        )
        
        print(f"📝 [PAPER] 收到订单: {order.side.upper()} {order.quantity} {order.symbol} @ {order.price or 'MARKET'}")

    def _fill_market_order(self, order: Order, current_price: Decimal) -> None:
        """Fill a market order immediately at current price.

        Args:
            order: Market order to fill
            current_price: Current market price
        """
        # Apply slippage
        fill_price = current_price
        if order.side == "buy":
            fill_price = fill_price * (Decimal("1") + self.slippage_rate)
        else:
            fill_price = fill_price * (Decimal("1") - self.slippage_rate)
        
        # Calculate commission
        commission = order.quantity * fill_price * self.commission_rate
        
        # Create trade fill
        fill = TradeFill(
            id=str(len(self.orders) + 1),
            order_id=order.id,
            symbol=order.symbol,
            side=Side.LONG if order.side == "buy" else Side.SHORT,
            price=fill_price,
            quantity=order.quantity,
            commission=commission,
            timestamp=self.clock.now(),
        )
        
        # Update order status
        order.filled_quantity = fill.quantity
        order.avg_fill_price = fill.price
        order.status = OrderStatus.FILLED
        
        # Remove from open orders
        if order.symbol in self.open_orders and order.id in self.open_orders[order.symbol]:
            self.open_orders[order.symbol].remove(order.id)
        
        # Update position
        self._update_position_after_fill(fill)
        
        # Publish events
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
                source="PAPER",
            )
        )
        
        print(f"✅ [PAPER] 订单成交: {order.side.upper()} {order.quantity} {order.symbol} @ {fill.price}")

    def _match_limit_orders(
        self,
        symbol: str,
        high: Decimal,
        low: Decimal,
        current_price: Decimal,
    ) -> List[TradeFill]:
        """Match pending limit orders with current market data.

        Args:
            symbol: Trading pair symbol
            high: High price of current bar
            low: Low price of current bar
            current_price: Current market price

        Returns:
            List of trade fills
        """
        fills = []
        order_ids = self.open_orders.get(symbol, []).copy()
        
        for order_id in order_ids:
            order = self.orders[order_id]
            
            if not order.is_open or order.order_type != "limit":
                continue
            
            # Check if order can be filled
            fill_price = None
            if order.side == "buy" and low <= order.price:
                # Buy limit order: fill if low touches or goes below limit price
                fill_price = min(order.price, current_price)
            elif order.side == "sell" and high >= order.price:
                # Sell limit order: fill if high touches or goes above limit price
                fill_price = max(order.price, current_price)
            
            if fill_price is not None:
                # Apply slippage
                if order.side == "buy":
                    fill_price = fill_price * (Decimal("1") + self.slippage_rate)
                else:
                    fill_price = fill_price * (Decimal("1") - self.slippage_rate)
                
                # Calculate commission
                commission = order.remaining_quantity * fill_price * self.commission_rate
                
                # Create trade fill
                fill = TradeFill(
                    id=str(len(self.orders) + len(fills) + 1),
                    order_id=order.id,
                    symbol=order.symbol,
                    side=Side.LONG if order.side == "buy" else Side.SHORT,
                    price=fill_price,
                    quantity=order.remaining_quantity,
                    commission=commission,
                    timestamp=self.clock.now(),
                )
                
                # Update order status
                order.filled_quantity = fill.quantity
                order.avg_fill_price = fill.price
                order.status = OrderStatus.FILLED
                
                # Remove from open orders
                self.open_orders[symbol].remove(order.id)
                
                fills.append(fill)
                
                # Update position
                self._update_position_after_fill(fill)
                
                # Publish events
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
                        source="PAPER",
                    )
                )
                
                print(f"✅ [PAPER] 限价单成交: {order.side.upper()} {order.quantity} {order.symbol} @ {fill.price}")
        
        return fills

    def _update_position_after_fill(self, fill: TradeFill) -> None:
        """Update position after trade fill.

        Args:
            fill: Trade fill to apply
        """
        symbol = fill.symbol

        if symbol not in self.positions:
            # First position open
            side = Side.LONG if fill.side == Side.LONG else Side.SHORT
            self.positions[symbol] = PositionFactory.create_position(
                symbol=symbol,
                side=side,
                quantity=fill.quantity,
                entry_price=fill.price,
                leverage=1,
            )
            
            # Deduct commission when opening position
            self.balance -= fill.commission

            self.event_bus.publish(
                Event(
                    type=EventType.POSITION_OPENED,
                    timestamp=self.clock.now(),
                    data={"symbol": symbol, "side": side.value, "quantity": str(fill.quantity)},
                    source="PAPER",
                )
            )
        else:
            position = self.positions[symbol]

            # Check if adding or reducing position
            current_side = position.side
            new_side = fill.side

            if current_side == new_side:
                # Same direction: increase position
                position.increase(fill)
                # Deduct commission when adding to position
                self.balance -= fill.commission
            else:
                # Opposite direction: reduce or close position
                position_side_fill = fill.model_copy(update={"side": current_side})
                realized_pnl = position.decrease(position_side_fill)

                # Update balance: add realized PnL, subtract commission
                self.balance += realized_pnl - fill.commission

                if position.is_closed():
                    # Publish position closed event
                    self.event_bus.publish(
                        Event(
                            type=EventType.POSITION_CLOSED,
                            timestamp=self.clock.now(),
                            data={
                                "symbol": symbol,
                                "realized_pnl": str(realized_pnl),
                                "commission": str(fill.commission),
                            },
                            source="PAPER",
                        )
                    )
                    del self.positions[symbol]

    def cancel_order(self, order_id: str) -> bool:
        """Cancel order.

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
                source="PAPER",
            )
        )
        
        return True

    def get_position(self, symbol: str) -> Optional[Position]:
        """Get current position for symbol.

        Args:
            symbol: Trading pair symbol

        Returns:
            Position if exists, None otherwise
        """
        return self.positions.get(symbol)

    def get_balance(self) -> Decimal:
        """Get account balance.

        Returns:
            Current account balance including unrealized PnL
        """
        balance = self.balance
        
        # Add unrealized PnL from open positions
        for symbol, position in self.positions.items():
            current_price = self.market_prices.get(symbol)
            if current_price:
                unrealized_pnl = position.calculate_unrealized_pnl(current_price)
                balance += unrealized_pnl
        
        return balance

    def get_market_price(self, symbol: str) -> Optional[Decimal]:
        """Get current market price for symbol.

        Args:
            symbol: Trading pair symbol

        Returns:
            Current price if available, None otherwise
        """
        return self.market_prices.get(symbol)

    def get_account_summary(self) -> dict:
        """Get account summary.

        Returns:
            Dictionary containing account information
        """
        total_equity = self.get_balance()
        unrealized_pnl = total_equity - self.balance
        
        return {
            "balance": self.balance,
            "total_equity": total_equity,
            "unrealized_pnl": unrealized_pnl,
            "positions": len(self.positions),
            "open_orders": sum(len(orders) for orders in self.open_orders.values()),
            "total_return": ((total_equity - self.initial_balance) / self.initial_balance * 100) if self.initial_balance > 0 else Decimal("0"),
        }
