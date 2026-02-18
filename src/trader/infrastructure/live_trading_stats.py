"""
Live Trading Statistics Collector
==================================

Tracks fills, computes performance metrics, and saves results to JSON.
Subscribes to ORDER_FILLED events and computes:
- Win rate, total trades, buy/sell counts
- Total commission / fees spent
- Realized P&L, unrealized P&L
- Sharpe ratio (from equity snapshots)
- Max drawdown
- Average holding time
"""

import json
import time
import math
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional


class DecimalEncoder(json.JSONEncoder):
    """JSON encoder that handles Decimal types."""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


class LiveTradingStats:
    """Collects and computes live trading performance statistics.
    
    Tracks:
    - Individual fills (buys and sells)
    - Round-trip trades (buy→sell pairs for realized P&L)
    - Equity curve snapshots (for Sharpe, drawdown)
    - Commission accumulation
    """

    def __init__(self, initial_balance: Decimal, symbol: str, leverage: int = 1):
        self.initial_balance = initial_balance
        self.symbol = symbol
        self.leverage = leverage
        self.start_time = datetime.now(timezone.utc)
        
        # Fill tracking
        self.fills: List[dict] = []  # All individual fills
        self.total_buy_qty = Decimal("0")
        self.total_sell_qty = Decimal("0")
        self.total_buy_value = Decimal("0")  # sum(qty * price) for buys
        self.total_sell_value = Decimal("0")  # sum(qty * price) for sells
        self.total_commission = Decimal("0")
        self.buy_count = 0
        self.sell_count = 0
        
        # Round-trip tracking (FIFO matching)
        self.open_legs: List[dict] = []  # Unmatched fills
        self.round_trips: List[dict] = []  # Completed buy→sell / sell→buy pairs
        
        # Equity curve (for Sharpe & drawdown)
        self.equity_snapshots: List[dict] = []
        self.peak_equity = initial_balance
        self.max_drawdown = Decimal("0")
        self.max_drawdown_pct = Decimal("0")
        
        # Guard against zero initial balance (e.g. from connection issues)
        if self.initial_balance <= 0:
            self.initial_balance = Decimal("1") # Avoid division by zero, will be updated later if possible
        
        # Grid-specific
        self.grid_resets = 0

    def on_fill(self, event_data: dict) -> None:
        """Record a fill from ORDER_FILLED event.
        
        Args:
            event_data: Event data dict with side, price, quantity, commission
        """
        side = event_data.get("side", "unknown")
        price = Decimal(str(event_data.get("price", "0")))
        quantity = Decimal(str(event_data.get("quantity", "0")))
        commission = Decimal(str(event_data.get("commission", "0")))
        symbol = event_data.get("symbol", self.symbol)
        
        fill = {
            "time": datetime.now(timezone.utc).isoformat(),
            "side": side,
            "price": price,
            "quantity": quantity,
            "value": price * quantity,
            "commission": commission,
            "exchange_id": event_data.get("exchange_id", ""),
        }
        self.fills.append(fill)
        
        # Accumulate totals
        self.total_commission += commission
        if side == "buy":
            self.buy_count += 1
            self.total_buy_qty += quantity
            self.total_buy_value += price * quantity
        elif side == "sell":
            self.sell_count += 1
            self.total_sell_qty += quantity
            self.total_sell_value += price * quantity
        
        # Try to match round-trips (FIFO)
        self._try_match_round_trip(fill)

    def _try_match_round_trip(self, new_fill: dict) -> None:
        """Try to match new fill with existing open legs for round-trip P&L."""
        opposite_side = "sell" if new_fill["side"] == "buy" else "buy"
        
        remaining_qty = new_fill["quantity"]
        i = 0
        while i < len(self.open_legs) and remaining_qty > Decimal("0"):
            leg = self.open_legs[i]
            if leg["side"] == opposite_side:
                match_qty = min(remaining_qty, leg["quantity"])
                
                # Calculate P&L for this round-trip
                if leg["side"] == "buy":
                    # Buy first, sell to close
                    pnl = (new_fill["price"] - leg["price"]) * match_qty
                else:
                    # Sell first (short), buy to close
                    pnl = (leg["price"] - new_fill["price"]) * match_qty
                
                self.round_trips.append({
                    "entry_side": leg["side"],
                    "entry_price": leg["price"],
                    "exit_price": new_fill["price"],
                    "quantity": match_qty,
                    "pnl": pnl,
                    "entry_time": leg["time"],
                    "exit_time": new_fill["time"],
                })
                
                # Reduce quantities
                remaining_qty -= match_qty
                leg["quantity"] -= match_qty
                
                if leg["quantity"] <= Decimal("0"):
                    self.open_legs.pop(i)
                else:
                    i += 1
            else:
                i += 1
        
        # If there's remaining unmatched quantity, add as new open leg
        if remaining_qty > Decimal("0"):
            self.open_legs.append({
                "side": new_fill["side"],
                "price": new_fill["price"],
                "quantity": remaining_qty,
                "time": new_fill["time"],
            })
    
    def record_equity(self, equity: Decimal) -> None:
        """Record an equity snapshot for Sharpe/drawdown calculations.
        
        Call this periodically (e.g., every N iterations).
        """
        self.equity_snapshots.append({
            "time": datetime.now(timezone.utc).isoformat(),
            "equity": equity,
        })
        
        # Track drawdown
        if equity > self.peak_equity:
            self.peak_equity = equity
        
        drawdown = self.peak_equity - equity
        drawdown_pct = drawdown / self.peak_equity if self.peak_equity > 0 else Decimal("0")
        
        if drawdown > self.max_drawdown:
            self.max_drawdown = drawdown
        if drawdown_pct > self.max_drawdown_pct:
            self.max_drawdown_pct = drawdown_pct

    def compute_results(self, final_balance: Decimal, final_equity: Decimal) -> dict:
        """Compute all performance statistics.
        
        Args:
            final_balance: Current wallet balance
            final_equity: Balance + unrealized P&L
            
        Returns:
            Dictionary of all computed statistics
        """
        end_time = datetime.now(timezone.utc)
        duration_seconds = (end_time - self.start_time).total_seconds()
        duration_hours = duration_seconds / 3600
        
        # --- Basic Stats ---
        total_fills = len(self.fills)
        total_round_trips = len(self.round_trips)
        
        # --- P&L ---
        realized_pnl = sum(rt["pnl"] for rt in self.round_trips)
        unrealized_pnl = final_equity - final_balance
        total_pnl = final_equity - self.initial_balance
        total_return_pct = (total_pnl / self.initial_balance * 100) if self.initial_balance > 0 else Decimal("0")
        
        # --- Win Rate ---
        winning_trades = [rt for rt in self.round_trips if rt["pnl"] > 0]
        losing_trades = [rt for rt in self.round_trips if rt["pnl"] <= 0]
        win_rate = (len(winning_trades) / total_round_trips * 100) if total_round_trips > 0 else 0
        
        avg_win = sum(rt["pnl"] for rt in winning_trades) / len(winning_trades) if winning_trades else Decimal("0")
        avg_loss = sum(rt["pnl"] for rt in losing_trades) / len(losing_trades) if losing_trades else Decimal("0")
        
        # Profit factor
        gross_profit = sum(rt["pnl"] for rt in winning_trades)
        gross_loss = abs(sum(rt["pnl"] for rt in losing_trades))
        profit_factor = float(gross_profit / gross_loss) if gross_loss > 0 else float("inf") if gross_profit > 0 else 0.0
        
        # --- Sharpe Ratio ---
        sharpe_ratio = self._compute_sharpe()
        
        # --- Commission Analysis ---
        total_volume = self.total_buy_value + self.total_sell_value
        effective_commission_rate = (self.total_commission / total_volume * 100) if total_volume > 0 else Decimal("0")
        commission_as_pct_of_pnl = (self.total_commission / abs(realized_pnl) * 100) if realized_pnl != 0 else Decimal("0")
        
        # --- Build Result ---
        result = {
            "session": {
                "symbol": self.symbol,
                "leverage": self.leverage,
                "start_time": self.start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "duration_hours": round(duration_hours, 2),
                "initial_balance": self.initial_balance,
                "final_balance": final_balance,
                "final_equity": final_equity,
            },
            "returns": {
                "total_pnl": total_pnl,
                "total_return_pct": round(float(total_return_pct), 4),
                "realized_pnl": realized_pnl,
                "unrealized_pnl": unrealized_pnl,
                "annualized_return_pct": round(float(total_return_pct) * (8760 / max(duration_hours, 0.01)), 2),
            },
            "trades": {
                "total_fills": total_fills,
                "buy_fills": self.buy_count,
                "sell_fills": self.sell_count,
                "total_round_trips": total_round_trips,
                "winning_trades": len(winning_trades),
                "losing_trades": len(losing_trades),
                "win_rate_pct": round(win_rate, 2),
                "avg_win": avg_win,
                "avg_loss": avg_loss,
                "profit_factor": round(profit_factor, 4),
                "largest_win": max((rt["pnl"] for rt in self.round_trips), default=Decimal("0")),
                "largest_loss": min((rt["pnl"] for rt in self.round_trips), default=Decimal("0")),
            },
            "risk": {
                "sharpe_ratio": sharpe_ratio,
                "max_drawdown_usd": self.max_drawdown,
                "max_drawdown_pct": round(float(self.max_drawdown_pct * 100), 2),
                "peak_equity": self.peak_equity,
            },
            "costs": {
                "total_commission": self.total_commission,
                "total_volume": total_volume,
                "effective_rate_pct": round(float(effective_commission_rate), 4),
                "commission_vs_pnl_pct": round(float(commission_as_pct_of_pnl), 2),
            },
            "grid_specific": {
                "grid_resets": self.grid_resets,
                "open_legs": len(self.open_legs),
                "total_buy_qty": self.total_buy_qty,
                "total_sell_qty": self.total_sell_qty,
                "net_position_qty": self.total_buy_qty - self.total_sell_qty,
            },
        }
        
        return result

    def _compute_sharpe(self, risk_free_rate: float = 0.0) -> float:
        """Compute annualized Sharpe ratio from equity snapshots.
        
        Uses periodic returns (snapshot-to-snapshot) to calculate.
        """
        if len(self.equity_snapshots) < 3:
            return 0.0
        
        equities = [float(s["equity"]) for s in self.equity_snapshots]
        returns = []
        for i in range(1, len(equities)):
            if equities[i - 1] > 0:
                r = (equities[i] - equities[i - 1]) / equities[i - 1]
                returns.append(r)
        
        if len(returns) < 2:
            return 0.0
        
        mean_return = sum(returns) / len(returns)
        variance = sum((r - mean_return) ** 2 for r in returns) / (len(returns) - 1)
        std_return = math.sqrt(variance) if variance > 0 else 0.0001
        
        # Annualize: assume each snapshot is ~2s apart (trading loop interval)
        # 365 * 24 * 3600 / 2 = ~15,768,000 periods per year
        # But we'll use a more conservative estimate based on actual duration
        total_seconds = (datetime.now(timezone.utc) - self.start_time).total_seconds()
        if total_seconds > 0 and len(returns) > 0:
            periods_per_year = len(returns) / total_seconds * 365 * 24 * 3600
        else:
            periods_per_year = 15768000
        
        annualized_return = mean_return * periods_per_year
        annualized_std = std_return * math.sqrt(periods_per_year)
        
        sharpe = (annualized_return - risk_free_rate) / annualized_std if annualized_std > 0 else 0.0
        return round(sharpe, 4)

    def save_to_file(self, final_balance: Decimal, final_equity: Decimal, filepath: str = "data/results.json") -> str:
        """Compute results and save to JSON file.
        
        Args:
            final_balance: Current wallet balance
            final_equity: Balance + unrealized P&L
            filepath: Output file path
            
        Returns:
            Absolute path of saved file
        """
        results = self.compute_results(final_balance, final_equity)
        
        # Ensure directory exists
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        # Load existing results if file exists (append to history)
        history = []
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    existing = json.load(f)
                if isinstance(existing, list):
                    history = existing
                elif isinstance(existing, dict):
                    history = [existing]
            except (json.JSONDecodeError, KeyError):
                pass
        
        history.append(results)
        
        with open(path, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2, cls=DecimalEncoder, ensure_ascii=False)
        
        return str(path.resolve())

    def print_summary(self, final_balance: Decimal, final_equity: Decimal) -> None:
        """Print a formatted summary to console."""
        r = self.compute_results(final_balance, final_equity)
        
        print("\n" + "=" * 62)
        print("  📊 LIVE TRADING PERFORMANCE REPORT")
        print("=" * 62)
        
        # Returns
        print(f"\n  --- Returns ---")
        print(f"  Total P&L:         ${float(r['returns']['total_pnl']):+,.2f}")
        print(f"  Total Return:      {r['returns']['total_return_pct']:+.2f}%")
        print(f"  Realized P&L:      ${float(r['returns']['realized_pnl']):+,.2f}")
        print(f"  Unrealized P&L:    ${float(r['returns']['unrealized_pnl']):+,.2f}")
        
        # Trades
        print(f"\n  --- Trades ---")
        print(f"  Total Fills:       {r['trades']['total_fills']} ({r['trades']['buy_fills']} buys, {r['trades']['sell_fills']} sells)")
        print(f"  Round Trips:       {r['trades']['total_round_trips']}")
        print(f"  Win Rate:          {r['trades']['win_rate_pct']:.1f}%")
        print(f"  Avg Win:           ${float(r['trades']['avg_win']):+,.4f}")
        print(f"  Avg Loss:          ${float(r['trades']['avg_loss']):+,.4f}")
        print(f"  Profit Factor:     {r['trades']['profit_factor']:.2f}")
        
        # Risk
        print(f"\n  --- Risk ---")
        print(f"  Sharpe Ratio:      {r['risk']['sharpe_ratio']:.4f}")
        print(f"  Max Drawdown:      ${float(r['risk']['max_drawdown_usd']):,.2f} ({r['risk']['max_drawdown_pct']:.2f}%)")
        
        # Costs
        print(f"\n  --- Costs ---")
        print(f"  Total Commission:  ${float(r['costs']['total_commission']):,.4f}")
        print(f"  Total Volume:      ${float(r['costs']['total_volume']):,.2f}")
        print(f"  Effective Rate:    {r['costs']['effective_rate_pct']:.4f}%")
        
        # Grid
        print(f"\n  --- Grid ---")
        print(f"  Grid Resets:       {r['grid_specific']['grid_resets']}")
        print(f"  Open Legs:         {r['grid_specific']['open_legs']}")
        print(f"  Net Position Qty:  {float(r['grid_specific']['net_position_qty']):+,.2f}")
        
        print(f"\n  Duration:          {r['session']['duration_hours']:.2f} hours")
        print("=" * 62)
