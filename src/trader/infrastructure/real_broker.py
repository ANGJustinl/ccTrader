
"""Real broker for connecting to Binance Testnet.

Provides real trading capabilities using Binance Testnet API.
"""
import os
import threading
import time
from decimal import Decimal
from datetime import datetime, timezone
from typing import Dict, List, Optional

import ccxt
from dotenv import load_dotenv

from ..domain.position import Position
from ..domain.services import PositionFactory
from ..domain.value_objects import Side, TradeFill
from .clock import SystemClock, IClock
from .event_bus import EventBus, Event, EventType
from ..application.order import Order, OrderStatus
from ..application.risk_manager import RiskManager
from .state_persistence import StatePersistence


class RealBroker:
    """Real broker for connecting to Binance Testnet.

    Provides real trading capabilities using Binance Testnet API.
    """

    def __init__(
        self,
        event_bus: EventBus,
        env_file: str = ".env.dev",
        testnet: bool = True,
        risk_manager: Optional[RiskManager] = None,
        state_persistence: Optional[StatePersistence] = None,
    ):
        """Initialize real broker.

        Args:
            event_bus: Event bus for publishing/subscribing events
            env_file: Path to environment file with API keys
            testnet: Whether to use testnet (default: True)
            risk_manager: Risk manager instance (optional)
            state_persistence: State persistence instance (optional)
        """
        self.clock = SystemClock()
        self.event_bus = event_bus

        # Thread safety lock
        self._lock = threading.Lock()

        # Risk management and persistence
        self.risk_manager = risk_manager
        self.state_persistence = state_persistence

        # Background sync thread
        self._sync_thread: Optional[threading.Thread] = None
        self._sync_running = False
        self._sync_interval = 5

        # Load environment variables
        load_dotenv(env_file)

        # Initialize exchange - use binance spot testnet (testnet.binance.vision)
        api_key = os.getenv("BINANCE_API_KEY") or ""
        api_secret = os.getenv("BINANCE_API_SECRET") or ""
        self.exchange = ccxt.binance(
            {
                "apiKey": api_key,
                "secret": api_secret,
                "enableRateLimit": True,
            }
        )

        if testnet:
            self.exchange.set_sandbox_mode(True)
            print("⚠️ [REAL] Using Binance Testnet (Sandbox Mode)")
        else:
            print("⚠️ [REAL] WARNING: Using LIVE Binance Exchange!")

        # Local cache
        self.positions: Dict[str, Position] = {}  # symbol -> Position
        self.orders: Dict[str, Order] = {}  # order_id -> Order
        self.market_prices: Dict[str, Decimal] = {}  # symbol -> current price
        self._last_filled_quantity: Dict[str, Decimal] = {}  # exchange_order_id -> last filled qty

        # Subscribe to market data updates
        self._setup_event_listeners()

        # Try to restore state from persistence
        self._try_restore_state()

    def _setup_event_listeners(self) -> None:
        """Setup event listeners for market data updates."""
        def on_market_data_update(event: Event):
            symbol = event.data.get("symbol")
            price = event.data.get("close")

            if symbol and price:
                with self._lock:
                    self.market_prices[symbol] = Decimal(str(price))

        self.event_bus.subscribe(EventType.BAR, on_market_data_update)

    def submit_order(self, order: Order) -> None:
        """Submit order to exchange.

        Args:
            order: Order to submit
        """
        try:
            # Risk check
            if self.risk_manager:
                current_balance = self.get_balance()
                with self._lock:
                    # Make copy of positions for risk check
                    positions_copy = dict(self.positions)
                
                passed, reason = self.risk_manager.check_order(order, current_balance, positions_copy)
                if not passed:
                    print(f"⚠️ [RISK] 订单被拒绝: {reason}")
                    with self._lock:
                        order.status = OrderStatus.REJECTED
                    return

            # First, update order status locally
            with self._lock:
                order.status = OrderStatus.SUBMITTED
                order.timestamp = self.clock.now()

            # Convert symbol format for Binance (BTC/USDT:USDT -> BTCUSDT)
            binance_symbol = order.symbol.replace("/", "").replace(":USDT", "")

            # Prepare order parameters
            side = "buy" if order.side == "buy" else "sell"
            type_ = "market" if order.order_type == "market" else "limit"

            params = {}
            if order.order_type == "limit" and order.price:
                params["price"] = float(order.price)

            # Submit order to exchange
            print(f"📝 [REAL] 提交订单: {order.side.upper()} {order.quantity} {order.symbol} @ {order.price or 'MARKET'}")

            exchange_order = self.exchange.create_order(  # type: ignore
                symbol=binance_symbol,
                type=type_,
                side=side,
                amount=float(order.quantity),
                **params
            )

            # Debug log: print full exchange order response
            print(f"🔍 [REAL] Exchange order response: status={exchange_order.get('status')}, filled={exchange_order.get('filled')}, id={exchange_order.get('id')}")

            # Update order with exchange ID - ONLY use exchange_order_id as key
            exchange_order_id = str(exchange_order["id"])
            with self._lock:
                self.orders[exchange_order_id] = order
                self._last_filled_quantity[exchange_order_id] = Decimal("0")

            # Publish order submitted event
            self.event_bus.publish(
                Event(
                    type=EventType.ORDER_SUBMITTED,
                    timestamp=self.clock.now(),
                    data={"order_id": order.id, "exchange_id": exchange_order_id, "symbol": order.symbol, "type": order.order_type},
                    source="REAL",
                )
            )

            # Check if order was filled immediately (market order)
            # Handle both "filled" and "closed" statuses (different exchanges use different terms)
            order_status = exchange_order.get("status")
            filled_qty = exchange_order.get("filled", 0)
            filled_qty_decimal = Decimal(str(filled_qty)) if filled_qty is not None else Decimal("0")
            if order_status in ["filled", "closed"] and filled_qty_decimal > Decimal("0"):
                print(f"🔍 [REAL] Order filled immediately! status={order_status}, filled={filled_qty}")
                self._handle_order_fill(exchange_order_id, exchange_order)  # type: ignore
            else:
                print(f"🔍 [REAL] Order not filled immediately. status={order_status}, filled={filled_qty}")

        except Exception as e:
            print(f"❌ [REAL] 提交订单失败: {e}")
            with self._lock:
                order.status = OrderStatus.REJECTED

    def _handle_order_fill(self, exchange_order_id: str, exchange_order: dict) -> None:
        """Handle order fill from exchange.

        Args:
            exchange_order_id: Exchange order ID
            exchange_order: Exchange order data
        """
        fill = None
        order = None
        with self._lock:
            order = self.orders.get(exchange_order_id)
            if not order:
                return

            # Get fill details
            fill_price = Decimal(str(exchange_order["price"]))
            fill_quantity = Decimal(str(exchange_order["filled"]))
            commission = Decimal("0")  # Get from exchange if available

            if exchange_order.get("trades"):
                trade = exchange_order["trades"][0]
                commission = Decimal(str(trade.get("fee", {}).get("cost", 0)))

            # Create trade fill
            fill = TradeFill(
                id=str(exchange_order["id"]),
                order_id=order.id,
                symbol=order.symbol,
                side=Side.LONG if order.side == "buy" else Side.SHORT,
                price=fill_price,
                quantity=fill_quantity,
                commission=commission,
                timestamp=datetime.fromtimestamp(exchange_order["timestamp"] / 1000, tz=timezone.utc),
            )

            # Update order status
            order.filled_quantity = fill_quantity
            order.avg_fill_price = fill_price
            order.status = OrderStatus.FILLED

            # Update position
            self._update_position_after_fill(fill)

        # Publish events (outside lock to prevent deadlock)
        if fill and order:
            self.event_bus.publish(
                Event(
                    type=EventType.ORDER_FILLED,
                    timestamp=self.clock.now(),
                    data={
                        "order_id": order.id,
                        "exchange_id": exchange_order_id,
                        "fill_id": fill.id,
                        "price": str(fill.price),
                        "quantity": str(fill.quantity),
                    },
                    source="REAL",
                )
            )

            print(f"✅ [REAL] 订单成交: {order.side.upper()} {order.quantity} {order.symbol} @ {fill.price}")

    def _handle_order_fill_delta(self, exchange_order_id: str, exchange_order: dict, delta: Decimal) -> None:
        """Handle incremental order fill.

        Args:
            exchange_order_id: Exchange order ID
            exchange_order: Exchange order data
            delta: Incremental filled quantity
        """
        fill = None
        order = None
        with self._lock:
            order = self.orders.get(exchange_order_id)
            if not order:
                return

            # Get fill details
            fill_price = Decimal(str(exchange_order.get("price", 0))) or self.market_prices.get(order.symbol, Decimal("0"))
            fill_quantity = delta
            commission = Decimal("0")

            if exchange_order.get("trades"):
                for trade in exchange_order["trades"]:
                    # Sum up commissions from all trades
                    commission += Decimal(str(trade.get("fee", {}).get("cost", 0)))

            # Create trade fill
            fill = TradeFill(
                id=str(exchange_order["id"]) + "_delta",
                order_id=order.id,
                symbol=order.symbol,
                side=Side.LONG if order.side == "buy" else Side.SHORT,
                price=fill_price,
                quantity=fill_quantity,
                commission=commission,
                timestamp=datetime.fromtimestamp(exchange_order.get("timestamp", time.time() * 1000) / 1000, tz=timezone.utc),
            )

            # Update order status
            order.filled_quantity += fill_quantity
            # Recalculate average fill price
            if order.filled_quantity > 0 and order.avg_fill_price is not None:
                order.avg_fill_price = ((order.avg_fill_price * (order.filled_quantity - delta)) + (fill_price * delta)) / order.filled_quantity
            elif order.filled_quantity > 0:
                order.avg_fill_price = fill_price

            # Update position
            self._update_position_after_fill(fill)

        # Publish events
        if fill and order:
            self.event_bus.publish(
                Event(
                    type=EventType.ORDER_FILLED,
                    timestamp=self.clock.now(),
                    data={
                        "order_id": order.id,
                        "exchange_id": exchange_order_id,
                        "fill_id": fill.id,
                        "price": str(fill.price),
                        "quantity": str(fill.quantity),
                        "partial": True,
                    },
                    source="REAL",
                )
            )

            print(f"📊 [REAL] 订单部分成交: +{delta} {order.symbol} @ {fill_price}, Total filled: {order.filled_quantity}/{order.quantity}")

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

            self.event_bus.publish(
                Event(
                    type=EventType.POSITION_OPENED,
                    timestamp=self.clock.now(),
                    data={"symbol": symbol, "side": side.value, "quantity": str(fill.quantity)},
                    source="REAL",
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
            else:
                # Opposite direction: reduce or close position
                position_side_fill = fill.model_copy(update={"side": current_side})
                realized_pnl = position.decrease(position_side_fill)

                if position.is_closed:
                    # Publish position closed event
                    self.event_bus.publish(
                        Event(
                            type=EventType.POSITION_CLOSED,
                            timestamp=self.clock.now(),
                            data={
                                "symbol": symbol,
                                "realized_pnl": str(realized_pnl),
                            },
                            source="REAL",
                        )
                    )
                    del self.positions[symbol]

    def _handle_order_partial_fill(self, exchange_order_id: str, exchange_order: dict) -> None:
        """Handle partially filled order.

        Args:
            exchange_order_id: Exchange order ID
            exchange_order: Exchange order data
        """
        prev_filled = self._last_filled_quantity.get(exchange_order_id, Decimal("0"))
        current_filled = Decimal(str(exchange_order.get("filled", 0)))
        delta = current_filled - prev_filled

        if delta > 0:
            order = None
            with self._lock:
                order = self.orders.get(exchange_order_id)
                if order:
                    order.status = OrderStatus.PARTIAL_FILLED
            if order:
                self._handle_order_fill_delta(exchange_order_id, exchange_order, delta)
                with self._lock:
                    self._last_filled_quantity[exchange_order_id] = current_filled

    def _sync_single_order(self, exchange_order_id: str) -> None:
        """Sync a single order from exchange.

        Args:
            exchange_order_id: Exchange order ID to sync
        """
        try:
            order = None
            symbol = None
            with self._lock:
                order = self.orders.get(exchange_order_id)
                if not order:
                    return
                symbol = order.symbol

            # Convert symbol format
            binance_symbol = symbol.replace("/", "").replace(":USDT", "") if symbol else ""

            # Fetch order from exchange
            exchange_order = self.exchange.fetch_order(exchange_order_id, binance_symbol)
            status = exchange_order.get("status")

            # Handle order status outside lock to avoid deadlock
            if status == "filled":
                # Order fully filled
                with self._lock:
                    order = self.orders.get(exchange_order_id)
                    if not order:
                        return
                    prev_filled = self._last_filled_quantity.get(exchange_order_id, Decimal("0"))
                
                current_filled = Decimal(str(exchange_order.get("filled", 0)))
                delta = current_filled - prev_filled

                if delta > 0:
                    self._handle_order_fill_delta(exchange_order_id, exchange_order, delta)
                    with self._lock:
                        self._last_filled_quantity[exchange_order_id] = current_filled

                with self._lock:
                    order = self.orders.get(exchange_order_id)
                    if order:
                        order.status = OrderStatus.FILLED

            elif status == "partially_filled":
                self._handle_order_partial_fill(exchange_order_id, exchange_order)

            elif status in ["canceled", "cancelled"]:
                with self._lock:
                    order = self.orders.get(exchange_order_id)
                    if order:
                        order.status = OrderStatus.CANCELLED
                self.event_bus.publish(
                    Event(
                        type=EventType.ORDER_CANCELLED,
                        timestamp=self.clock.now(),
                        data={"order_id": order.id if order else ""},
                        source="REAL",
                    )
                )

            elif status == "rejected":
                with self._lock:
                    order = self.orders.get(exchange_order_id)
                    if order:
                        order.status = OrderStatus.REJECTED

        except Exception as e:
            print(f"⚠️ [REAL] 同步订单 {exchange_order_id} 失败: {e}")

    def sync_open_orders(self) -> None:
        """Sync all open orders from exchange."""
        open_order_ids = []
        with self._lock:
            # Get all open order IDs from our cache
            open_order_ids = [
                oid for oid, order in self.orders.items()
                if order.status in [OrderStatus.SUBMITTED, OrderStatus.PARTIAL_FILLED]
            ]

        if not open_order_ids:
            return

        print(f"🔄 [REAL] 同步 {len(open_order_ids)} 个未结订单...")
        for exchange_order_id in open_order_ids:
            self._sync_single_order(exchange_order_id)

    def _sync_loop(self) -> None:
        """Background sync loop."""
        while self._sync_running:
            try:
                self.sync_open_orders()
            except Exception as e:
                print(f"❌ [REAL] 同步循环错误: {e}")
            time.sleep(self._sync_interval)

    def start_order_sync(self, interval: int = 5) -> None:
        """Start background order synchronization.

        Args:
            interval: Sync interval in seconds (default: 5)
        """
        if self._sync_running:
            print("⚠️ [REAL] 订单同步已在运行")
            return

        self._sync_interval = interval
        self._sync_running = True
        self._sync_thread = threading.Thread(target=self._sync_loop, daemon=True)
        self._sync_thread.start()
        print(f"✅ [REAL] 订单同步已启动 (间隔: {interval}秒)")

    def stop_order_sync(self) -> None:
        """Stop background order synchronization."""
        if not self._sync_running:
            return

        self._sync_running = False
        if self._sync_thread:
            self._sync_thread.join(timeout=10)
            self._sync_thread = None
        print("✅ [REAL] 订单同步已停止")

    def cancel_order(self, order_id: str) -> bool:
        """Cancel order on exchange.

        Args:
            order_id: Order ID to cancel

        Returns:
            True if order was cancelled, False otherwise
        """
        try:
            order = None
            with self._lock:
                order = self.orders.get(order_id)
                if not order or not order.is_open:
                    return False

            # Convert symbol format
            binance_symbol = order.symbol.replace("/", "").replace(":USDT", "")

            # Cancel order on exchange
            self.exchange.cancel_order(order_id, binance_symbol)

            with self._lock:
                order.status = OrderStatus.CANCELLED

            self.event_bus.publish(
                Event(
                    type=EventType.ORDER_CANCELLED,
                    timestamp=self.clock.now(),
                    data={"order_id": order_id},
                    source="REAL",
                )
            )

            return True
        except Exception as e:
            print(f"❌ [REAL] 取消订单失败: {e}")
            return False

    def get_position(self, symbol: str) -> Optional[Position]:
        """Get current position for symbol.

        Args:
            symbol: Trading pair symbol

        Returns:
            Position if exists, None otherwise
        """
        with self._lock:
            return self.positions.get(symbol)

    def get_balance(self) -> Decimal:
        """Get account balance from exchange.

        Returns:
            Current account balance including unrealized PnL
        """
        try:
            balance = Decimal("0")
            account_info = self.exchange.fetch_balance()

            # Get USDT balance
            usdt_balance = account_info.get("USDT", {}).get("free", 0)
            balance = Decimal(str(usdt_balance))

            # Add unrealized PnL from open positions
            with self._lock:
                for symbol, position in self.positions.items():
                    current_price = self.market_prices.get(symbol)
                    if current_price:
                        unrealized_pnl = position.calculate_unrealized_pnl(current_price)
                        balance += unrealized_pnl

            return balance
        except Exception as e:
            print(f"❌ [REAL] 获取余额失败: {e}")
            return Decimal("0")

    def get_market_price(self, symbol: str) -> Optional[Decimal]:
        """Get current market price for symbol.

        Args:
            symbol: Trading pair symbol

        Returns:
            Current price if available, None otherwise
        """
        # First check our cache
        with self._lock:
            if symbol in self.market_prices:
                return self.market_prices[symbol]
        
        # If not in cache, fetch from exchange
        try:
            ticker = self.exchange.fetch_ticker(symbol)
            if ticker and ticker.get("last"):
                price = Decimal(str(ticker["last"]))
                with self._lock:
                    self.market_prices[symbol] = price
                return price
        except Exception as e:
            print(f"⚠️ [REAL] 获取市场价格失败: {e}")
        
        return None

    def get_account_summary(self) -> dict:
        """Get account summary from exchange.

        Returns:
            Dictionary containing account information
        """
        try:
            total_equity = self.get_balance()

            # Get initial balance (try to fetch from exchange or estimate)
            initial_balance = Decimal("10000")  # Default
            try:
                account_info = self.exchange.fetch_balance()
                total_wallet_balance = account_info.get("total", {}).get("USDT", 0)
                if total_wallet_balance:
                    initial_balance = Decimal(str(total_wallet_balance))
            except:
                pass

            with self._lock:
                positions_count = len(self.positions)
                open_orders_count = len([o for o in self.orders.values() if o.is_open])

            return {
                "balance": total_equity,
                "equity": total_equity,
                "unrealized_pnl": Decimal("0"),
                "positions": positions_count,
                "open_orders": open_orders_count,
                "return_pct": ((total_equity - initial_balance) / initial_balance * 100) if initial_balance > 0 else Decimal("0"),
            }
        except Exception as e:
            print(f"❌ [REAL] 获取账户摘要失败: {e}")
            return {
                "balance": Decimal("0"),
                "equity": Decimal("0"),
                "unrealized_pnl": Decimal("0"),
                "positions": 0,
                "open_orders": 0,
                "return_pct": Decimal("0"),
            }

    def _try_restore_state(self) -> None:
        """Try to restore state from persistence."""
        if not self.state_persistence:
            return

        state = self.state_persistence.load_state()
        if not state:
            return

        try:
            with self._lock:
                # Restore positions
                self.positions = self.state_persistence.restore_positions(state)
                
                # Restore orders
                self.orders = self.state_persistence.restore_orders(state)
                
                # Restore risk manager state
                if self.risk_manager and "risk_manager" in state:
                    self.risk_manager.restore_state(state["risk_manager"])
            
            print("✅ [REAL] 状态恢复成功")
        except Exception as e:
            print(f"❌ [REAL] 状态恢复失败: {e}")

    def _save_state_periodically(self) -> None:
        """Save current state to persistence."""
        if not self.state_persistence:
            return

        try:
            balance = self.get_balance()
            
            # Update risk manager with current balance
            if self.risk_manager:
                self.risk_manager.update_balance(balance)
                risk_state = self.risk_manager.get_state()
            else:
                risk_state = {}

            with self._lock:
                # Make copies for thread safety
                positions_copy = dict(self.positions)
                orders_copy = dict(self.orders)

            self.state_persistence.save_state(
                positions=positions_copy,
                orders=orders_copy,
                risk_manager_state=risk_state,
                balance=balance,
            )
        except Exception as e:
            print(f"❌ [REAL] 状态保存失败: {e}")
