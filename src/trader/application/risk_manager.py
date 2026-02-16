"""
Risk Management System for Trading.

Provides multi-layer risk checks including:
- Max Drawdown Protection (>5% force liquidation)
- Fat Finger Check (>1 BTC rejection)
- Daily Loss Limit (>10% stop)
- Position Size Limit (>50% net value rejection)
- Rate Limiting (>100 req/min delay)
"""
import threading
import time
from decimal import Decimal
from typing import Dict, Tuple, List

from .order import Order
from ..domain.position import Position


class RiskManager:
    """Risk management system for trading operations."""

    def __init__(
        self,
        initial_balance: Decimal,
        max_drawdown_pct: Decimal = Decimal("0.05"),
        daily_loss_limit_pct: Decimal = Decimal("0.10"),
        max_order_size: Decimal = Decimal("1.0"),
        max_position_pct: Decimal = Decimal("0.5"),
        max_requests_per_window: int = 100,
        rate_limit_window: int = 60,
    ):
        """Initialize risk manager.

        Args:
            initial_balance: Initial account balance
            max_drawdown_pct: Maximum allowed drawdown percentage (default 5%)
            daily_loss_limit_pct: Maximum daily loss percentage (default 10%)
            max_order_size: Maximum single order size (default 1 BTC)
            max_position_pct: Maximum position as percentage of net value (default 50%)
            max_requests_per_window: Maximum requests per rate limit window (default 100)
            rate_limit_window: Rate limit window in seconds (default 60)
        """
        self._lock = threading.Lock()
        
        self.initial_balance = initial_balance
        self.peak_balance = initial_balance
        self.current_balance = initial_balance
        self.current_drawdown = Decimal("0")
        self.daily_pnl = Decimal("0")
        self.trading_halted = False

        # Risk configuration
        self.max_drawdown_pct = max_drawdown_pct
        self.daily_loss_limit_pct = daily_loss_limit_pct
        self.max_order_size = max_order_size
        self.max_position_pct = max_position_pct
        
        # Rate limiting
        self.rate_limit_window = rate_limit_window
        self.max_requests_per_window = max_requests_per_window
        self.request_timestamps: List[float] = []

        print(f"🛡️ [RISK] Risk manager initialized")
        print(f"   Initial balance: ${initial_balance:,.2f}")
        print(f"   Max drawdown: {max_drawdown_pct * 100:.1f}%")
        print(f"   Daily loss limit: {daily_loss_limit_pct * 100:.1f}%")
        print(f"   Max order size: {max_order_size} BTC")
        print(f"   Max position: {max_position_pct * 100:.1f}% of net value")

    def check_order(
        self,
        order: Order,
        current_balance: Decimal,
        positions: Dict[str, Position],
    ) -> Tuple[bool, str]:
        """Check if order passes all risk checks.

        Args:
            order: Order to check
            current_balance: Current account balance
            positions: Current open positions

        Returns:
            Tuple of (is_approved, reason)
        """
        with self._lock:
            if self.trading_halted:
                return False, "Trading halted by risk manager"

            checks = [
                self._check_fat_finger(order),
                self._check_position_size(order, current_balance, positions),
                self._check_drawdown(current_balance),
                self._check_daily_loss_limit(),
                self._check_rate_limit(),
            ]

            for passed, reason in checks:
                if not passed:
                    print(f"⚠️ [RISK] 订单拒绝: {reason}")
                    return False, reason

            return True, "Order approved"

    def update_balance(self, new_balance: Decimal) -> None:
        """Update balance and calculate drawdown.

        Args:
            new_balance: New account balance
        """
        with self._lock:
            old_balance = self.current_balance
            self.current_balance = new_balance
            self.daily_pnl += new_balance - old_balance

            if new_balance > self.peak_balance:
                self.peak_balance = new_balance
                print(f"📈 [RISK] 新高净值: ${self.peak_balance:,.2f}")

            if self.peak_balance > Decimal("0"):
                self.current_drawdown = (self.peak_balance - new_balance) / self.peak_balance
                
                if self.current_drawdown >= self.max_drawdown_pct:
                    self.trading_halted = True
                    print(f"🔥 [RISK] 熔断触发! 回撤 {self.current_drawdown * 100:.2f}% 超过阈值")
                    print("   强制平仓并停止交易")

            if self.daily_pnl <= -self.initial_balance * self.daily_loss_limit_pct:
                self.trading_halted = True
                print(f"🔥 [RISK] 日亏损限制触发! 亏损 ${-self.daily_pnl:,.2f}")

    def get_state(self) -> dict:
        """Get current risk manager state for persistence.

        Returns:
            Dictionary containing risk manager state
        """
        with self._lock:
            return {
                "initial_balance": str(self.initial_balance),
                "peak_balance": str(self.peak_balance),
                "current_balance": str(self.current_balance),
                "current_drawdown": str(self.current_drawdown),
                "daily_pnl": str(self.daily_pnl),
                "trading_halted": self.trading_halted,
            }

    def restore_state(self, state: dict) -> None:
        """Restore risk manager state from persistence.

        Args:
            state: Dictionary containing risk manager state
        """
        with self._lock:
            self.initial_balance = Decimal(state.get("initial_balance", str(self.initial_balance)))
            self.peak_balance = Decimal(state.get("peak_balance", str(self.peak_balance)))
            self.current_balance = Decimal(state.get("current_balance", str(self.current_balance)))
            self.current_drawdown = Decimal(state.get("current_drawdown", "0"))
            self.daily_pnl = Decimal(state.get("daily_pnl", "0"))
            self.trading_halted = state.get("trading_halted", False)
            print(f"📂 [RISK] 状态已恢复")
            print(f"   当前余额: ${self.current_balance:,.2f}")
            print(f"   回撤: {self.current_drawdown * 100:.2f}%")
            print(f"   交易暂停: {self.trading_halted}")

    def _check_fat_finger(self, order: Order) -> Tuple[bool, str]:
        """Check for fat finger orders (too large)."""
        if order.quantity > self.max_order_size:
            return False, f"Fat finger: order size {order.quantity} exceeds max {self.max_order_size}"
        return True, ""

    def _check_position_size(
        self,
        order: Order,
        current_balance: Decimal,
        positions: Dict[str, Position],
    ) -> Tuple[bool, str]:
        """Check if adding position exceeds net value limit.
        
        For leveraged positions, compare margin (notional / leverage) 
        instead of raw notional value.
        """
        if current_balance <= Decimal("0"):
            return False, "No available balance"

        # Get current position for symbol
        current_position = positions.get(order.symbol)
        current_position_value = Decimal("0")
        
        if current_position and current_position.quantity > Decimal("0"):
            # Use margin (entry_price * qty / leverage) for leveraged positions
            leverage = Decimal(str(current_position.leverage)) if current_position.leverage > 1 else Decimal("1")
            current_position_value = (current_position.quantity * current_position.entry_price) / leverage

        # Estimate new order margin
        order_price = order.price if order.price else Decimal("50000")  # Fallback price
        order_notional = order.quantity * order_price
        # Determine leverage from existing position or default to 1
        leverage = Decimal("1")
        if current_position and current_position.leverage > 1:
            leverage = Decimal(str(current_position.leverage))
        elif hasattr(self, '_leverage'):
            leverage = Decimal(str(self._leverage))
        order_margin = order_notional / leverage
        
        total_margin = current_position_value + order_margin

        max_allowed_value = current_balance * self.max_position_pct
        
        if total_margin > max_allowed_value:
            return False, (
                f"Position margin limit: {total_margin:,.2f} exceeds "
                f"{self.max_position_pct * 100:.1f}% of balance ({max_allowed_value:,.2f})"
            )

        return True, ""

    def _check_drawdown(self, current_balance: Decimal) -> Tuple[bool, str]:
        """Check if drawdown exceeds limit."""
        if self.peak_balance > Decimal("0"):
            drawdown = (self.peak_balance - current_balance) / self.peak_balance
            if drawdown >= self.max_drawdown_pct:
                self.trading_halted = True
                return False, f"Max drawdown exceeded: {drawdown * 100:.2f}%"
        return True, ""

    def _check_daily_loss_limit(self) -> Tuple[bool, str]:
        """Check if daily loss limit has been reached."""
        if self.daily_pnl <= -self.initial_balance * self.daily_loss_limit_pct:
            self.trading_halted = True
            return False, f"Daily loss limit reached: ${-self.daily_pnl:,.2f}"
        return True, ""

    def _check_rate_limit(self) -> Tuple[bool, str]:
        """Check and enforce rate limiting."""
        now = time.time()
        window_start = now - self.rate_limit_window

        # Remove old timestamps
        self.request_timestamps = [ts for ts in self.request_timestamps if ts > window_start]

        if len(self.request_timestamps) >= self.max_requests_per_window:
            return False, f"Rate limit exceeded: {len(self.request_timestamps)} requests in {self.rate_limit_window}s"

        # Record this request
        self.request_timestamps.append(now)
        return True, ""
