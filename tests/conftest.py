"""
Pytest configuration and shared fixtures.
"""

import pytest


@pytest.fixture
def sample_config():
    """提供示例配置的fixture"""
    return {
        "api_key": "test_key",
        "api_secret": "test_secret",
        "exchange": "binance",
    }


@pytest.fixture
def sample_market_data():
    """提供示例市场数据的fixture"""
    return {
        "symbol": "BTC/USDT",
        "timestamp": 1234567890,
        "open": 50000.0,
        "high": 50500.0,
        "low": 49500.0,
        "close": 50200.0,
        "volume": 100.0,
    }
