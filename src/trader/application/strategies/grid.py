from decimal import Decimal
from typing import List, Optional, Dict
from trader.application.strategy import BaseStrategy
from trader.application.order import Order
from trader.utils.indicators import calculate_atr, calculate_bollinger_bands, calculate_ema, calculate_sma

class DynamicGridStrategy(BaseStrategy):
    """
    Dynamic Grid Strategy based on ATR and Bollinger Bands.
    
    Logic:
    1. Pivot: Bollinger Middle Band (SMA 20)
    2. Range: [Pivot - k*ATR, Pivot + k*ATR]
    3. Grids: Dynamically calculated to ensure earnings > 2 * commission
    4. Risk: Stop trading/Cut loss if price breaks range
    5. Mode: 
       - GRID: Standard oscillation scalping
       - SAR: Momentum Trend Following (Stop & Reverse) when hard stop triggered
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
        
        # SAR / Adaptive State
        self.state_mode: str = "GRID"  # "GRID" or "SAR"
        self.max_risk_pct: Decimal = Decimal("0.25")  # Max allowed loss of grid capital (25%)
        self.absolute_stop_price: Optional[Decimal] = None
        self.sar_fast_ema_period: int = 9
        self.sar_slow_ema_period: int = 21

        # Indicators
        self.atr_period = 14
        self.bb_period = 20
        self.bb_std = Decimal("2.0")
        
        # Data History
        self.bar_history = []
        self.min_history = max(self.atr_period, self.bb_period, self.sar_slow_ema_period, 50) + 5

    def on_bar(self, bar):
        # 0. Update History
        self.bar_history.append(bar)
        if len(self.bar_history) > self.min_history + 100:
            self.bar_history.pop(0)
            
        if len(self.bar_history) < self.min_history:
            if len(self.bar_history) % 10 == 1:
                print(f"[Grid DEBUG] Collecting bars: {len(self.bar_history)}/{self.min_history}")
            return

        # 1. State Machine: SAR Mode Interception
        if self.state_mode == "SAR":
            self._run_sar_engine(bar.close)
            return

        # Prepare Grid Indicators
        closes = [b.close for b in self.bar_history]
        highs = [b.high for b in self.bar_history]
        lows = [b.low for b in self.bar_history]

        atr_values = calculate_atr(highs, lows, closes, period=self.atr_period)
        if not atr_values or atr_values[-1] is None: return
        atr = atr_values[-1]
        
        bb_values = calculate_bollinger_bands(closes, period=self.bb_period, std_dev=self.bb_std)
        if not bb_values or bb_values[-1].middle is None: return
        pivot = bb_values[-1].middle
        
        current_price = bar.close

        # Trend Filter Update
        self.trend_direction = None
        if self.trend_filter_enabled:
             ema_values = calculate_ema(closes, period=self.trend_ema_period)
             if ema_values and ema_values[-1] is not None:
                 if current_price > ema_values[-1]:
                     self.trend_direction = "UP"
                 else:
                     self.trend_direction = "DOWN"

        # 2. Active Grid: Check for Breakouts / Stop Loss
        if self.grid_lines:
            self.check_and_reset_grid(current_price)

        # 3. Initialize Grid if not exists (and we are in GRID mode)
        active_orders = self.broker.get_open_orders(self.symbol)
        position = self.broker.get_position(self.symbol)
        if hasattr(position, 'quantity') and position.quantity == 0:
             position = None
        
        if not self.grid_lines and not active_orders and self.state_mode == "GRID":
            print(f"[Grid DEBUG] Initializing grid: pivot={pivot:.2f}, atr={atr:.4f}, price={current_price:.4f}")
            self._calculate_and_place_grids(pivot, atr, current_price)

    def check_and_reset_grid(self, current_price: Decimal):
        """Check limits and trigger breakout logic."""
        if not self.grid_lines: return

        # Breakout Detection
        # We use a slight buffer to verify breakout isn't just noise, 
        # BUT for Hard Stop, we must be strict if it hits the calculated stop level.
        # Here we detect if we are OUTSIDE the grid range.
        
        hit_upper = current_price >= self.upper_limit
        hit_lower = current_price <= self.lower_limit
        
        if hit_upper:
             print(f"🔄 [Grid] Price ({current_price:.2f}) hit UPPER limit ({self.upper_limit:.2f}). Checking breakout...")
             self._handle_breakout("UP", current_price)
        elif hit_lower:
             print(f"🔄 [Grid] Price ({current_price:.2f}) hit LOWER limit ({self.lower_limit:.2f}). Checking breakout...")
             self._handle_breakout("DOWN", current_price)

    def cancel_and_reset_grid(self, current_price: Decimal):
        """Cancel all orders and restart grid at new price."""
        if self.state_mode != "GRID": return

        print(f"🔄 [Grid] Executing Dynamic Reset at {current_price:.2f}...")
        try:
            if self.broker:
                self.broker.cancel_all_orders(self.symbol)
        except Exception as e:
            print(f"⚠️ [Grid] Failed to cancel orders during reset: {e}")
            
        self.grid_lines = []
        self.upper_limit = None
        self.lower_limit = None
        self.absolute_stop_price = None
        
        # Logic to re-init on NEXT bar (handled by on_bar)

    def _calculate_and_place_grids(self, pivot: Decimal, atr: Decimal, current_price: Decimal):
        """Calculate grid levels and place initial orders"""
        range_width = atr * self.atr_multiplier
        
        # Center grid if price drifted
        if abs(current_price - pivot) > (range_width * Decimal("0.5")):
            pivot = current_price
            
        self.upper_limit = pivot + range_width
        self.lower_limit = pivot - range_width
        self.pivot_price = pivot
        
        # Reset Absolute Stop Price based on Entry (if we had a position)
        # But here we are initializing. The Stop Price is tracked relative to ENTRY of a position.
        # If we don't have a position yet, we don't have a Hard Stop.
        # We will calculate Hard Stop when we actually check breakout on an existing position.
        
        if self.upper_limit <= self.lower_limit: return

        # Calc Grids
        actual_grids = self.grid_number # Simplified for brevity, use full logic if needed
        # (Preserving original logic for count calculation would be good, but for brevity using fixed)
        # Restoring original dynamic count logic:
        import math
        min_profit_ratio = Decimal("1") + self.min_profit
        try:
            max_grids_geo = int(math.log(float(self.upper_limit / self.lower_limit)) / math.log(float(min_profit_ratio)))
            actual_grids = min(self.grid_number, max_grids_geo)
        except:
            actual_grids = self.grid_number
            
        if actual_grids < 3: return

        self.grid_lines = []
        # Geometric spacing
        ratio = (self.upper_limit / self.lower_limit) ** (Decimal("1") / Decimal(actual_grids))
        for i in range(actual_grids + 1):
             self.grid_lines.append(self.lower_limit * (ratio ** i))
             
        step_size = current_price * (ratio - Decimal("1"))

        # Position Sizing
        balance = self.broker.get_balance()
        if balance <= 0: balance = Decimal("5000")
        available_capital = balance * self.capital_usage * Decimal(str(self.leverage))
        qty_per_grid = available_capital / (Decimal(str(actual_grids)) * current_price)
        
        # Precision
        precision = Decimal("0.001") # Simplified
        qty_per_grid = (qty_per_grid / precision).to_integral_value(rounding='ROUND_DOWN') * precision
        if qty_per_grid == 0: return
        self.position_size = qty_per_grid
        
        print(f"[Grid] Initializing: Range=[{self.lower_limit:.2f}, {self.upper_limit:.2f}], Grids={actual_grids}, Qty={qty_per_grid}")

        self.grid_orders = {}
        for level in self.grid_lines:
            if abs(level - current_price) < (step_size * Decimal("0.2")): continue
            if level > current_price:
                self.create_limit_order(self.symbol, "sell", float(self.position_size), float(level))
            else:
                self.create_limit_order(self.symbol, "buy", float(self.position_size), float(level))

    def on_order_update(self, order: Order):
        """Handle filled orders to place counter-orders"""
        if self.state_mode != "GRID": return
        if not self.grid_lines: return

        last_filled = self.order_fill_tracking.get(order.id, Decimal("0"))
        current_filled = order.filled_quantity
        new_fill_qty = current_filled - last_filled
        
        if new_fill_qty > Decimal("0"):
            self.order_fill_tracking[order.id] = current_filled
            fill_price = Decimal(str(order.price)) if order.price else order.avg_fill_price
            if not fill_price: return

            closest_level = min(self.grid_lines, key=lambda x: abs(x - fill_price))
            
            if order.side == "buy":
                try:
                    idx = self.grid_lines.index(closest_level)
                    if idx + 1 < len(self.grid_lines):
                        target_level = self.grid_lines[idx + 1]
                        self.create_limit_order(self.symbol, "sell", float(new_fill_qty), float(target_level))
                except: pass
            elif order.side == "sell":
                try:
                    idx = self.grid_lines.index(closest_level)
                    if idx - 1 >= 0:
                        target_level = self.grid_lines[idx - 1]
                        self.create_limit_order(self.symbol, "buy", float(new_fill_qty), float(target_level))
                except: pass

        if order.status in ["filled", "cancelled", "rejected", "expired"]:
            if order.id in self.order_fill_tracking:
                del self.order_fill_tracking[order.id]

    def _handle_breakout(self, direction: str, current_price: Decimal):
        """
        Handle breakout with Adaptive Hard Stop & SAR Trigger.
        CRITICAL: Safety First - Cancel Orders -> Close Position -> Check SAR.
        """
        position = self.broker.get_position(self.symbol)
        if not position or position.quantity == 0:
            # Nothing to stop, just reset grid
            self.cancel_and_reset_grid(current_price)
            return

        entry_price = position.entry_price
        side_str = str(position.side).split('.')[-1]
        
        # 1. Calculate Hard Stop Price (Dynamic)
        # Allow 25% flexible drawdown per component... 
        # Formula: allowed_move = max_risk / leverage
        allowed_move = self.max_risk_pct / Decimal(str(self.leverage))
        
        stop_triggered = False
        
        if direction == "UP" and side_str == "SHORT":
            stop_price = entry_price * (Decimal("1") + allowed_move)
            # Use Hard Stop check
            if current_price >= stop_price:
                 print(f"🛑 [STOP] HARD STOP Triggered! Price {current_price} >= {stop_price} (Entry: {entry_price})")
                 stop_triggered = True
            elif current_price >= self.upper_limit * (Decimal("1") + self.stop_loss_buffer):
                 print(f"🛑 [STOP] Grid Range Broken! Price {current_price} >= Upper Limit Buffer")
                 stop_triggered = True
                 
        elif direction == "DOWN" and side_str == "LONG":
            stop_price = entry_price * (Decimal("1") - allowed_move)
            if current_price <= stop_price:
                 print(f"🛑 [STOP] HARD STOP Triggered! Price {current_price} <= {stop_price} (Entry: {entry_price})")
                 stop_triggered = True
            elif current_price <= self.lower_limit * (Decimal("1") - self.stop_loss_buffer):
                 print(f"🛑 [STOP] Grid Range Broken! Price {current_price} <= Lower Limit Buffer")
                 stop_triggered = True

        if stop_triggered:
            # Safety Check: Cancel Orders FIRST to free margin
            print("⚡ [SAFETY] 1. Cancelling All Orders...")
            self.broker.cancel_all_orders(self.symbol)
            
            # Execute Close
            print(f"⚡ [SAFETY] 2. Closing Position (Market {position.quantity})...")
            close_side = "buy" if side_str == "SHORT" else "sell"
            self.create_market_order(self.symbol, close_side, float(position.quantity))
            
            # 3. SAR Evaluation
            # Check Momentum (Fast vs Slow EMA)
            closes = [b.close for b in self.bar_history]
            if len(closes) < self.sar_slow_ema_period:
                print("⚠️ [SAR] Not enough data for EMA check. Grid Reset.")
                self.cancel_and_reset_grid(current_price)
                return
                
            fast_ema_vals = calculate_ema(closes, self.sar_fast_ema_period)
            slow_ema_vals = calculate_ema(closes, self.sar_slow_ema_period)
            
            fast_ema = fast_ema_vals[-1]
            slow_ema = slow_ema_vals[-1]
            
            if fast_ema is None or slow_ema is None: return
            
            # Trigger Logic
            triggered_sar = False
            sar_side = None
            
            if direction == "UP" and fast_ema > slow_ema:
                print(f"📈 [SAR ACTIVATED] Bullish Breakout Confirmed (Fast {fast_ema:.2f} > Slow {slow_ema:.2f})")
                triggered_sar = True
                sar_side = "buy"
            elif direction == "DOWN" and fast_ema < slow_ema:
                print(f"📉 [SAR ACTIVATED] Bearish Breakout Confirmed (Fast {fast_ema:.2f} < Slow {slow_ema:.2f})")
                triggered_sar = True
                sar_side = "sell"
                
            if triggered_sar:
                # Calculate Sizing
                sar_qty = self._calculate_sar_position_size(current_price)
                if sar_qty > 0:
                    print(f"🚀 [SAR] Opening Momentum Position: {sar_side.upper()} {sar_qty}")
                    self.create_market_order(self.symbol, sar_side, float(sar_qty))
                    self.state_mode = "SAR"
                    self.grid_lines = [] # Clear grid lines
                else:
                    print(f"⚠️ [SAR] Volume/Sizing too low. No trade.")
                    self.state_mode = "GRID"
                    self.cancel_and_reset_grid(current_price)
            else:
                print("⚠️ [SAR] Momentum not confirmed. Resetting Grid.")
                self.state_mode = "GRID"
                self.cancel_and_reset_grid(current_price)
        else:
            # Just reset logic if it's a minor breach OR neutral position
            self.cancel_and_reset_grid(current_price)

    def _calculate_sar_position_size(self, current_price: Decimal) -> Decimal:
        """
        Calculate SAR position size using Volume Ratio Clamp.
        Ratio = Current Vol / SMA(20) Vol
        Map 1.0 -> 10%, 5.0 -> 30%
        """
        # Get volumes
        volumes = [Decimal(str(b.volume)) for b in self.bar_history]
        if not volumes: return Decimal("0")
        
        current_vol = volumes[-1]
        
        # Calculate SMA 20 Volume
        vol_sma_period = 20
        if len(volumes) < vol_sma_period:
            avg_vol = sum(volumes) / Decimal(len(volumes))
        else:
            avg_vol = sum(volumes[-vol_sma_period:]) / Decimal(vol_sma_period)
            
        if avg_vol == 0: avg_vol = Decimal("1") # Avoid div zero
        
        volume_ratio = current_vol / avg_vol
        print(f"📊 [SAR SIZE] Volume Ratio: {volume_ratio:.2f} (Curr: {current_vol:.0f}, Avg: {avg_vol:.0f})")
        
        # User defined Clamp Function
        # min_allocation = 10%
        # max_allocation = 30%
        # Map [1.0, 5.0] -> [0.0, 1.0]
        
        min_alloc = Decimal("0.10")
        max_alloc = Decimal("0.30")
        
        base_ratio = float(volume_ratio)
        normalized = (base_ratio - 1.0) / (5.0 - 1.0)
        normalized = max(0.0, min(1.0, normalized))
        
        final_alloc = min_alloc + Decimal(str(normalized)) * (max_alloc - min_alloc)
        
        balance = self.broker.get_balance()
        # Leverage? User said "20x leverage... asset allows 1.25%". 
        # Here we use configured leverage.
        
        # SAR is a directional trade. User said "Allocating 10-30% of Available Funds". 
        # Usually implies Size = (Balance * Alloc * Leverage) / Price
        
        sar_value = balance * final_alloc * Decimal(str(self.leverage))
        sar_qty = sar_value / current_price
        
        # Rounding (Safety)
        precision = Decimal("0.001")
        sar_qty = (sar_qty / precision).to_integral_value(rounding='ROUND_DOWN') * precision
        
        print(f"💰 [SAR SIZE] Allocation: {final_alloc*100:.1f}% -> Qty {sar_qty}")
        return sar_qty

    def _run_sar_engine(self, current_price: Decimal):
        """
        SAR Mode: Trend Following.
        Exit when Fast EMA crosses Slow EMA against position.
        Also check for Hard Stop.
        """
        closes = [b.close for b in self.bar_history]
        if len(closes) < self.sar_slow_ema_period: return

        # Indicators
        fast = calculate_ema(closes, self.sar_fast_ema_period)[-1]
        slow = calculate_ema(closes, self.sar_slow_ema_period)[-1]
        
        position = self.broker.get_position(self.symbol)
        if not position or position.quantity == 0:
             # Position closed externally?
             print("⚠️ [SAR] Position lost. Resetting to Grid.")
             self.state_mode = "GRID"
             self.cancel_and_reset_grid(current_price)
             return
             
        side_str = str(position.side).split('.')[-1]
        entry_price = position.entry_price

        # 1. HARD STOP (Safety Net)
        allowed_loss = self.max_risk_pct / Decimal(str(self.leverage))
        is_hard_stop = False
        
        if side_str == "LONG":
            stop_price = entry_price * (Decimal("1") - allowed_loss)
            if current_price <= stop_price:
                 print(f"🛑 [SAR STOP] Hard Stop Hit! Price {current_price:.4f} <= {stop_price:.4f} (Entry: {entry_price})")
                 is_hard_stop = True
        elif side_str == "SHORT":
            stop_price = entry_price * (Decimal("1") + allowed_loss)
            if current_price >= stop_price:
                 print(f"🛑 [SAR STOP] Hard Stop Hit! Price {current_price:.4f} >= {stop_price:.4f} (Entry: {entry_price})")
                 is_hard_stop = True
                 
        if is_hard_stop:
             # Force Close
             close_side = "buy" if side_str == "SHORT" else "sell"
             print(f"⚡ [SAR STOP] Closing {side_str} position...")
             self.create_market_order(self.symbol, close_side, float(position.quantity))
             self.state_mode = "GRID"
             self.cancel_and_reset_grid(current_price)
             return
        
        # 2. TREND REVERSAL (EMA Cross)
        exit_sar = False
        if side_str == "LONG":
            if fast < slow:
                print(f"📉 [SAR EXIT] Trend Reversal (Fast {fast:.2f} < Slow {slow:.2f}). Closing LONG.")
                exit_sar = True
        elif side_str == "SHORT":
            if fast > slow:
                print(f"📈 [SAR EXIT] Trend Reversal (Fast {fast:.2f} > Slow {slow:.2f}). Closing SHORT.")
                exit_sar = True
                
        if exit_sar:
            self.create_market_order(self.symbol, "sell" if side_str == "LONG" else "buy", float(position.quantity))
            self.state_mode = "GRID"
            self.cancel_and_reset_grid(current_price)
