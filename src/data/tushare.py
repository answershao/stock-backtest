"""Tushare-specific data workflows."""

from src.data.tushare_analysis import (
    ExpectedReturnTimeseriesRequest,
    build_expected_return_timeseries,
    calculate_expected_return_from_cache,
)
from src.data.tushare_expected_return import TushareConsensusSnapshot, create_tushare_pro
from src.data.tushare_strategy import (
    BacktestOutputPaths,
    FULL_HISTORY_START_DATE,
    TushareBacktestArtifacts,
    TushareCacheArtifacts,
    fetch_open_trade_dates,
    fetch_open_trade_dates_cached,
    prefetch_tushare_strategy_cache,
    run_tushare_expected_return_backtest,
    write_backtest_artifacts,
)

__all__ = [
    "BacktestOutputPaths",
    "ExpectedReturnTimeseriesRequest",
    "FULL_HISTORY_START_DATE",
    "TushareBacktestArtifacts",
    "TushareCacheArtifacts",
    "TushareConsensusSnapshot",
    "build_expected_return_timeseries",
    "calculate_expected_return_from_cache",
    "create_tushare_pro",
    "fetch_open_trade_dates",
    "fetch_open_trade_dates_cached",
    "prefetch_tushare_strategy_cache",
    "run_tushare_expected_return_backtest",
    "write_backtest_artifacts",
]
