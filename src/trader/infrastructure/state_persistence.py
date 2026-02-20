"""
State Persistence for Trading System.

Provides JSON-based persistence for trading state including:
- Positions
- Orders
- Risk Manager state
- Balance snapshot
"""
import json
import threading
from pathlib import Path
from datetime import datetime
from decimal import Decimal
from typing import Dict, Optional

from ..domain.position import Position
from ..domain.value_objects import Side
from ..application.order import Order, OrderStatus


class StatePersistence:
    """State persistence manager for trading system."""

    def __init__(self, storage_path: str = "data/trader_state.json"):
        """Initialize state persistence.

        Args:
            storage_path: Path to JSON storage file
        """
        self._lock = threading.Lock()
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(exist_ok=True)
        print(f"💾 [PERSIST] State persistence initialized at {self.storage_path}")

    def save_state(
        self,
        positions: Dict[str, Position],
        orders: Dict[str, Order],
        risk_manager_state: dict,
        balance: Decimal,
        leverage_map: Dict[str, int] = {},
        last_filled_quantity: Dict[str, Decimal] = {},
    ) -> None:
        """Save current state to JSON.

        Args:
            positions: Dictionary of current positions
            orders: Dictionary of current orders
            risk_manager_state: Risk manager state dictionary
            balance: Current account balance
        """
        with self._lock:
            try:
                state = {
                    "timestamp": datetime.utcnow().isoformat(),
                    "balance": str(balance),
                    "risk_manager": risk_manager_state,
                    "positions": {
                        symbol: self._position_to_dict(pos)
                        for symbol, pos in positions.items()
                    },
                    "orders": {
                        order_id: self._order_to_dict(order)
                        for order_id, order in orders.items()
                        if order.status in [OrderStatus.PENDING, OrderStatus.SUBMITTED, OrderStatus.PARTIAL_FILLED]
                    },
                    "leverage_map": leverage_map,
                    "last_filled_quantity": {
                        oid: str(qty) for oid, qty in last_filled_quantity.items()
                    },
                }

                with open(self.storage_path, "w", encoding="utf-8") as f:
                    json.dump(state, f, indent=2, ensure_ascii=False)

                # Only print if not called too frequently 
                # (suppress in silent mode by checking caller)

            except Exception as e:
                print(f"❌ [PERSIST] 保存状态失败: {e}")

    def load_state(self) -> Optional[dict]:
        """Load state from JSON.

        Returns:
            State dictionary if file exists, None otherwise
        """
        with self._lock:
            if not self.storage_path.exists():
                print(f"📂 [PERSIST] 状态文件不存在: {self.storage_path}")
                return None

            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    state = json.load(f)

                print(f"📂 [PERSIST] 状态已加载: {self.storage_path}")
                print(f"   时间: {state.get('timestamp', 'unknown')}")
                print(f"   余额: ${state.get('balance', '0')}")
                print(f"   持仓: {len(state.get('positions', {}))} 个")
                print(f"   订单: {len(state.get('orders', {}))} 个")

                return state

            except Exception as e:
                print(f"❌ [PERSIST] 加载状态失败: {e}")
                return None

    def restore_positions(self, state: dict) -> Dict[str, Position]:
        """Restore positions from loaded state.

        Args:
            state: Loaded state dictionary

        Returns:
            Dictionary of restored positions
        """
        positions = {}
        positions_data = state.get("positions", {})

        for symbol, pos_dict in positions_data.items():
            try:
                positions[symbol] = self._dict_to_position(pos_dict)
            except Exception as e:
                print(f"⚠️ [PERSIST] 恢复持仓失败 {symbol}: {e}")

        return positions

    def restore_orders(self, state: dict) -> Dict[str, Order]:
        """Restore orders from loaded state."""
        orders = {}
        orders_data = state.get("orders", {})
        for order_id, order_dict in orders_data.items():
            try:
                orders[order_id] = self._dict_to_order(order_dict)
            except Exception as e:
                print(f"⚠️ [PERSIST] 恢复订单失败 {order_id}: {e}")
        return orders

    def restore_leverage(self, state: dict) -> Dict[str, int]:
        """Restore leverage map from loaded state."""
        return state.get("leverage_map", {})

    def restore_last_filled(self, state: dict) -> Dict[str, Decimal]:
        """Restore last filled quantities from loaded state."""
        last_filled = {}
        data = state.get("last_filled_quantity", {})
        for oid, qty_str in data.items():
            last_filled[oid] = Decimal(qty_str)
        return last_filled

    def _position_to_dict(self, position: Position) -> dict:
        """Convert Position to serializable dictionary.

        Args:
            position: Position object

        Returns:
            Serializable dictionary
        """
        return {
            "symbol": position.symbol,
            "side": position.side.value,
            "quantity": str(position.quantity),
            "entry_price": str(position.entry_price),
            "leverage": position.leverage,
            "liquidation_price": str(position.liquidation_price) if position.liquidation_price else None,
            "maintenance_margin_rate": str(position.maintenance_margin_rate),
        }

    def _dict_to_position(self, pos_dict: dict) -> Position:
        """Convert dictionary back to Position object.

        Args:
            pos_dict: Position dictionary

        Returns:
            Position object
        """
        side = Side.LONG if pos_dict["side"] == "LONG" else Side.SHORT
        return Position(
            symbol=pos_dict["symbol"],
            side=side,
            quantity=Decimal(pos_dict["quantity"]),
            entry_price=Decimal(pos_dict["entry_price"]),
            leverage=pos_dict.get("leverage", 1),
            liquidation_price=Decimal(pos_dict["liquidation_price"]) if pos_dict.get("liquidation_price") else None,
            maintenance_margin_rate=Decimal(pos_dict.get("maintenance_margin_rate", "0.005")),
        )

    def _order_to_dict(self, order: Order) -> dict:
        """Convert Order to serializable dictionary.

        Args:
            order: Order object

        Returns:
            Serializable dictionary
        """
        return {
            "id": order.id,
            "symbol": order.symbol,
            "side": order.side,
            "order_type": order.order_type,
            "quantity": str(order.quantity),
            "price": str(order.price) if order.price else None,
            "status": order.status.value,
            "filled_quantity": str(order.filled_quantity),
            "avg_fill_price": str(order.avg_fill_price) if order.avg_fill_price else None,
            "timestamp": order.timestamp.isoformat() if order.timestamp else None,
            "create_time": order.create_time.isoformat() if order.create_time else None,
        }

    def _dict_to_order(self, order_dict: dict) -> Order:
        """Convert dictionary back to Order object.

        Args:
            order_dict: Order dictionary

        Returns:
            Order object
        """
        timestamp = datetime.now()
        if order_dict.get("timestamp"):
            timestamp = datetime.fromisoformat(order_dict["timestamp"])

        create_time = datetime.now()
        if order_dict.get("create_time"):
            create_time = datetime.fromisoformat(order_dict["create_time"])

        return Order(
            id=order_dict["id"],
            symbol=order_dict["symbol"],
            side=order_dict["side"],
            order_type=order_dict["order_type"],
            quantity=Decimal(order_dict["quantity"]),
            price=Decimal(order_dict["price"]) if order_dict.get("price") else None,
            status=OrderStatus(order_dict["status"]),
            filled_quantity=Decimal(order_dict.get("filled_quantity", "0")),
            avg_fill_price=Decimal(order_dict["avg_fill_price"]) if order_dict.get("avg_fill_price") else None,
            timestamp=timestamp,
            create_time=create_time,
        )
