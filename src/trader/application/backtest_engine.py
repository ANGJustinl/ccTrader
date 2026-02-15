"""Backtest engine for running trading strategies.

Provides backtesting capability with order matching and performance metrics.
"""
from decimal import Decimal
from datetime import datetime, timedelta
from typing import Callable, List, Optional

from ..infrastructure.clock import BacktestClock, IClock
from ..infrastructure.event_bus import EventBus, Event, EventType
from ..infrastructure.data_repository import (
    DataRepository,
    BarData,
    FundingRateData,
    InMemoryDataRepository,
)
from ..utils.slippage import VolatilitySlippageModel, BarDataForSlippage
from .simulated_broker import SimulatedBroker
from .order import Order
from .backtest_report import BacktestReportGenerator


class BacktestEngine:
    """回测引擎核心

    Provides backtesting capability for trading strategies.

    Attributes:
        clock: Backtest clock instance
        event_bus: Event bus for publishing events
        broker: Simulated broker for order matching
        data_repo: Data repository for storing market data
        strategy: Strategy function to execute
        on_bar_callbacks: List of callback functions to call on each bar
        current_bar: Current bar being processed
        trades: List of executed trades
        equity_curve: Equity curve data points
        _funding_rate_cursor: Cursor for iterating through funding rate data
        _processed_funding_timestamps: Track processed funding rate timestamps
    """

    def __init__(
        self,
        initial_balance: Decimal = Decimal("10000"),
        slippage: Decimal = Decimal("0.0005"),
        commission: Decimal = Decimal("0.0004"),
        use_volatility_slippage: bool = False,
    ):
        """Initialize backtest engine.

        Args:
            initial_balance: Initial account balance (default: 10000)
            slippage: Slippage rate as decimal (default: 0.0005 = 0.05%)
            commission: Commission rate as decimal (default: 0.0004 = 0.04%)
            use_volatility_slippage: Whether to use volatility-based dynamic slippage
        """
        # Ensure all parameters are Decimal
        if not isinstance(initial_balance, Decimal):
            initial_balance = Decimal(str(initial_balance))
        if not isinstance(slippage, Decimal):
            slippage = Decimal(str(slippage))
        if not isinstance(commission, Decimal):
            commission = Decimal(str(commission))
            
        self.clock = BacktestClock()
        self.event_bus = EventBus()
        self.broker = SimulatedBroker(
            clock=self.clock,
            event_bus=self.event_bus,
            initial_balance=initial_balance,
            slippage_rate=slippage,
            commission_rate=commission,
        )
        self.data_repo: Optional[DataRepository] = None
        self.strategy: Optional[Callable] = None
        self.on_bar_callbacks: List[Callable] = []
        self.current_bar: Optional[BarData] = None
        self.all_bars: List[BarData] = []  # Store all bars for volatility calculation

        # Volatility-based slippage
        self.use_volatility_slippage = use_volatility_slippage
        self.slippage_model = VolatilitySlippageModel() if use_volatility_slippage else None

        # 性能指标
        self.trades: List[dict] = []
        self.equity_curve: List[dict] = []
        
        # 累计统计
        self.total_funding_paid: Decimal = Decimal("0")
        self.total_slippage: Decimal = Decimal("0")
        self.total_commission: Decimal = Decimal("0")
        
        # 资金费率处理游标
        self._funding_rate_cursor = 0
        self._processed_funding_timestamps = set()

    def load_data(
        self,
        bars: List[BarData],
        funding_rates: Optional[List[FundingRateData]] = None,
    ) -> None:
        """加载回测数据

        Args:
            bars: List of bar data
            funding_rates: Optional list of funding rate data
        """
        self.data_repo = InMemoryDataRepository()
        self.all_bars = bars.copy()  # Store all bars for volatility calculation

        for bar in bars:
            self.data_repo.save_bar(bar)

        if funding_rates:
            for rate in funding_rates:
                self.data_repo.save_funding_rate(rate)

    def download_data(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        timeframe: str = "15m",
        exchange: str = "binance",
    ) -> None:
        """下载历史数据

        Args:
            symbol: Trading pair symbol
            start_date: Start date for data
            end_date: End date for data
            timeframe: Timeframe for bars (default: "15m")
            exchange: Exchange name (default: "binance")
        """
        from ..infrastructure.data_downloader import DataDownloader

        downloader = DataDownloader(exchange)

        # 下载 K 线数据
        since = int(start_date.timestamp() * 1000)
        bars = downloader.download_ohlcv(symbol, timeframe, since)

        # 下载资金费率数据
        funding_rates = downloader.download_funding_rates(symbol, since)

        self.load_data(bars, funding_rates)

    def set_strategy(self, strategy) -> None:
        """设置策略

        Args:
            strategy: Strategy instance or function
        """
        # Check if it's a strategy instance with on_bar method
        if hasattr(strategy, 'on_bar') and callable(strategy.on_bar):
            self.strategy = strategy.on_bar
            # Store reference to strategy instance for later use
            self._strategy_instance = strategy
        elif callable(strategy):
            self.strategy = strategy
            self._strategy_instance = None
        else:
            raise ValueError("Strategy must be a callable or have on_bar method")

    def add_on_bar_callback(self, callback: Callable) -> None:
        """添加 K 线回调函数

        Args:
            callback: Callback function to call on each bar
        """
        self.on_bar_callbacks.append(callback)

    def run(self, symbol: str) -> dict:
        """运行回测

        Args:
            symbol: Trading pair symbol to backtest

        Returns:
            Dictionary of backtest metrics
        """
        if not self.data_repo:
            raise ValueError("No data loaded")

        if not self.strategy:
            raise ValueError("No strategy set")

        # 获取所有数据
        bars = self.data_repo._bars.get(symbol, [])

        if not bars:
            raise ValueError(f"No bars for symbol {symbol}")

        # 初始化策略
        if hasattr(self, '_strategy_instance') and self._strategy_instance is not None:
            self._strategy_instance.broker = self.broker
            self._strategy_instance.clock = self.clock
            self._strategy_instance.event_bus = self.event_bus
            # 订阅事件
            self._setup_event_listeners()
        else:
            self.strategy.__dict__["broker"] = self.broker
            self.strategy.__dict__["clock"] = self.clock
            self.strategy.__dict__["event_bus"] = self.event_bus

        # 重置资金费率游标
        self._funding_rate_cursor = 0
        self._processed_funding_timestamps = set()

        # 策略启动回调
        if hasattr(self, '_strategy_instance') and self._strategy_instance is not None:
            if hasattr(self._strategy_instance, 'on_start'):
                self._strategy_instance.on_start()

        # 主循环
        for bar in bars:
            self._process_bar(bar)

        # 策略停止回调
        if hasattr(self, '_strategy_instance') and self._strategy_instance is not None:
            if hasattr(self._strategy_instance, 'on_stop'):
                self._strategy_instance.on_stop()

        # 计算最终指标
        return self._calculate_metrics()
    
    def _setup_event_listeners(self) -> None:
        """设置事件监听器来调用策略回调"""
        if not hasattr(self, '_strategy_instance') or self._strategy_instance is None:
            return
        
        strategy = self._strategy_instance
        
        # 订阅订单更新事件
        def on_order_event(event: Event):
            order_id = event.data.get("order_id")
            if order_id and order_id in self.broker.orders:
                order = self.broker.orders[order_id]
                if hasattr(strategy, 'on_order_update'):
                    strategy.on_order_update(order)
        
        self.event_bus.subscribe(EventType.ORDER_SUBMITTED, on_order_event)
        self.event_bus.subscribe(EventType.ORDER_FILLED, on_order_event)
        self.event_bus.subscribe(EventType.ORDER_CANCELLED, on_order_event)

    def _process_bar(self, bar: BarData) -> None:
        """处理单根 K 线

        Args:
            bar: Bar data to process
        """
        # 更新时钟
        self.clock.set_time(bar.timestamp)

        # 保存当前 K 线
        self.current_bar = bar

        # 发布 K 线事件
        self.event_bus.publish(
            Event(
                type=EventType.BAR,
                timestamp=bar.timestamp,
                data={
                    "symbol": bar.symbol,
                    "open": str(bar.open),
                    "high": str(bar.high),
                    "low": str(bar.low),
                    "close": str(bar.close),
                    "volume": str(bar.volume),
                },
            )
        )

        # 撮合订单
        fills = self.broker.match_orders(bar.symbol, bar.high, bar.low, bar.close)

        # 记录成交
        for fill in fills:
            self.trades.append(
                {
                    "timestamp": fill.timestamp,
                    "price": fill.price,
                    "quantity": fill.quantity,
                    "commission": fill.commission,
                    "side": fill.side.value,
                }
            )
            # 累计手续费
            self.total_commission += fill.commission

        # [关键修复] 处理资金费率数据并触发策略回调
        self._process_funding_rates(bar.timestamp, bar.symbol)

        # 检查资金费率结算（8小时一次：00:00, 08:00, 16:00 UTC）
        self._check_funding_settlement(bar.timestamp)

        # 调用策略
        if self.strategy:
            try:
                self.strategy(bar)
            except Exception as e:
                self.event_bus.publish(
                    Event(
                        type=EventType.ERROR,
                        timestamp=bar.timestamp,
                        data={"error": str(e)},
                    )
                )

        # 调用回调函数
        for callback in self.on_bar_callbacks:
            callback(bar)

        # 记录权益曲线
        self.equity_curve.append(
            {
                "timestamp": bar.timestamp,
                "balance": self.broker.balance,
                "positions": len(self.broker.positions),
            }
        )

    def _process_funding_rates(self, bar_timestamp: datetime, symbol: str) -> None:
        """处理资金费率数据并触发策略回调

        在每个 K 线处理时，检查是否有新的资金费率数据需要处理
        并触发策略的 on_funding_rate 回调

        Args:
            bar_timestamp: Current bar timestamp
            symbol: Trading pair symbol
        """
        if not self.data_repo:
            return

        # 获取该交易对的资金费率数据
        funding_rates = self.data_repo._funding_rates.get(symbol, [])
        if not funding_rates:
            return

        # 使用游标遍历所有未处理的资金费率数据
        while self._funding_rate_cursor < len(funding_rates):
            funding_data = funding_rates[self._funding_rate_cursor]
            
            # 如果资金费率时间戳大于当前 K 线时间戳，跳过（还没到这个时间）
            if funding_data.timestamp > bar_timestamp:
                break
            
            # 检查是否已经处理过这个时间戳
            funding_timestamp_key = funding_data.timestamp.isoformat()
            if funding_timestamp_key in self._processed_funding_timestamps:
                self._funding_rate_cursor += 1
                continue
            
            # 触发策略回调
            if hasattr(self, '_strategy_instance') and self._strategy_instance is not None:
                if hasattr(self._strategy_instance, 'on_funding_rate'):
                    self._strategy_instance.on_funding_rate(funding_data.rate, funding_data.timestamp)
            
            # 标记为已处理
            self._processed_funding_timestamps.add(funding_timestamp_key)
            self._funding_rate_cursor += 1

    def _check_funding_settlement(self, timestamp: datetime) -> None:
        """检查并处理资金费率结算

        资金费率每 8 小时结算一次（00:00, 08:00, 16:00 UTC）
        这里应用资金费率到持仓的盈亏

        Args:
            timestamp: Current timestamp
        """
        # 资金费率每 8 小时结算一次（00:00, 08:00, 16:00 UTC）
        hour = timestamp.hour

        if hour not in [0, 8, 16]:
            return

        # 获取资金费率
        if not self.data_repo:
            return

            # 查找最近的资金费率
        funding_rates = self.data_repo._funding_rates.get(self.current_bar.symbol, [])
        if not funding_rates:
            return

        # 使用最新的费率
        rate = funding_rates[-1].rate

        # 应用资金费率到所有仓位
        for symbol, position in self.broker.positions.items():
            position_value = position.quantity * self.current_bar.close

            if position.side == "LONG":
                # 多头扣除费率
                funding = position_value * rate
                self.broker.balance -= funding
                self.total_funding_paid += funding
            else:
                # 空头获得费率
                funding = position_value * rate
                self.broker.balance += funding
                # 空头获得的费率不增加累计付费统计

            self.event_bus.publish(
                Event(
                    type=EventType.FUNDING_RATE_APPLIED,
                    timestamp=timestamp,
                    data={
                        "symbol": symbol,
                        "rate": str(rate),
                        "funding": str(funding),
                        "balance": str(self.broker.balance),
                    },
                )
            )

    def _calculate_metrics(self) -> dict:
        """计算回测指标

        Returns:
            Dictionary of backtest metrics including full report
        """
        initial_balance = self.broker.initial_balance
        final_balance = self.broker.balance
        total_return = (final_balance - initial_balance) / initial_balance * 100

        # 计算胜率
        winning_trades = 0
        losing_trades = 0

        # 从交易记录计算（简化处理）
        # 实际应该跟踪每个仓位的盈亏

        # 生成完整回测报告
        report_generator = BacktestReportGenerator()
        report = report_generator.generate_report(
            initial_balance=initial_balance,
            final_balance=final_balance,
            equity_curve=self.equity_curve,
            trades=[],  # TODO: Convert self.trades to TradeRecord format
            total_commission=self.total_commission,
            total_slippage=self.total_slippage,
            total_funding_paid=self.total_funding_paid,
        )

        # 格式化报告
        formatted_report = report_generator.format_report(report)

        return {
            "initial_balance": initial_balance,
            "final_balance": final_balance,
            "total_return": total_return,
            "total_trades": len(self.trades),
            "equity_curve": self.equity_curve,
            "total_commission": self.total_commission,
            "total_slippage": self.total_slippage,
            "total_funding_paid": self.total_funding_paid,
            "report": report,
            "formatted_report": formatted_report,
        }
