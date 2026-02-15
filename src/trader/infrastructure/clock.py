"""Clock abstraction for the trading system.

Provides time abstraction that supports both realtime and backtesting modes.
"""
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from typing import Optional


class IClock(ABC):
    """Clock abstraction interface."""
    
    @abstractmethod
    def now(self) -> datetime:
        """返回当前时间"""
        pass
    
    @abstractmethod
    def set_time(self, timestamp: datetime) -> None:
        """设置时间（回测模式使用）"""
        pass
    
    @abstractmethod
    def advance(self, seconds: int = 1) -> None:
        """推进时间（回测模式使用）"""
        pass


class RealtimeClock(IClock):
    """Realtime clock - used for live trading."""
    
    def now(self) -> datetime:
        """Get current UTC time."""
        return datetime.now(timezone.utc)
    
    def set_time(self, timestamp: datetime) -> None:
        """Cannot set time in realtime mode."""
        raise NotImplementedError("Cannot set time in realtime mode")
    
    def advance(self, seconds: int = 1) -> None:
        """Cannot advance time in realtime mode."""
        raise NotImplementedError("Cannot advance time in realtime mode")


# Alias for consistency with paper trading
SystemClock = RealtimeClock


class BacktestClock(IClock):
    """Backtest clock - controllable time progression for backtesting."""
    
    def __init__(self, initial_time: Optional[datetime] = None):
        """Initialize backtest clock with optional initial time.
        
        Args:
            initial_time: Initial timestamp, defaults to Jan 1, 2024 UTC
        """
        self._current_time = initial_time or datetime(2024, 1, 1, tzinfo=timezone.utc)
    
    @property
    def current_time(self) -> datetime:
        """Get current time."""
        return self._current_time
    
    def now(self) -> datetime:
        """Get current time."""
        return self._current_time
    
    def set_time(self, timestamp: datetime) -> None:
        """Set current time.
        
        Args:
            timestamp: New timestamp to set
        """
        self._current_time = timestamp
    
    def advance(self, seconds: int = 1) -> None:
        """Advance time by specified seconds.
        
        Args:
            seconds: Number of seconds to advance
        """
        self._current_time += timedelta(seconds=seconds)
