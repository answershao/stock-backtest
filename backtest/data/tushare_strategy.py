from __future__ import annotations

from backtest.data.tushare_analysis import (
    calculate_expected_return_from_cache,
    normalize_daily_basic as _normalize_daily_basic,
    normalize_fina_indicator as _normalize_fina_indicator,
    normalize_report_rc as _normalize_report_rc,
    resolve_base_annual_eps_with_ann_date as _resolve_base_annual_eps_with_ann_date,
    resolve_trade_date_on_or_before_from_cache as _resolve_trade_date_on_or_before_from_cache,
)
from backtest.data.tushare_cache_helpers import (
    read_single_cache_frame as _read_single_cache_frame,
    read_stock_cache_frame as _read_stock_cache_frame,
)
from backtest.data.tushare_strategy_data import (
    BacktestOutputPaths,
    FULL_HISTORY_START_DATE,
    TushareBacktestArtifacts,
    TushareCacheArtifacts,
    build_signal_frame_from_tushare,
    clear_tushare_cache_dir,
    fetch_open_trade_dates,
    fetch_open_trade_dates_cached,
    fetch_price_history_from_tushare,
    prefetch_tushare_strategy_cache,
    resolve_next_trade_date as _resolve_next_trade_date,
    resolve_strategy_dates,
    run_tushare_expected_return_backtest,
    write_backtest_artifacts,
    years_before as _years_before,
)

__all__ = [
    "FULL_HISTORY_START_DATE",
    "BacktestOutputPaths",
    "TushareBacktestArtifacts",
    "TushareCacheArtifacts",
    "build_signal_frame_from_tushare",
    "calculate_expected_return_from_cache",
    "clear_tushare_cache_dir",
    "fetch_open_trade_dates",
    "fetch_open_trade_dates_cached",
    "fetch_price_history_from_tushare",
    "prefetch_tushare_strategy_cache",
    "resolve_strategy_dates",
    "run_tushare_expected_return_backtest",
    "write_backtest_artifacts",
    "_normalize_daily_basic",
    "_normalize_fina_indicator",
    "_normalize_report_rc",
    "_read_single_cache_frame",
    "_read_stock_cache_frame",
    "_resolve_base_annual_eps_with_ann_date",
    "_resolve_next_trade_date",
    "_resolve_trade_date_on_or_before_from_cache",
    "_years_before",
]
