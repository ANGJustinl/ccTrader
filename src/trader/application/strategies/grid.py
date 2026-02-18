from decimal import Decimal
from typing import List, Optional, Dict
from trader.application.strategy import BaseStrategy
from trader.application.order import Order
from trader.utils.indicators import calculate_atr, calculate_bollinger_bands, calculate_ema

class DynamicGridStrategy(BaseStrategy):
    """
    Dynamic Grid Strategy based on ATR and Bollinger Bands.
    
    Logic:
    1. Pivot: Bollinger Middle Band (SMA 20)
    2. Range: [Pivot - k*ATR, Pivot + k*ATR]
    3. Grids: Dynamically calculated to ensure earnings > 2 * commission
    4. Risk: Stop trading/Cut loss if price breaks range
    """
    
    def __init__(self, 
                 name: str = "DynamicGrid",
                 symbol: str = "BTCUSDT",
                 grid_number: int = 10, 
                 atr_multiplier: float = 2.0,
                 min_profit_per_grid: float = 0.003, # 0.3% profit covers ~0.08% fees
                 stop_loss_buffer: float = 0.005, # Buffer beyond range for stop loss
                 position_size: float = 0.01,
                 trend_filter_enabled: bool = True,
                 trend_ema_period: int = 50,
                 grid_spacing: str = "arithmetic",
                 leverage: int = 1,
                 capital_usage: float = 0.5):  # Use 50% of account by default
        super().__init__(name)
        self.symbol = symbol
        self.grid_number = grid_number
        self.atr_multiplier = Decimal(str(atr_multiplier))
        self.min_profit = Decimal(str(min_profit_per_grid))
        self.stop_loss_buffer = Decimal(str(stop_loss_buffer))
        self.position_size = Decimal(str(position_size))
        self.trend_filter_enabled = trend_filter_enabled
        self.trend_ema_period = trend_ema_period
        self.grid_spacing = grid_spacing
        self.leverage = leverage
        self.capital_usage = Decimal(str(capital_usage))
        self.trend_direction: Optional[str] = None # "UP" or "DOWN"
        
        # Grid State
        self.grid_lines: List[Decimal] = [] # List of price levels
        self.pivot_price: Optional[Decimal] = None
        self.upper_limit: Optional[Decimal] = None
        self.lower_limit: Optional[Decimal] = None
        self.grid_orders: Dict[str, Decimal] = {} # order_id -> grid_price
        self.order_fill_tracking: Dict[str, Decimal] = {} # order_id -> filled_qty
        
        # Indicators
        self.atr_period = 14
        self.bb_period = 20
        self.bb_std = Decimal("2.0")
        
        # Data History
        self.bar_history = []
        self.min_history = max(self.atr_period, self.bb_period) + 5

    def on_bar(self, bar):
        # 0. Update History
        self.bar_history.append(bar)
        if len(self.bar_history) > self.min_history + 50:
            self.bar_history.pop(0)
            
        if len(self.bar_history) < self.min_history:
            if len(self.bar_history) % 10 == 1:
                print(f"[Grid DEBUG] Collecting bars: {len(self.bar_history)}/{self.min_history}")
            return

        # Prepare data for indicators (Decimal)

        # Prepare data for indicators (Decimal)
        closes = [b.close for b in self.bar_history]
        highs = [b.high for b in self.bar_history]
        lows = [b.low for b in self.bar_history]

        # 1. Calculate Indicators
        atr_values = calculate_atr(highs, lows, closes, period=self.atr_period)
        if not atr_values or atr_values[-1] is None:
            print("ATR is None")
            return
        atr = atr_values[-1]
        
        bb_values = calculate_bollinger_bands(closes, period=self.bb_period, std_dev=self.bb_std)
        if not bb_values or bb_values[-1].middle is None:
            print("BB Middle is None")
            return
        pivot = bb_values[-1].middle
        
        current_price = bar.close

        # Calculate Trend EMA
        self.trend_direction = None
        if self.trend_filter_enabled:
             ema_values = calculate_ema(closes, period=self.trend_ema_period)
             if ema_values and ema_values[-1] is not None:
                 if current_price > ema_values[-1]:
                     self.trend_direction = "UP"
                 else:
                     self.trend_direction = "DOWN"
                 # print(f"[Grid] Trend: {self.trend_direction} (Price={current_price}, EMA={ema_values[-1]:.2f})")
        
        # print(f"DEBUG: Indics - ATR={atr:.2f}, pivot={pivot:.2f}, price={current_price:.2f}")

        # 2. Active Grid: Check and Reset
        if self.grid_lines:
            self.check_and_reset_grid(current_price)

        # 3. Initialize Grid if not exists
        active_orders = self.broker.get_open_orders(self.symbol)
        position = self.broker.get_position(self.symbol)
        if hasattr(position, 'quantity') and position.quantity == 0:
             position = None
        
        if not self.grid_lines and not active_orders:
            # Initialize grid (even if position exists - we build around it)
            print(f"[Grid DEBUG] Initializing grid: pivot={pivot:.2f}, atr={atr:.4f}, price={current_price:.4f}")
            self._calculate_and_place_grids(pivot, atr, current_price)
        elif self.grid_lines:
            pass
        else:
            # print(f"[Grid DEBUG] Skip init: grid_lines={len(self.grid_lines)}, active_orders={len(active_orders)}, position={position}")
            pass

    def check_and_reset_grid(self, current_price: Decimal):
        """Check if price drifted too far and reset grid if needed."""
        if not self.grid_lines:
            return

        # Trigger reset if price hits the boundaries (instead of stopping)
        # Using a buffer to trigger slightly before/after the exact limit to capture trend
        reset_needed = False
        
        if current_price >= self.upper_limit:
            print(f"🔄 [Grid] Price ({current_price:.2f}) hit UPPER limit ({self.upper_limit:.2f}). Resetting grid UP...")
            reset_needed = True
        elif current_price <= self.lower_limit:
            print(f"🔄 [Grid] Price ({current_price:.2f}) hit LOWER limit ({self.lower_limit:.2f}). Resetting grid DOWN...")
            reset_needed = True
            
        if reset_needed:
            self.cancel_and_reset_grid(current_price)

    def cancel_and_reset_grid(self, current_price: Decimal):
        """Cancel all orders and restart grid at new price."""
        print(f"🔄 [Grid] Executing Dynamic Reset at {current_price:.2f}...")
        
        # 1. Cancel all open orders
        try:
            if self.broker:
                self.broker.cancel_all_orders(self.symbol)
        except Exception as e:
            print(f"⚠️ [Grid] Failed to cancel orders during reset: {e}")
            
        # 2. Reset Grid State
        self.grid_lines = []
        self.upper_limit = None
        self.lower_limit = None
        
        # 3. Recalculate and Place New Grid
        # Recalculate indicators for new pivot
        if len(self.bar_history) < self.min_history:
             print("⚠️ [Grid] Not enough history for reset. Waiting next bar.")
             return
             
        closes = [b.close for b in self.bar_history]
        ema_values = calculate_ema(closes, period=self.trend_ema_period)
        bb_values = calculate_bollinger_bands(closes, period=self.bb_period, std_dev=self.bb_std)
        atr_values = calculate_atr([b.high for b in self.bar_history], [b.low for b in self.bar_history], closes, period=self.atr_period)

        if not (ema_values and bb_values and atr_values):
            print("⚠️ [Grid] Indicators unavailable for reset.")
            return
            
        # Use EMA as pivot for trend following, or BB Middle for mean reversion
        # Active Grid V2 favors following the drift, so we anchor to current price or EMA
        # Here we use BB Middle (SMA 20) as the "fair value" anchor, but ensure range covers current price
        pivot = bb_values[-1].middle
        atr = atr_values[-1]
        
        print(f"🔄 [Grid] Re-initializing: Pivot={pivot:.2f}, ATR={atr:.2f}")
        self._calculate_and_place_grids(pivot, atr, current_price)

    def _calculate_and_place_grids(self, pivot: Decimal, atr: Decimal, current_price: Decimal):
        """Calculate grid levels and place initial orders"""
        
        range_width = atr * self.atr_multiplier
        
        # Active Grid V2: Ensure range always brackets current price
        # If current price is far from pivot, shift pivot to current price to center the grid
        if abs(current_price - pivot) > (range_width * Decimal("0.5")):
            print(f"⚡ [Grid] Price far from pivot. Centering grid on Price {current_price:.2f} instead of SMA {pivot:.2f}")
            pivot = current_price
            
        self.upper_limit = pivot + range_width
        self.lower_limit = pivot - range_width
        self.pivot_price = pivot
        
        if self.upper_limit <= self.lower_limit:
            return

        # Dynamic Grid Count Calculation
        if self.grid_spacing == "geometric":
            # Geometric: Price_i = Lower * (Ratio ^ i)
            # Ratio = (Upper / Lower) ^ (1 / N)
            # Min Ratio required = 1 + Min Profit
            min_ratio = Decimal("1") + self.min_profit
            import math
            # max_grids = log(Upper/Lower) / log(min_ratio)
            try:
                max_grids = int(math.log(float(self.upper_limit / self.lower_limit)) / math.log(float(min_ratio)))
            except ValueError:
                max_grids = self.grid_number
        else:
            # Arithmetic: Step = Range / N
            # Total Range = Upper - Lower
            total_range = self.upper_limit - self.lower_limit
            # Min price step required
            min_step = current_price * self.min_profit
            # Max possible grids
            max_grids = int(total_range / min_step)
        
        # Use min(configured, calculated) to ensure profit
        actual_grids = min(self.grid_number, max_grids)
        if actual_grids < 3:
            print(f"[Grid] Volatility too low for grid. Spacing: {self.grid_spacing}. Skipping.")
            return

        self.grid_lines = []
        step_size = Decimal("0") # Just for logging/check in arithmetic

        # === Dynamic Position Sizing ===
        balance = self.broker.get_balance() if self.broker else Decimal("5000")
        available_capital = balance * self.capital_usage * Decimal(str(self.leverage))
        qty_per_grid = available_capital / (Decimal(str(actual_grids)) * current_price)
        
        # Determine precision based on price scale or generic safe bet (5 decimals)
        # TODO: Fetch lot size from exchange metadata if possible
        precision = Decimal("0.00001")
        qty_per_grid = (qty_per_grid / precision).to_integral_value(rounding='ROUND_DOWN') * precision
        
        if qty_per_grid < precision:
            print(f"[Grid] Calculated qty too small: {qty_per_grid}. Skipping.")
            return
        self.position_size = qty_per_grid
        print(f"[Grid] Dynamic position size: {qty_per_grid} (Balance={balance:.2f}, Leverage={self.leverage}x, Usage={self.capital_usage*100:.0f}%, Grids={actual_grids})")

        if self.grid_spacing == "geometric":
             # Calculate Ratio
             ratio = (self.upper_limit / self.lower_limit) ** (Decimal("1") / Decimal(actual_grids))
             print(f"[Grid] Initializing (Geometric): Range=[{self.lower_limit:.2f}, {self.upper_limit:.2f}], Grids={actual_grids}, Ratio={ratio:.4f}")
             
             for i in range(actual_grids + 1):
                 level = self.lower_limit * (ratio ** i)
                 self.grid_lines.append(level)
                 
             # For check below, define approximate step size at current price
             step_size = current_price * (ratio - Decimal("1"))
             
        else:
            # Arithmetic
            total_range = self.upper_limit - self.lower_limit
            step_size = total_range / Decimal(actual_grids)
            
            print(f"[Grid] Initializing (Arithmetic): Pivot={pivot}, ATR={atr}, Range=[{self.lower_limit}, {self.upper_limit}], Grids={actual_grids}, Step={step_size}")
            
            for i in range(actual_grids + 1):
                level = self.lower_limit + (Decimal(i) * step_size)
                self.grid_lines.append(level)
            
        # Place Orders
        # Active Grid V2 Logic:
        # If Trend Filter enabled:
        # UP Trend (Price > EMA) -> Only Place BUY grids (or skewed)? 
        # Actually for a grid, "Buying in Uptrend" means buying dips. "Selling in Uptrend" means selling rallies (taking profit).
        # A Neutral Grid captures both. 
        # But if the trend is STRONG UP, Shorting at the top of range is risky (price blows through).
        # So we restrict opening NEW Short positions (Sell Orders) if trend is UP? 
        # No, a grid MUST sell to close the buy. 
        # The risk is opening a *naked* short grid at the top.
        # For simplicity in V2: We allow both, but relied on Reset to handle drift. 
        # Or we can implement "Long Only" grid for Uptrend (Only Buy orders below price, and Sell orders ONLY to close positions).
        # But Broker doesn't track "Close" vs "Open" easily without position management.
        # Let's stick to Standard Grid but with Dynamic Reset for now.
        
        self.grid_orders = {}
        batch_orders = []
        
        for level in self.grid_lines:
            # Skip levels too close (within 10% of step)
            if abs(level - current_price) < (step_size * Decimal("0.1")):
                continue
                
            # Trend Filter (Optional - Strict Mode)
            # If UP trend, maybe we skip the highest sell orders to avoid getting run over?
            # For now, we trust the Reset logic to cut losses if it blows through.
            
            if level > current_price:
                self.create_limit_order(self.symbol, "sell", float(self.position_size), float(level))
            else:
                self.create_limit_order(self.symbol, "buy", float(self.position_size), float(level))

    def on_order_update(self, order: Order):
        """Handle filled orders to place counter-orders"""
        # Track filled quantity to handle partial fills
        last_filled = self.order_fill_tracking.get(order.id, Decimal("0"))
        current_filled = order.filled_quantity
        new_fill_qty = current_filled - last_filled
        
        if new_fill_qty > Decimal("0"):
            self.order_fill_tracking[order.id] = current_filled
            
            print(f"[Grid] Order Fill Update: {order.side} +{new_fill_qty} (Total: {current_filled}/{order.quantity}) @ {order.price}")
            
            # Simple approach: Find closest grid line
            fill_price = Decimal(str(order.price)) if order.price else order.avg_fill_price
            if not fill_price:
                return

            # Find index of this grid line
            closest_level = min(self.grid_lines, key=lambda x: abs(x - fill_price))
            
            if order.side == "buy":
                # User bought, now sell higher
                try:
                    idx = self.grid_lines.index(closest_level)
                    if idx + 1 < len(self.grid_lines):
                        target_level = self.grid_lines[idx + 1]
                        self.create_limit_order(self.symbol, "sell", float(new_fill_qty), float(target_level))
                        print(f"[Grid] Placing Counter SELL @ {target_level} (Qty: {new_fill_qty})")
                except ValueError:
                    pass
            elif order.side == "sell":
                # User sold, now buy lower
                try:
                    idx = self.grid_lines.index(closest_level)
                    if idx - 1 >= 0:
                        target_level = self.grid_lines[idx - 1]
                        self.create_limit_order(self.symbol, "buy", float(new_fill_qty), float(target_level))
                        print(f"[Grid] Placing Counter BUY @ {target_level} (Qty: {new_fill_qty})")
                except ValueError:
                    pass

        # Cleanup if order is closed
        if order.status in ["filled", "cancelled", "rejected", "expired"]:
            if order.id in self.order_fill_tracking:
                del self.order_fill_tracking[order.id]

    def _handle_breakout(self, direction: str, current_price: Decimal):
        """Handle active grid breakout"""
        # Cancel all open orders to stop adding risk
        self.broker.cancel_all_orders(self.symbol)
        
        # Reset grid lines
        self.grid_lines = []
        
        # Check Stop Loss Trigger
        position = self.broker.get_position(self.symbol)
        if hasattr(position, 'quantity') and position.quantity > 0:
            # Need to import Side enum or check string
            # Position.side is likely an Enum but we can check value
            side_str = str(position.side).split('.')[-1] if '.' in str(position.side) else str(position.side)
            
            do_close = False
            stop_thresh = Decimal("0")
            
            if direction == "UP" and side_str == "SHORT":
                stop_thresh = self.upper_limit * (Decimal("1") + self.stop_loss_buffer)
                if current_price >= stop_thresh:
                    do_close = True
            elif direction == "DOWN" and side_str == "LONG":
                stop_thresh = self.lower_limit * (Decimal("1") - self.stop_loss_buffer)
                if current_price <= stop_thresh:
                    do_close = True
            
            if do_close:
                print(f"[Grid] Stop Loss Triggered! ({current_price} crossed {stop_thresh:.2f}). Closing {side_str} position.")
                # Execute Market Close
                close_side = "buy" if side_str == "SHORT" else "sell"
                self.create_market_order(self.symbol, close_side, float(position.quantity))
            else:
                print(f"[Grid] Breakout {direction}. Position {side_str} held (Price {current_price} within buffer {self.stop_loss_buffer}).")
        else:
            print(f"[Grid] Breakout {direction} detected. No position to close.")
