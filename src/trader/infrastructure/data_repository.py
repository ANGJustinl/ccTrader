"""Data access layer for market data storage.

Provides abstraction for storing and retrieving market data with thread safety.
"""
import threading
from abc import ABC, abstractmethod
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict


class BarData(BaseModel):
    """K线数据"""
    model_config = ConfigDict(frozen=True)
    
    symbol: str
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


class FundingRateData(BaseModel):
    """资金费率数据"""
    model_config = ConfigDict(frozen=True)
    
    symbol: str
    rate: Decimal
    timestamp: datetime
    next_funding_time: datetime


class DataRepository(ABC):
    """数据存储接口"""
    
    @abstractmethod
    def save_bar(self, bar: BarData) -> None:
        """保存K线数据
        
        Args:
            bar: Bar data to save
        """
        pass
    
    @abstractmethod
    def get_bars(
        self, 
        symbol: str, 
        start_time: datetime, 
        end_time: datetime
    ) -> List[BarData]:
        """获取K线数据
        
        Args:
            symbol: Trading pair symbol
            start_time: Start of time range
            end_time: End of time range
        
        Returns:
            List of bar data within time range
        """
        pass
    
    @abstractmethod
    def save_funding_rate(self, rate: FundingRateData) -> None:
        """保存资金费率
        
        Args:
            rate: Funding rate data to save
        """
        pass
    
    @abstractmethod
    def get_funding_rates(
        self,
        symbol: str,
        start_time: datetime,
        end_time: datetime
    ) -> List[FundingRateData]:
        """获取资金费率数据
        
        Args:
            symbol: Trading pair symbol
            start_time: Start of time range
            end_time: End of time range
        
        Returns:
            List of funding rate data within time range
        """
        pass


class InMemoryDataRepository(DataRepository):
    """内存数据存储 - 适合回测"""
    
    def __init__(self):
        """Initialize in-memory data repository."""
        self._bars: Dict[str, List[BarData]] = defaultdict(list)
        self._funding_rates: Dict[str, List[FundingRateData]] = defaultdict(list)
        self._lock = threading.Lock()
    
    def save_bar(self, bar: BarData) -> None:
        """Save bar data to memory.
        
        Args:
            bar: Bar data to save
        """
        with self._lock:
            self._bars[bar.symbol].append(bar)
    
    def get_bars(
        self,
        symbol: str,
        start_time: datetime,
        end_time: datetime
    ) -> List[BarData]:
        """Get bar data within time range.
        
        Args:
            symbol: Trading pair symbol
            start_time: Start of time range
            end_time: End of time range
        
        Returns:
            List of bar data within time range
        """
        with self._lock:
            bars = self._bars.get(symbol, [])
            return [
                b for b in bars
                if start_time <= b.timestamp <= end_time
            ]
    
    def save_funding_rate(self, rate: FundingRateData) -> None:
        """Save funding rate data to memory.
        
        Args:
            rate: Funding rate data to save
        """
        with self._lock:
            self._funding_rates[rate.symbol].append(rate)
    
    def get_funding_rates(
        self,
        symbol: str,
        start_time: datetime,
        end_time: datetime
    ) -> List[FundingRateData]:
        """Get funding rate data within time range.
        
        Args:
            symbol: Trading pair symbol
            start_time: Start of time range
            end_time: End of time range
        
        Returns:
            List of funding rate data within time range
        """
        with self._lock:
            rates = self._funding_rates.get(symbol, [])
            return [
                r for r in rates
                if start_time <= r.timestamp <= end_time
            ]
