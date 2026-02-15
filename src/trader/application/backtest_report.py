"""Backtest report generation with comprehensive performance metrics.

Calculates and formats key trading performance metrics including
Sharpe ratio, maximum drawdown, win rate, and more.
"""
from decimal import Decimal
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from pydantic import BaseModel, Field
import math


class TradeRecord(BaseModel):
    """Record of a single trade."""
    entry_timestamp: datetime
    exit_timestamp: datetime
    side: str  # "long" or "short"
    entry_price: Decimal
    exit_price: Decimal
    quantity: Decimal
    pnl: Decimal
    pnl_percent: Decimal
    commission: Decimal


class BacktestReport(BaseModel):
    """Comprehensive backtest performance report."""
    initial_balance: Decimal = Field(description="Initial account balance")
    final_balance: Decimal = Field(description="Final account balance")
    total_return: Decimal = Field(description="Total return percentage")
    annualized_return: Decimal = Field(description="Annualized return percentage")
    
    total_trades: int = Field(description="Total number of trades")
    winning_trades: int = Field(description="Number of winning trades")
    losing_trades: int = Field(description="Number of losing trades")
    win_rate: Decimal = Field(description="Win rate percentage")
    
    avg_win: Decimal = Field(description="Average winning trade P&L")
    avg_loss: Decimal = Field(description="Average losing trade P&L")
    profit_factor: Decimal = Field(description="Profit factor (gross profits / gross losses)")
    risk_reward_ratio: Decimal = Field(description="Average win / average loss")
    
    max_drawdown: Decimal = Field(description="Maximum drawdown percentage")
    max_drawdown_duration: timedelta = Field(description="Maximum drawdown duration")
    
    sharpe_ratio: Decimal = Field(description="Sharpe ratio (risk-adjusted return)")
    sortino_ratio: Decimal = Field(description="Sortino ratio (downside risk-adjusted)")
    calmar_ratio: Decimal = Field(description="Calmar ratio (return / max drawdown)")
    
    total_commission: Decimal = Field(description="Total commission paid")
    total_slippage: Decimal = Field(description="Total slippage incurred")
    total_funding_paid: Decimal = Field(description="Total funding fees paid")
    
    start_date: datetime = Field(description="Backtest start date")
    end_date: datetime = Field(description="Backtest end date")
    duration: timedelta = Field(description="Backtest duration")
    
    trades: List[TradeRecord] = Field(default_factory=list, description="Individual trade records")
    equity_curve: List[Dict] = Field(default_factory=list, description="Equity curve data points")


class BacktestReportGenerator:
    """Generate comprehensive backtest performance reports."""
    
    def __init__(
        self,
        risk_free_rate: Decimal = Decimal("0.02"),  # 2% annual risk-free rate
        annual_trading_days: int = 365,  # For crypto, 24/7 trading
    ):
        """Initialize report generator.

        Args:
            risk_free_rate: Annual risk-free rate for Sharpe ratio calculation
            annual_trading_days: Number of trading days per year
        """
        self.risk_free_rate = risk_free_rate
        self.annual_trading_days = annual_trading_days

    def generate_report(
        self,
        initial_balance: Decimal,
        final_balance: Decimal,
        equity_curve: List[Dict],
        trades: Optional[List[TradeRecord]] = None,
        total_commission: Decimal = Decimal("0"),
        total_slippage: Decimal = Decimal("0"),
        total_funding_paid: Decimal = Decimal("0"),
    ) -> BacktestReport:
        """Generate a comprehensive backtest report.

        Args:
            initial_balance: Starting account balance
            final_balance: Ending account balance
            equity_curve: List of equity data points with timestamp and balance
            trades: Optional list of individual trade records
            total_commission: Total commission paid
            total_slippage: Total slippage incurred
            total_funding_paid: Total funding fees paid

        Returns:
            BacktestReport with all performance metrics
        """
        trades = trades or []
        
        # Calculate basic returns
        total_return = (final_balance - initial_balance) / initial_balance * Decimal("100")
        
        # Get date range
        start_date = equity_curve[0]["timestamp"] if equity_curve else datetime.now()
        end_date = equity_curve[-1]["timestamp"] if equity_curve else datetime.now()
        duration = end_date - start_date
        
        # Annualized return
        years = Decimal(str(duration.days)) / Decimal(str(self.annual_trading_days))
        annualized_return = ((final_balance / initial_balance) ** (Decimal("1") / years) - Decimal("1")) * Decimal("100") if years > Decimal("0") else Decimal("0")
        
        # Trade statistics
        winning_trades = [t for t in trades if t.pnl > Decimal("0")]
        losing_trades = [t for t in trades if t.pnl <= Decimal("0")]
        win_rate = Decimal(str(len(winning_trades) / len(trades) * 100)) if trades else Decimal("0")
        
        avg_win = sum(t.pnl for t in winning_trades) / Decimal(str(len(winning_trades))) if winning_trades else Decimal("0")
        avg_loss = abs(sum(t.pnl for t in losing_trades) / Decimal(str(len(losing_trades)))) if losing_trades else Decimal("0")
        
        profit_factor = self._calculate_profit_factor(winning_trades, losing_trades)
        risk_reward_ratio = avg_win / avg_loss if avg_loss > Decimal("0") else Decimal("0")
        
        # Drawdown analysis
        max_drawdown, max_dd_duration = self._calculate_max_drawdown(equity_curve)
        
        # Risk-adjusted returns
        sharpe_ratio = self._calculate_sharpe_ratio(equity_curve)
        sortino_ratio = self._calculate_sortino_ratio(equity_curve)
        calmar_ratio = annualized_return / max_drawdown if max_drawdown > Decimal("0") else Decimal("0")
        
        return BacktestReport(
            initial_balance=initial_balance,
            final_balance=final_balance,
            total_return=total_return,
            annualized_return=annualized_return,
            total_trades=len(trades),
            winning_trades=len(winning_trades),
            losing_trades=len(losing_trades),
            win_rate=win_rate,
            avg_win=avg_win,
            avg_loss=avg_loss,
            profit_factor=profit_factor,
            risk_reward_ratio=risk_reward_ratio,
            max_drawdown=max_drawdown,
            max_drawdown_duration=max_dd_duration,
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            calmar_ratio=calmar_ratio,
            total_commission=total_commission,
            total_slippage=total_slippage,
            total_funding_paid=total_funding_paid,
            start_date=start_date,
            end_date=end_date,
            duration=duration,
            trades=trades,
            equity_curve=equity_curve,
        )

    def _calculate_profit_factor(
        self,
        winning_trades: List[TradeRecord],
        losing_trades: List[TradeRecord],
    ) -> Decimal:
        """Calculate profit factor (gross profits / gross losses)."""
        gross_profits = sum(t.pnl for t in winning_trades)
        gross_losses = abs(sum(t.pnl for t in losing_trades))
        
        return gross_profits / gross_losses if gross_losses > Decimal("0") else Decimal("0")

    def _calculate_max_drawdown(
        self,
        equity_curve: List[Dict],
    ) -> tuple[Decimal, timedelta]:
        """Calculate maximum drawdown and its duration.

        Returns:
            Tuple of (max_drawdown_percentage, max_drawdown_duration)
        """
        if not equity_curve:
            return Decimal("0"), timedelta(0)
        
        peak_balance = Decimal(str(equity_curve[0]["balance"]))
        peak_timestamp = equity_curve[0]["timestamp"]
        max_drawdown = Decimal("0")
        max_dd_start = peak_timestamp
        max_dd_end = peak_timestamp
        
        for point in equity_curve:
            balance = Decimal(str(point["balance"]))
            timestamp = point["timestamp"]
            
            if balance > peak_balance:
                peak_balance = balance
                peak_timestamp = timestamp
            
            drawdown = (peak_balance - balance) / peak_balance * Decimal("100")
            
            if drawdown > max_drawdown:
                max_drawdown = drawdown
                max_dd_start = peak_timestamp
                max_dd_end = timestamp
        
        max_dd_duration = max_dd_end - max_dd_start
        return max_drawdown, max_dd_duration

    def _calculate_sharpe_ratio(self, equity_curve: List[Dict]) -> Decimal:
        """Calculate Sharpe ratio (risk-adjusted return)."""
        if len(equity_curve) < 2:
            return Decimal("0")
        
        # Calculate daily returns
        returns = []
        for i in range(1, len(equity_curve)):
            prev_balance = Decimal(str(equity_curve[i-1]["balance"]))
            curr_balance = Decimal(str(equity_curve[i]["balance"]))
            daily_return = (curr_balance - prev_balance) / prev_balance
            returns.append(float(daily_return))
        
        if not returns:
            return Decimal("0")
        
        # Calculate Sharpe ratio
        avg_return = sum(returns) / len(returns)
        std_dev = math.sqrt(sum((r - avg_return) ** 2 for r in returns) / len(returns))
        
        # Annualize
        annual_factor = math.sqrt(self.annual_trading_days)
        excess_return = avg_return - (float(self.risk_free_rate) / self.annual_trading_days)
        
        sharpe = (excess_return / std_dev * annual_factor) if std_dev > 0 else 0
        
        return Decimal(str(sharpe))

    def _calculate_sortino_ratio(self, equity_curve: List[Dict]) -> Decimal:
        """Calculate Sortino ratio (downside risk-adjusted return)."""
        if len(equity_curve) < 2:
            return Decimal("0")
        
        # Calculate daily returns
        returns = []
        downside_returns = []
        for i in range(1, len(equity_curve)):
            prev_balance = Decimal(str(equity_curve[i-1]["balance"]))
            curr_balance = Decimal(str(equity_curve[i]["balance"]))
            daily_return = (curr_balance - prev_balance) / prev_balance
            returns.append(float(daily_return))
            
            # Only consider negative returns for downside
            if daily_return < Decimal("0"):
                downside_returns.append(float(daily_return))
        
        if not returns:
            return Decimal("0")
        
        avg_return = sum(returns) / len(returns)
        
        # Calculate downside deviation
        if not downside_returns:
            downside_std = 0
        else:
            downside_std = math.sqrt(sum(r ** 2 for r in downside_returns) / len(returns))
        
        # Annualize
        annual_factor = math.sqrt(self.annual_trading_days)
        excess_return = avg_return - (float(self.risk_free_rate) / self.annual_trading_days)
        
        sortino = (excess_return / downside_std * annual_factor) if downside_std > 0 else 0
        
        return Decimal(str(sortino))

    def format_report(self, report: BacktestReport) -> str:
        """Format report as a human-readable string.

        Args:
            report: BacktestReport to format

        Returns:
            Formatted string report
        """
        lines = [
            "=" * 80,
            "BACKTEST PERFORMANCE REPORT",
            "=" * 80,
            "",
            f"Period: {report.start_date.strftime('%Y-%m-%d')} to {report.end_date.strftime('%Y-%m-%d')}",
            f"Duration: {report.duration.days} days",
            "",
            "-" * 80,
            "RETURN METRICS",
            "-" * 80,
            f"Initial Balance: ${report.initial_balance:,.2f}",
            f"Final Balance:   ${report.final_balance:,.2f}",
            f"Total Return:    {report.total_return:+.2f}%",
            f"Annualized:      {report.annualized_return:+.2f}%",
            "",
            "-" * 80,
            "TRADE STATISTICS",
            "-" * 80,
            f"Total Trades:    {report.total_trades}",
            f"Winning Trades:  {report.winning_trades}",
            f"Losing Trades:   {report.losing_trades}",
            f"Win Rate:        {report.win_rate:.2f}%",
            f"Average Win:     ${report.avg_win:,.2f}",
            f"Average Loss:    ${report.avg_loss:,.2f}",
            f"Profit Factor:   {report.profit_factor:.2f}",
            f"Risk/Reward:     {report.risk_reward_ratio:.2f}",
            "",
            "-" * 80,
            "RISK METRICS",
            "-" * 80,
            f"Max Drawdown:    {report.max_drawdown:.2f}%",
            f"DD Duration:     {report.max_drawdown_duration.days} days",
            f"Sharpe Ratio:    {report.sharpe_ratio:.2f}",
            f"Sortino Ratio:   {report.sortino_ratio:.2f}",
            f"Calmar Ratio:    {report.calmar_ratio:.2f}",
            "",
            "-" * 80,
            "COSTS",
            "-" * 80,
            f"Total Commission: ${report.total_commission:,.2f}",
            f"Total Slippage:   ${report.total_slippage:,.2f}",
            f"Total Funding:    ${report.total_funding_paid:,.2f}",
            "=" * 80,
        ]
        
        return "\n".join(lines)
