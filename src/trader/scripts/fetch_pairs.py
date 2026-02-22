#!/usr/bin/env python3
"""Trading pairs scanner for mean-reversion strategies.

Fetches active USDT futures pairs from Binance, calculates volatility metrics,
and identifies candidates suitable for mean-reversion trading strategies.

适配说明:
- 使用 DataDownloader 进行数据获取
- 统一使用 logging 进行日志记录
- 添加 tenacity 重试机制
- 兼容现有项目配置体系
"""

import argparse
import logging
import os
import sys
import time
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from statsmodels.tsa.stattools import adfuller
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from trader.infrastructure.data_downloader import DataDownloader
from trader.infrastructure.data_repository import BarData

# 配置日志
logger = logging.getLogger(__name__)


class PairScannerConfig:
    """交易对扫描器配置"""

    def __init__(
        self,
        exchange: str = "binance",
        env_file: str = ".env.dev",
        testnet: bool = False,
        market_type: str = "future",
        min_volume_usd: float = 50_000_000,
        timeframe: str = "15m",
        lookback_bars: int = 500,
        adf_significance: float = 0.05,
        rvol_weight: float = 0.4,
        cv_weight: float = 0.3,
        adf_weight: float = 0.3,
        max_retries: int = 3,
        retry_delay: float = 1.0,
    ):
        self.exchange = exchange
        self.env_file = env_file
        self.testnet = testnet
        self.market_type = market_type
        self.min_volume_usd = min_volume_usd
        self.timeframe = timeframe
        self.lookback_bars = lookback_bars
        self.adf_significance = adf_significance
        self.rvol_weight = rvol_weight
        self.cv_weight = cv_weight
        self.adf_weight = adf_weight
        self.max_retries = max_retries
        self.retry_delay = retry_delay


class PairScanner:
    """交易对扫描器 - 用于发现均值回归策略候选交易对"""

    def __init__(self, config: Optional[PairScannerConfig] = None):
        """初始化扫描器

        Args:
            config: 扫描器配置，使用默认配置如果未提供
        """
        self.config = config or PairScannerConfig()
        self._setup_logging()
        self._load_environment()
        self._init_downloader()

    def _setup_logging(self) -> None:
        """配置日志记录"""
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        # 减少第三方库的日志级别
        logging.getLogger("urllib3").setLevel(logging.WARNING)
        logging.getLogger("ccxt").setLevel(logging.WARNING)

    def _load_environment(self) -> None:
        """加载环境变量配置"""
        env_path = Path(self.config.env_file)
        if env_path.exists():
            load_dotenv(env_path)
            logger.info(f"加载环境配置: {env_path}")
        else:
            logger.warning(f"环境文件不存在: {env_path}")

    def _init_downloader(self) -> None:
        """初始化数据下载器"""
        try:
            self.downloader = DataDownloader(
                exchange_name=self.config.exchange,
                env_file=self.config.env_file,
                testnet=self.config.testnet,
            )
            logger.info(
                f"初始化数据下载器: {self.config.exchange} "
                f"(testnet={self.config.testnet})"
            )
        except Exception as e:
            logger.error(f"初始化数据下载器失败: {e}")
            raise

    @retry(
        retry=retry_if_exception_type(Exception),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    def get_active_usdt_futures(self) -> List[str]:
        """获取活跃的 USDT 永续合约交易对

        Returns:
            List of active USDT futures symbols
        """
        try:
            # 使用 CCXT 获取所有交易对
            markets = self.downloader.exchange.load_markets()
            symbols = []

            for symbol, market in markets.items():
                # 筛选 USDT 永续合约
                if (
                    market.get("quote") == "USDT"
                    and market.get("type") == "swap"
                    and market.get("linear", False)
                    and market.get("active", False)
                ):
                    # 获取 24h 成交量
                    try:
                        ticker = self.downloader.exchange.fetch_ticker(symbol)
                        quote_volume = float(ticker.get("quoteVolume", 0))

                        if quote_volume >= self.config.min_volume_usd:
                            symbols.append(symbol)
                            logger.debug(f"添加交易对: {symbol}, 24h成交量: ${quote_volume:,.0f}")
                    except Exception as e:
                        logger.debug(f"获取 {symbol} ticker 失败: {e}")
                        continue

            logger.info(f"找到 {len(symbols)} 个符合条件的 USDT 永续合约")
            return sorted(symbols)

        except Exception as e:
            logger.error(f"获取活跃交易对失败: {e}")
            raise

    @retry(
        retry=retry_if_exception_type(Exception),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    def get_klines(self, symbol: str) -> pd.DataFrame:
        """获取 K 线数据

        Args:
            symbol: Trading pair symbol (e.g., "BTC/USDT:USDT")

        Returns:
            DataFrame with OHLCV data
        """
        try:
            bars = self.downloader.download_ohlcv(
                symbol=symbol,
                timeframe=self.config.timeframe,
                limit=self.config.lookback_bars,
            )

            if not bars:
                logger.warning(f"{symbol}: 没有返回数据")
                return pd.DataFrame()

            # 转换为 DataFrame
            df = pd.DataFrame([
                {
                    "timestamp": bar.timestamp,
                    "high": float(bar.high),
                    "low": float(bar.low),
                    "close": float(bar.close),
                }
                for bar in bars
            ])

            logger.debug(f"{symbol}: 获取了 {len(df)} 条 K 线数据")
            return df

        except Exception as e:
            logger.error(f"{symbol}: 获取 K 线数据失败: {e}")
            raise

    def calculate_metrics(self, df: pd.DataFrame) -> Tuple[float, float, float, float]:
        """计算均值回归指标

        Args:
            df: DataFrame with OHLCV data

        Returns:
            Tuple of (rvol, cv_vol, adf_stat, p_value)
        """
        if df.empty or len(df) < 20:
            return 0.0, float("inf"), 0.0, 1.0

        atr_period = 14

        # Calculate TR and ATR
        df["prev_close"] = df["close"].shift(1)
        df["tr"] = np.maximum(
            df["high"] - df["low"],
            np.maximum(
                abs(df["high"] - df["prev_close"]),
                abs(df["low"] - df["prev_close"]),
            ),
        )
        df["atr"] = df["tr"].rolling(window=atr_period).mean()
        df["sma"] = df["close"].rolling(window=atr_period).mean()

        # 1. Relative Volatility (RVol)
        df["rvol"] = (df["atr"] / df["sma"]) * 100
        avg_rvol = df["rvol"].mean()

        # 2. Volatility Stability (CV of RVol)
        vol_std = df["rvol"].std()
        cv_vol = vol_std / avg_rvol if avg_rvol > 0 else float("inf")

        # 3. Mean Reversion (ADF Test on close prices)
        close_prices = df["close"].dropna().values
        try:
            adf_result = adfuller(close_prices, maxlag=1)
            adf_stat = adf_result[0]
            p_value = adf_result[1]
        except Exception as e:
            logger.debug(f"ADF test failed: {e}")
            adf_stat, p_value = 0.0, 1.0

        return avg_rvol, cv_vol, adf_stat, p_value

    def scan_markets(self) -> pd.DataFrame:
        """扫描市场，寻找均值回归候选交易对

        Returns:
            DataFrame with scan results sorted by score
        """
        logger.info("开始扫描市场...")

        # 获取活跃交易对
        try:
            symbols = self.get_active_usdt_futures()
        except Exception as e:
            logger.error(f"获取活跃交易对失败: {e}")
            return pd.DataFrame()

        if not symbols:
            logger.warning("没有找到符合条件的交易对")
            return pd.DataFrame()

        logger.info(f"扫描 {len(symbols)} 个交易对...")
        results = []

        for i, symbol in enumerate(symbols, 1):
            try:
                logger.debug(f"[{i}/{len(symbols)}] 分析 {symbol}...")

                df = self.get_klines(symbol)
                if df.empty:
                    continue

                rvol, cv_vol, adf_stat, p_value = self.calculate_metrics(df)

                # 筛选: 显著的均值回归特性
                if p_value < self.config.adf_significance:
                    results.append({
                        "symbol": symbol,
                        "rvol_pct": round(rvol, 2),
                        "vol_cv": round(cv_vol, 4),
                        "adf_stat": round(adf_stat, 2),
                        "p_value": round(p_value, 4),
                    })
                    logger.debug(f"{symbol} 通过筛选 (p={p_value:.4f})")

            except Exception as e:
                logger.warning(f"分析 {symbol} 失败: {e}")
                continue

            # 限速保护
            time.sleep(0.1)

        if not results:
            logger.warning("没有交易对通过筛选条件")
            return pd.DataFrame()

        # 构建 DataFrame
        df_res = pd.DataFrame(results)

        # 标准化指标并计算综合得分
        # 更高的 RVol 更好，更低的 Vol_CV 更好，更低的 ADF_Stat (更负) 更好
        rvol_range = df_res["rvol_pct"].max() - df_res["rvol_pct"].min()
        cv_range = df_res["vol_cv"].max() - df_res["vol_cv"].min()
        adf_range = df_res["adf_stat"].max() - df_res["adf_stat"].min()

        if rvol_range > 0:
            df_res["rvol_score"] = (df_res["rvol_pct"] - df_res["rvol_pct"].min()) / rvol_range
        else:
            df_res["rvol_score"] = 1.0

        if cv_range > 0:
            df_res["cv_score"] = 1 - ((df_res["vol_cv"] - df_res["vol_cv"].min()) / cv_range)
        else:
            df_res["cv_score"] = 1.0

        if adf_range > 0:
            df_res["adf_score"] = 1 - ((df_res["adf_stat"] - df_res["adf_stat"].min()) / adf_range)
        else:
            df_res["adf_score"] = 1.0

        # 加权综合得分 (权重可配置)
        df_res["total_score"] = (
            df_res["rvol_score"] * self.config.rvol_weight
            + df_res["cv_score"] * self.config.cv_weight
            + df_res["adf_score"] * self.config.adf_weight
        )

        # 排序并选择列
        df_res = df_res.sort_values("total_score", ascending=False).reset_index(drop=True)

        logger.info(f"扫描完成，找到 {len(df_res)} 个候选交易对")
        return df_res[["symbol", "rvol_pct", "vol_cv", "adf_stat", "total_score"]]

    def export_results(self, df: pd.DataFrame, output_path: Optional[str] = None) -> str:
        """导出扫描结果

        Args:
            df: Scan results DataFrame
            output_path: Output file path (optional)

        Returns:
            Path to exported file
        """
        if df.empty:
            logger.warning("没有数据可导出")
            return ""

        if output_path is None:
            timestamp = pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")
            output_path = f"pair_scan_results_{timestamp}.csv"

        df.to_csv(output_path, index=False)
        logger.info(f"结果已导出到: {output_path}")
        return output_path


def create_parser() -> argparse.ArgumentParser:
    """创建命令行参数解析器"""
    parser = argparse.ArgumentParser(
        description="Scan and filter trading pairs for mean-reversion strategies",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # 基本扫描 (使用默认配置)
  python fetch_pairs.py

  # 使用 Testnet
  python fetch_pairs.py --testnet

  # 调整筛选条件
  python fetch_pairs.py --min-volume 100000000 --timeframe 1h

  # 导出结果到指定文件
  python fetch_pairs.py --output results.csv --top 20
        """,
    )

    # 基础配置
    parser.add_argument(
        "--env-file",
        default=".env.dev",
        help="环境变量文件路径 (默认: .env.dev)",
    )
    parser.add_argument(
        "--testnet",
        action="store_true",
        help="使用 Testnet 环境",
    )
    parser.add_argument(
        "--market-type",
        default="future",
        choices=["spot", "future"],
        help="市场类型 (默认: future)",
    )

    # 扫描参数
    parser.add_argument(
        "--min-volume",
        type=float,
        default=50_000_000,
        help="最小24h成交量 (USD) (默认: 50,000,000)",
    )
    parser.add_argument(
        "--timeframe",
        default="15m",
        choices=["1m", "5m", "15m", "1h", "4h", "1d"],
        help="K线时间周期 (默认: 15m)",
    )
    parser.add_argument(
        "--lookback",
        type=int,
        default=500,
        help="回看K线数量 (默认: 500)",
    )
    parser.add_argument(
        "--adf-pvalue",
        type=float,
        default=0.05,
        help="ADF检验p值阈值 (默认: 0.05)",
    )

    # 评分权重
    parser.add_argument(
        "--rvol-weight",
        type=float,
        default=0.4,
        help="相对波动率权重 (默认: 0.4)",
    )
    parser.add_argument(
        "--cv-weight",
        type=float,
        default=0.3,
        help="波动率变异系数权重 (默认: 0.3)",
    )
    parser.add_argument(
        "--adf-weight",
        type=float,
        default=0.3,
        help="ADF统计量权重 (默认: 0.3)",
    )

    # 输出选项
    parser.add_argument(
        "--output",
        type=str,
        help="导出结果到CSV文件路径",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=15,
        help="显示前N个结果 (默认: 15)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="显示详细日志",
    )

    return parser


def main():
    """Main entry point for the pair scanner."""
    parser = create_parser()
    args = parser.parse_args()

    # 配置日志级别
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.setLevel(logging.DEBUG)
    else:
        logging.getLogger().setLevel(logging.INFO)

    # 创建配置
    config = PairScannerConfig(
        exchange="binance",
        env_file=args.env_file,
        testnet=args.testnet,
        market_type=args.market_type,
        min_volume_usd=args.min_volume,
        timeframe=args.timeframe,
        lookback_bars=args.lookback,
        adf_significance=args.adf_pvalue,
        rvol_weight=args.rvol_weight,
        cv_weight=args.cv_weight,
        adf_weight=args.adf_weight,
    )

    # 创建扫描器并执行扫描
    try:
        scanner = PairScanner(config)
        results = scanner.scan_markets()

        if results.empty:
            print("\n未找到符合条件的交易对。")
            return 0

        # 显示结果
        top_n = args.top
        print(f"\n{'='*80}")
        print(f"Top {min(top_n, len(results))} 均值回归策略候选交易对")
        print(f"{'='*80}")
        print(results.head(top_n).to_string(index=False))
        print(f"{'='*80}\n")

        # 导出结果
        if args.output:
            scanner.export_results(results, args.output)

        return 0

    except KeyboardInterrupt:
        print("\n\n用户中断扫描")
        return 130
    except Exception as e:
        logger.error(f"扫描失败: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())