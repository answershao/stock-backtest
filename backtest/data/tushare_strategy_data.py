from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from backtest.expected_return import GrowthInputs, calculate_expected_return_3y, resolve_target_quarter
from backtest.strategy import BacktestResult, StrategyConfig, run_expected_return_strategy
from backtest.data.cache import TushareDataCache
from backtest.data.tushare_analysis import normalize_daily_basic, normalize_fina_indicator, normalize_report_rc, resolve_base_annual_eps
from backtest.data.tushare_cache_helpers import (
    filter_frame_by_date_range,
    legacy_cache_patterns,
    load_cached_dataset_frame,
    sanitize_cache_key_parts,
    update_incremental_cache,
)
from backtest.data.tushare_expected_return import build_consensus_growth_from_report_rc, fetch_report_rc_from_tushare

FULL_HISTORY_START_DATE = "19900101"


@dataclass(frozen=True)
class TushareBacktestArtifacts:
    price_df: pd.DataFrame
    signal_df: pd.DataFrame
    backtest_result: BacktestResult
    rebalance_dates: tuple[pd.Timestamp, ...]


@dataclass(frozen=True)
class TushareCacheArtifacts:
    trading_dates: tuple[pd.Timestamp, ...]
    cache_dir: Path


@dataclass(frozen=True)
class BacktestOutputPaths:
    portfolio_path: Path
    trades_path: Path
    holdings_path: Path
    signals_path: Path
    rebalance_path: Path
    rebalance_summary_path: Path
    rebalance_plot_path: Path
    stock_report_dir: Path


def fetch_open_trade_dates(pro, start_date: str, end_date: str) -> tuple[pd.Timestamp, ...]:
    cal = pro.trade_cal(exchange="", start_date=start_date, end_date=end_date, is_open="1")
    if cal is None or cal.empty:
        raise ValueError("Tushare 未返回交易日历。")
    dates = pd.to_datetime(cal["cal_date"].astype(str), format="%Y%m%d", errors="coerce").dropna()
    if dates.empty:
        raise ValueError("交易日历为空。")
    return tuple(sorted(dates.tolist()))


def fetch_open_trade_dates_cached(
    pro,
    *,
    start_date: str,
    end_date: str,
    cache: TushareDataCache | None,
) -> tuple[pd.Timestamp, ...]:
    if cache is None:
        return fetch_open_trade_dates(pro, start_date, end_date)
    frame = load_cached_dataset_frame(
        cache=cache,
        dataset="trade_cal",
        canonical_key_parts=["full", "is_open_1"],
        legacy_glob_patterns=legacy_cache_patterns(dataset="trade_cal", key_parts=["full", "is_open_1"]),
        fallback_fetcher=lambda: cache.load_or_fetch(
            dataset="trade_cal",
            key_parts=[start_date, end_date, "is_open_1"],
            fetcher=lambda: pro.trade_cal(exchange="", start_date=start_date, end_date=end_date, is_open="1"),
        ),
    )
    if frame.empty:
        raise ValueError("Tushare 未返回交易日历。")
    frame = filter_frame_by_date_range(frame, "cal_date", start_date, end_date)
    dates = pd.to_datetime(frame["cal_date"].astype(str), format="%Y%m%d", errors="coerce").dropna()
    if dates.empty:
        raise ValueError("交易日历为空。")
    return tuple(sorted(dates.tolist()))


def resolve_strategy_dates(
    *,
    trading_dates: tuple[pd.Timestamp, ...],
    start_date: str,
    end_date: str,
    month_days: tuple[str, ...] = ("05-01", "11-01"),
) -> tuple[pd.Timestamp, tuple[pd.Timestamp, ...]]:
    start_ts = pd.Timestamp(start_date)
    end_ts = pd.Timestamp(end_date)
    actual_start = resolve_next_trade_date(trading_dates, start_ts)

    resolved: list[pd.Timestamp] = []
    for year in range(actual_start.year, end_ts.year + 1):
        for month_day in month_days:
            target = pd.Timestamp(f"{year}-{month_day}")
            if target < actual_start or target > end_ts:
                continue
            actual = resolve_next_trade_date(trading_dates, target)
            if actual is None or actual > end_ts:
                continue
            if actual not in resolved:
                resolved.append(actual)
    return actual_start, tuple(sorted(resolved))


def fetch_price_history_from_tushare(
    pro,
    *,
    stock_pool: list[str],
    start_date: str,
    end_date: str,
    trading_dates: tuple[pd.Timestamp, ...] | None = None,
    cache: TushareDataCache | None = None,
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for ts_code in stock_pool:
        if cache is None:
            daily = pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date, fields="ts_code,trade_date,close")
        else:
            daily = load_cached_dataset_frame(
                cache=cache,
                dataset="daily",
                canonical_key_parts=[ts_code, "close"],
                legacy_glob_patterns=legacy_cache_patterns(dataset="daily", key_parts=[ts_code, "close"]),
                fallback_fetcher=lambda ts_code=ts_code: cache.load_or_fetch(
                    dataset="daily",
                    key_parts=[ts_code, start_date, end_date, "close"],
                    fetcher=lambda: pro.daily(
                        ts_code=ts_code,
                        start_date=start_date,
                        end_date=end_date,
                        fields="ts_code,trade_date,close",
                    ),
                ),
            )
            daily = filter_frame_by_date_range(daily, "trade_date", start_date, end_date)
        if daily is None or daily.empty:
            continue
        data = daily.rename(columns={"ts_code": "code", "trade_date": "date"}).copy()
        data["date"] = pd.to_datetime(data["date"], format="%Y%m%d", errors="coerce")
        data["close"] = pd.to_numeric(data["close"], errors="coerce")
        data = data.dropna(subset=["date", "close"])
        data = data.sort_values("date").drop_duplicates(subset=["date"], keep="last")
        if trading_dates is not None:
            calendar = pd.Index(trading_dates, name="date")
            reindexed = data.set_index("date")[["close"]].sort_index().reindex(calendar).ffill().dropna(subset=["close"]).reset_index()
            reindexed["code"] = ts_code
            data = reindexed[["date", "code", "close"]]
        frames.append(data[["date", "code", "close"]])
    if not frames:
        raise ValueError("未从 Tushare 拉到任何价格数据。")
    return pd.concat(frames, ignore_index=True).sort_values(["date", "code"]).reset_index(drop=True)


def fetch_dividend_history_from_tushare(
    pro,
    *,
    stock_pool: list[str],
    start_date: str,
    end_date: str,
    cache: TushareDataCache | None = None,
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for ts_code in stock_pool:
        if cache is None:
            raw = _fetch_dividend_frame(pro, ts_code=ts_code, start_date=start_date, end_date=end_date)
        else:
            raw = load_cached_dataset_frame(
                cache=cache,
                dataset="dividend",
                canonical_key_parts=[ts_code],
                legacy_glob_patterns=legacy_cache_patterns(dataset="dividend", key_parts=[ts_code]),
                fallback_fetcher=lambda ts_code=ts_code: cache.load_or_fetch(
                    dataset="dividend",
                    key_parts=[ts_code, start_date, end_date],
                    fetcher=lambda: _fetch_dividend_frame(pro, ts_code=ts_code, start_date=start_date, end_date=end_date),
                ),
            )
            raw = filter_frame_by_date_range(raw, "ex_date", start_date, end_date)
        normalized = normalize_dividend(raw)
        normalized = normalized[(normalized["date"] >= pd.Timestamp(start_date)) & (normalized["date"] <= pd.Timestamp(end_date))]
        if normalized.empty:
            continue
        normalized["code"] = ts_code
        frames.append(normalized[["date", "code", "cash_div"]])
    if not frames:
        return pd.DataFrame(columns=["date", "code", "cash_div"])
    return pd.concat(frames, ignore_index=True).sort_values(["date", "code"]).reset_index(drop=True)


def build_rebalance_report(
    *,
    price_df: pd.DataFrame,
    signal_df: pd.DataFrame,
    backtest_result: BacktestResult,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    prices = price_df.copy()
    prices["date"] = pd.to_datetime(prices["date"])
    prices["code"] = prices["code"].astype(str)
    prices["close"] = pd.to_numeric(prices["close"], errors="coerce")
    prices = prices.dropna(subset=["date", "code", "close"])
    prices = prices.sort_values(["date", "code"]).set_index(["date", "code"])

    signals = signal_df.copy()
    signals["date"] = pd.to_datetime(signals["date"])
    signals["code"] = signals["code"].astype(str)
    signals["expected_return_3y"] = pd.to_numeric(signals["expected_return_3y"], errors="coerce")
    signals = signals.dropna(subset=["date", "code"]).sort_values(["date", "code"]).set_index(["date", "code"])

    portfolio = backtest_result.portfolio_history.copy()
    portfolio["date"] = pd.to_datetime(portfolio["date"])
    portfolio = portfolio.set_index("date")

    holdings = backtest_result.holdings_history.copy()
    holdings["date"] = pd.to_datetime(holdings["date"])

    detail_rows: list[dict[str, object]] = []
    summary_rows: list[dict[str, object]] = []
    previous_holdings: dict[str, float] = {}

    for date in backtest_result.rebalance_dates:
        date = pd.Timestamp(date)
        current_subset = holdings[holdings["date"] == date]
        if current_subset.empty:
            current_holdings = pd.DataFrame(columns=["shares", "close", "market_value", "weight", "expected_return_3y"])
            current_holdings.index = pd.Index([], name="code")
        else:
            current_holdings = current_subset.set_index("code")
        current_portfolio = portfolio.loc[date] if date in portfolio.index else None
        prev_portfolio = portfolio.loc[portfolio.index[portfolio.index < date].max()] if (portfolio.index < date).any() else None
        dividend_cash = float(current_portfolio["dividend_cash"]) if current_portfolio is not None and "dividend_cash" in current_portfolio else 0.0
        pre_equity = float(prev_portfolio["equity"]) + dividend_cash if prev_portfolio is not None else float(current_portfolio["equity"]) if current_portfolio is not None else 0.0
        post_equity = float(current_portfolio["equity"]) if current_portfolio is not None else pre_equity
        try:
            prices_today = prices.xs(date, level="date")
        except KeyError:
            prices_today = pd.DataFrame(columns=["close"])

        codes = sorted(set(previous_holdings) | set(current_holdings.index))
        for code in codes:
            pre_shares = float(previous_holdings.get(code, 0.0))
            post_shares = float(current_holdings.loc[code, "shares"]) if code in current_holdings.index else 0.0
            delta_shares = post_shares - pre_shares
            close = float(prices_today.loc[code, "close"]) if code in prices_today.index else None
            signal_value = None
            signal_reason = None
            signal_valid = None
            if (date, code) in signals.index:
                signal_row = signals.loc[(date, code)]
                if isinstance(signal_row, pd.DataFrame):
                    signal_row = signal_row.iloc[-1]
                signal_value = signal_row.get("expected_return_3y")
                signal_reason = signal_row.get("reason") if "reason" in signal_row else None
                signal_valid = signal_row.get("valid") if "valid" in signal_row else None
            pre_value = None if close is None else pre_shares * close
            post_value = None if close is None else post_shares * close
            delta_value = None if close is None else delta_shares * close
            detail_rows.append(
                {
                    "date": date,
                    "code": code,
                    "action": _classify_rebalance_action(pre_shares, post_shares),
                    "signal": signal_value,
                    "signal_reason": signal_reason,
                    "signal_valid": signal_valid,
                    "close": close,
                    "pre_shares": pre_shares,
                    "post_shares": post_shares,
                    "delta_shares": delta_shares,
                    "delta_value": delta_value,
                    "pre_value": pre_value,
                    "post_value": post_value,
                    "pre_weight": None if pre_value is None or pre_equity == 0 else pre_value / pre_equity,
                    "post_weight": None if post_value is None or post_equity == 0 else post_value / post_equity,
                }
            )

        changed_codes = 0
        for code in codes:
            pre_shares = float(previous_holdings.get(code, 0.0))
            post_shares = float(current_holdings.loc[code, "shares"]) if code in current_holdings.index else 0.0
            if abs(pre_shares - post_shares) > 1e-12:
                changed_codes += 1

        summary_rows.append(
            {
                "date": date,
                "equity_before": pre_equity,
                "equity_after": post_equity,
                "cash_after": float(current_portfolio["cash"]) if current_portfolio is not None else None,
                "positions_after": int(current_portfolio["positions"]) if current_portfolio is not None else None,
                "dividend_cash": dividend_cash,
                "changed_codes": changed_codes,
            }
        )
        previous_holdings = {code: float(row["shares"]) for code, row in current_holdings.iterrows()}

    detail_frame = pd.DataFrame(detail_rows).sort_values(["date", "action", "code"], ascending=[True, True, True]).reset_index(drop=True)
    summary_frame = pd.DataFrame(summary_rows).sort_values("date").reset_index(drop=True)
    return detail_frame, summary_frame


def build_signal_frame_from_tushare(
    pro,
    *,
    stock_pool: list[str],
    signal_dates: tuple[pd.Timestamp, ...],
    report_rc_start_date: str = "20100101",
    pe_history_years: int = 10,
    cache: TushareDataCache | None = None,
) -> pd.DataFrame:
    if not signal_dates:
        raise ValueError("signal_dates 为空。")

    earliest_signal = signal_dates[0].strftime("%Y%m%d")
    latest_signal = signal_dates[-1].strftime("%Y%m%d")
    pe_history_start = years_before(earliest_signal, pe_history_years)
    fina_start = years_before(earliest_signal, 5)

    records: list[dict[str, object]] = []
    for ts_code in stock_pool:
        daily_basic = fetch_daily_basic_history(pro, ts_code, pe_history_start, latest_signal, cache=cache)
        if daily_basic.empty:
            continue
        report_rc = fetch_report_rc_history(pro, ts_code, report_rc_start_date, latest_signal, cache=cache)
        fina_indicator = fetch_fina_indicator_history(pro, ts_code, fina_start, latest_signal, cache=cache)

        for signal_date in signal_dates:
            result = calculate_expected_return_from_prefetched(
                as_of=signal_date,
                daily_basic=daily_basic,
                report_rc=report_rc,
                fina_indicator=fina_indicator,
                pe_history_years=pe_history_years,
            )
            records.append(
                {
                    "date": signal_date,
                    "code": ts_code,
                    "expected_return_3y": result.expected_return_3y,
                    "valid": result.valid,
                    "reason": result.reason,
                    "current_pe": result.current_pe,
                    "target_pe": result.target_pe,
                    "g": result.g,
                    "growth_source": result.growth_source,
                }
            )

    if not records:
        raise ValueError("未生成任何策略信号。")
    return pd.DataFrame(records).sort_values(["date", "code"]).reset_index(drop=True)


def run_tushare_expected_return_backtest(
    pro=None,
    *,
    stock_pool: list[str],
    start_date: str,
    end_date: str,
    strategy_config: StrategyConfig | None = None,
    report_rc_start_date: str = "20100101",
    pe_history_years: int = 10,
    cache_dir: str | Path | None = None,
    cache_only: bool = True,
) -> TushareBacktestArtifacts:
    if pro is None and not cache_only:
        raise ValueError("cache_only=False 时必须提供 Tushare pro 客户端。")
    cache = TushareDataCache(Path(cache_dir), cache_only=cache_only) if cache_dir else None
    trading_dates = fetch_open_trade_dates_cached(pro, start_date=start_date, end_date=end_date, cache=cache)
    actual_start, rebalance_dates = resolve_strategy_dates(
        trading_dates=trading_dates,
        start_date=start_date,
        end_date=end_date,
        month_days=(strategy_config or StrategyConfig()).rebalance_month_days,
    )
    signal_dates = (actual_start, *rebalance_dates)
    price_df = fetch_price_history_from_tushare(
        pro,
        stock_pool=stock_pool,
        start_date=actual_start.strftime("%Y%m%d"),
        end_date=end_date,
        trading_dates=trading_dates,
        cache=cache,
    )
    dividend_df = fetch_dividend_history_from_tushare(
        pro,
        stock_pool=stock_pool,
        start_date=actual_start.strftime("%Y%m%d"),
        end_date=end_date,
        cache=cache,
    )
    signal_df = build_signal_frame_from_tushare(
        pro,
        stock_pool=stock_pool,
        signal_dates=signal_dates,
        report_rc_start_date=report_rc_start_date,
        pe_history_years=pe_history_years,
        cache=cache,
    )
    backtest_result = run_expected_return_strategy(
        price_df=price_df,
        signal_df=signal_df,
        start_date=actual_start.strftime("%Y-%m-%d"),
        end_date=end_date,
        stock_pool=stock_pool,
        config=strategy_config,
        dividend_df=dividend_df,
    )
    return TushareBacktestArtifacts(
        price_df=price_df,
        signal_df=signal_df,
        backtest_result=backtest_result,
        rebalance_dates=rebalance_dates,
    )


def prefetch_tushare_strategy_cache(
    pro,
    *,
    stock_pool: list[str],
    cache_dir: str | Path,
    end_date: str | None = None,
    report_rc_start_date: str = FULL_HISTORY_START_DATE,
    refresh_datasets: tuple[str, ...] = (),
) -> TushareCacheArtifacts:
    resolved_end_date = end_date or pd.Timestamp.now().strftime("%Y%m%d")
    cache_root = Path(cache_dir)
    cache = TushareDataCache(cache_root, cache_only=False)
    clear_selected_cache_files(cache_root, stock_pool=stock_pool, datasets=refresh_datasets)
    trading_dates = update_trade_cal_cache(
        pro,
        cache=cache,
        start_date=FULL_HISTORY_START_DATE,
        end_date=resolved_end_date,
    )
    for ts_code in stock_pool:
        update_daily_cache(pro, ts_code, cache=cache, start_date=FULL_HISTORY_START_DATE, end_date=resolved_end_date, trading_dates=trading_dates)
        update_daily_basic_cache(pro, ts_code, cache=cache, start_date=FULL_HISTORY_START_DATE, end_date=resolved_end_date, trading_dates=trading_dates)
        update_report_rc_cache(pro, ts_code, cache=cache, start_date=report_rc_start_date, end_date=resolved_end_date)
        update_fina_indicator_cache(pro, ts_code, cache=cache, start_date=FULL_HISTORY_START_DATE, end_date=resolved_end_date)
        update_dividend_cache(pro, ts_code, cache=cache, start_date=FULL_HISTORY_START_DATE, end_date=resolved_end_date)
    return TushareCacheArtifacts(trading_dates=trading_dates, cache_dir=cache_root)


def clear_tushare_cache_dir(cache_dir: str | Path) -> None:
    path = Path(cache_dir)
    if path.exists():
        for csv_file in path.rglob("*.csv"):
            csv_file.unlink()
    path.mkdir(parents=True, exist_ok=True)


def write_backtest_artifacts(
    artifacts: TushareBacktestArtifacts,
    *,
    output_dir: str | Path,
    cache_dir: str | Path | None = None,
    stock_name_map: dict[str, str] | None = None,
) -> BacktestOutputPaths:
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)

    portfolio_path = output_root / "portfolio_history.csv"
    trades_path = output_root / "trade_log.csv"
    holdings_path = output_root / "holdings_history.csv"
    signals_path = output_root / "signal_snapshot.csv"
    rebalance_path = output_root / "rebalance_report.csv"
    rebalance_summary_path = output_root / "rebalance_summary.csv"
    rebalance_plot_path = output_root / "rebalance_actions.png"
    stock_report_dir = output_root / "stock_reports"

    rebalance_report, rebalance_summary = build_rebalance_report(
        price_df=artifacts.price_df,
        signal_df=artifacts.signal_df,
        backtest_result=artifacts.backtest_result,
    )

    artifacts.backtest_result.portfolio_history.to_csv(portfolio_path, index=False)
    artifacts.backtest_result.trade_log.to_csv(trades_path, index=False)
    artifacts.backtest_result.holdings_history.to_csv(holdings_path, index=False)
    artifacts.signal_df.to_csv(signals_path, index=False)
    rebalance_report.to_csv(rebalance_path, index=False)
    rebalance_summary.to_csv(rebalance_summary_path, index=False)

    from backtest.plotting import plot_rebalance_actions
    from backtest.plotting import plot_stock_lifecycle_reports

    plot_rebalance_actions(rebalance_report, output=rebalance_plot_path)
    plot_stock_lifecycle_reports(
        artifacts.price_df,
        artifacts.backtest_result.trade_log,
        output_dir=stock_report_dir,
        cache_dir=cache_dir,
        stock_name_map=stock_name_map,
        stock_pool=artifacts.price_df["code"].drop_duplicates().tolist(),
    )

    return BacktestOutputPaths(
        portfolio_path=portfolio_path,
        trades_path=trades_path,
        holdings_path=holdings_path,
        signals_path=signals_path,
        rebalance_path=rebalance_path,
        rebalance_summary_path=rebalance_summary_path,
        rebalance_plot_path=rebalance_plot_path,
        stock_report_dir=stock_report_dir,
    )


def clear_selected_cache_files(
    cache_root: Path,
    *,
    stock_pool: list[str],
    datasets: tuple[str, ...],
) -> None:
    if not datasets:
        return

    normalized = {item.strip() for item in datasets if item and item.strip()}
    for dataset in normalized:
        if dataset == "trade_cal":
            path = cache_root / dataset / "full__is_open_1.csv"
            if path.exists():
                path.unlink()
            continue

        if dataset == "daily":
            suffix = ["close"]
        elif dataset == "daily_basic":
            suffix = ["pe_ttm"]
        elif dataset in {"report_rc", "fina_indicator", "dividend"}:
            suffix = []
        else:
            raise ValueError(f"不支持的 refresh dataset: {dataset}")

        for ts_code in stock_pool:
            file_name = "__".join(sanitize_cache_key_parts([ts_code, *suffix])) + ".csv"
            path = cache_root / dataset / file_name
            if path.exists():
                path.unlink()


def update_trade_cal_cache(
    pro,
    *,
    cache: TushareDataCache,
    start_date: str,
    end_date: str,
) -> tuple[pd.Timestamp, ...]:
    frame = update_incremental_cache(
        cache=cache,
        dataset="trade_cal",
        key_parts=["full", "is_open_1"],
        requested_start_date=start_date,
        requested_end_date=end_date,
        date_column="cal_date",
        fetcher=lambda fetch_start, fetch_end: pro.trade_cal(exchange="", start_date=fetch_start, end_date=fetch_end, is_open="1"),
        empty_columns=["cal_date", "is_open"],
        sort_columns=["cal_date"],
    )
    dates = pd.to_datetime(frame["cal_date"].astype(str), format="%Y%m%d", errors="coerce").dropna()
    if dates.empty:
        raise ValueError("交易日历为空。")
    return tuple(sorted(dates.tolist()))


def update_daily_cache(
    pro,
    ts_code: str,
    *,
    cache: TushareDataCache,
    start_date: str,
    end_date: str,
    trading_dates: tuple[pd.Timestamp, ...],
) -> pd.DataFrame:
    effective_end_date = resolve_trade_date_on_or_before(trading_dates, end_date)
    if effective_end_date is None:
        return pd.DataFrame(columns=["ts_code", "trade_date", "close"])
    return update_incremental_cache(
        cache=cache,
        dataset="daily",
        key_parts=[ts_code, "close"],
        requested_start_date=start_date,
        requested_end_date=effective_end_date,
        date_column="trade_date",
        fetcher=lambda fetch_start, fetch_end: pro.daily(ts_code=ts_code, start_date=fetch_start, end_date=fetch_end, fields="ts_code,trade_date,close"),
        empty_columns=["ts_code", "trade_date", "close"],
        sort_columns=["trade_date"],
    )


def update_daily_basic_cache(
    pro,
    ts_code: str,
    *,
    cache: TushareDataCache,
    start_date: str,
    end_date: str,
    trading_dates: tuple[pd.Timestamp, ...],
) -> pd.DataFrame:
    effective_end_date = resolve_trade_date_on_or_before(trading_dates, end_date)
    if effective_end_date is None:
        return pd.DataFrame(columns=["ts_code", "trade_date", "pe_ttm"])
    return update_incremental_cache(
        cache=cache,
        dataset="daily_basic",
        key_parts=[ts_code, "pe_ttm"],
        requested_start_date=start_date,
        requested_end_date=effective_end_date,
        date_column="trade_date",
        fetcher=lambda fetch_start, fetch_end: pro.daily_basic(ts_code=ts_code, start_date=fetch_start, end_date=fetch_end, fields="ts_code,trade_date,pe_ttm"),
        empty_columns=["ts_code", "trade_date", "pe_ttm"],
        sort_columns=["trade_date"],
    )


def update_report_rc_cache(
    pro,
    ts_code: str,
    *,
    cache: TushareDataCache,
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    return update_incremental_cache(
        cache=cache,
        dataset="report_rc",
        key_parts=[ts_code],
        requested_start_date=start_date,
        requested_end_date=end_date,
        date_column="report_date",
        fetcher=lambda fetch_start, fetch_end: fetch_report_rc_from_tushare(pro, ts_code=ts_code, start_date=fetch_start, end_date=fetch_end),
        empty_columns=["report_date", "quarter", "org_name", "eps"],
        sort_columns=["report_date", "quarter", "org_name"],
    )


def update_fina_indicator_cache(
    pro,
    ts_code: str,
    *,
    cache: TushareDataCache,
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    return update_incremental_cache(
        cache=cache,
        dataset="fina_indicator",
        key_parts=[ts_code],
        requested_start_date=start_date,
        requested_end_date=end_date,
        date_column="ann_date",
        fetcher=lambda fetch_start, fetch_end: pro.fina_indicator(ts_code=ts_code, start_date=fetch_start, end_date=fetch_end),
        empty_columns=["ann_date", "end_date", "eps"],
        sort_columns=["end_date", "ann_date"],
    )


def update_dividend_cache(
    pro,
    ts_code: str,
    *,
    cache: TushareDataCache,
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    return update_incremental_cache(
        cache=cache,
        dataset="dividend",
        key_parts=[ts_code],
        requested_start_date=start_date,
        requested_end_date=end_date,
        date_column="ex_date",
        fetcher=lambda fetch_start, fetch_end: _fetch_dividend_frame(
            pro,
            ts_code=ts_code,
            start_date=fetch_start,
            end_date=fetch_end,
        ),
        empty_columns=["ts_code", "ex_date", "cash_div", "cash_div_tax", "div_proc"],
        sort_columns=["ex_date"],
    )


def fetch_daily_basic_history(
    pro,
    ts_code: str,
    start_date: str,
    end_date: str,
    *,
    cache: TushareDataCache | None,
) -> pd.DataFrame:
    if cache is None:
        df = pro.daily_basic(ts_code=ts_code, start_date=start_date, end_date=end_date, fields="ts_code,trade_date,pe_ttm")
    else:
        df = load_cached_dataset_frame(
            cache=cache,
            dataset="daily_basic",
            canonical_key_parts=[ts_code, "pe_ttm"],
            legacy_glob_patterns=legacy_cache_patterns(dataset="daily_basic", key_parts=[ts_code, "pe_ttm"]),
            fallback_fetcher=lambda: cache.load_or_fetch(
                dataset="daily_basic",
                key_parts=[ts_code, start_date, end_date, "pe_ttm"],
                fetcher=lambda: pro.daily_basic(ts_code=ts_code, start_date=start_date, end_date=end_date, fields="ts_code,trade_date,pe_ttm"),
            ),
        )
        df = filter_frame_by_date_range(df, "trade_date", start_date, end_date)
    if df is None or df.empty:
        return pd.DataFrame(columns=["date", "pe_ttm"])
    return normalize_daily_basic(df)


def fetch_report_rc_history(
    pro,
    ts_code: str,
    start_date: str,
    end_date: str,
    *,
    cache: TushareDataCache | None,
) -> pd.DataFrame:
    if cache is None:
        df = fetch_report_rc_from_tushare(pro, ts_code=ts_code, start_date=start_date, end_date=end_date)
    else:
        df = load_cached_dataset_frame(
            cache=cache,
            dataset="report_rc",
            canonical_key_parts=[ts_code],
            legacy_glob_patterns=legacy_cache_patterns(dataset="report_rc", key_parts=[ts_code]),
            fallback_fetcher=lambda: cache.load_or_fetch(
                dataset="report_rc",
                key_parts=[ts_code, start_date, end_date],
                fetcher=lambda: fetch_report_rc_from_tushare(pro, ts_code=ts_code, start_date=start_date, end_date=end_date),
            ),
        )
        df = filter_frame_by_date_range(df, "report_date", start_date, end_date)
    if df is None or df.empty:
        return pd.DataFrame()
    return normalize_report_rc(df)


def fetch_fina_indicator_history(
    pro,
    ts_code: str,
    start_date: str,
    end_date: str,
    *,
    cache: TushareDataCache | None,
) -> pd.DataFrame:
    if cache is None:
        df = pro.fina_indicator(ts_code=ts_code, start_date=start_date, end_date=end_date)
    else:
        df = load_cached_dataset_frame(
            cache=cache,
            dataset="fina_indicator",
            canonical_key_parts=[ts_code],
            legacy_glob_patterns=legacy_cache_patterns(dataset="fina_indicator", key_parts=[ts_code]),
            fallback_fetcher=lambda: cache.load_or_fetch(
                dataset="fina_indicator",
                key_parts=[ts_code, start_date, end_date],
                fetcher=lambda: pro.fina_indicator(ts_code=ts_code, start_date=start_date, end_date=end_date),
            ),
        )
        df = filter_frame_by_date_range(df, "ann_date", start_date, end_date)
    if df is None or df.empty:
        return pd.DataFrame()
    return normalize_fina_indicator(df)


def normalize_dividend(data: pd.DataFrame) -> pd.DataFrame:
    if data is None or data.empty:
        return pd.DataFrame(columns=["date", "cash_div"])

    frame = data.copy()
    if "div_proc" in frame.columns:
        div_proc = frame["div_proc"].astype(str).fillna("")
        frame = frame[div_proc.str.contains("实施", na=False)]
    if "ex_date" not in frame.columns:
        return pd.DataFrame(columns=["date", "cash_div"])

    cash_column = "cash_div" if "cash_div" in frame.columns else "cash_div_tax" if "cash_div_tax" in frame.columns else None
    if cash_column is None:
        return pd.DataFrame(columns=["date", "cash_div"])

    frame["date"] = pd.to_datetime(frame["ex_date"], format="%Y%m%d", errors="coerce")
    frame["cash_div"] = pd.to_numeric(frame[cash_column], errors="coerce")
    frame = frame.dropna(subset=["date", "cash_div"])
    frame = frame[frame["cash_div"] != 0]
    if frame.empty:
        return pd.DataFrame(columns=["date", "cash_div"])
    return (
        frame.groupby("date", as_index=False)["cash_div"].sum()
        .sort_values("date")
        .reset_index(drop=True)
    )


def _fetch_dividend_frame(
    pro,
    *,
    ts_code: str,
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    if not hasattr(pro, "dividend"):
        return pd.DataFrame(columns=["ts_code", "ex_date", "cash_div", "cash_div_tax", "div_proc"])
    try:
        return pro.dividend(ts_code=ts_code, start_date=start_date, end_date=end_date)
    except TypeError:
        return pro.dividend(ts_code=ts_code)


def _classify_rebalance_action(pre_shares: float, post_shares: float) -> str:
    if abs(pre_shares) <= 1e-12 and abs(post_shares) <= 1e-12:
        return "HOLD"
    if abs(pre_shares) <= 1e-12 and post_shares > 0:
        return "BUY"
    if pre_shares > 0 and abs(post_shares) <= 1e-12:
        return "SELL"
    if post_shares > pre_shares:
        return "BUY"
    if post_shares < pre_shares:
        return "SELL"
    return "HOLD"


def calculate_expected_return_from_prefetched(
    *,
    as_of: pd.Timestamp,
    daily_basic: pd.DataFrame,
    report_rc: pd.DataFrame,
    fina_indicator: pd.DataFrame,
    pe_history_years: int,
):
    as_of_ts = pd.Timestamp(as_of)
    daily_as_of = daily_basic[daily_basic["date"] <= as_of_ts]
    if daily_as_of.empty:
        return calculate_expected_return_3y(current_pe=None, pe_history=[], growth=GrowthInputs())

    latest_row = daily_as_of.iloc[-1]
    current_pe = latest_row.get("pe_ttm")
    pe_window_start = as_of_ts - pd.DateOffset(years=pe_history_years)
    pe_history = daily_as_of.loc[daily_as_of["date"] >= pe_window_start, "pe_ttm"].dropna().tolist()

    base_quarter, base_eps = resolve_base_annual_eps(fina_indicator, as_of_ts)
    target_quarter = resolve_target_quarter(base_quarter)
    _, consensus_cagr_3y, _ = build_consensus_growth_from_report_rc(
        report_rc[report_rc["report_date"] <= as_of_ts],
        target_quarter=target_quarter,
        base_eps=base_eps,
    )

    return calculate_expected_return_3y(
        current_pe=current_pe,
        pe_history=pe_history,
        growth=GrowthInputs(future_3y_consensus_cagr=consensus_cagr_3y),
    )


def resolve_trade_date_on_or_before(
    trading_dates: tuple[pd.Timestamp, ...],
    target_date: str,
) -> str | None:
    if not trading_dates:
        return None
    target = pd.Timestamp(target_date)
    valid = [date for date in trading_dates if date <= target]
    if not valid:
        return None
    return valid[-1].strftime("%Y%m%d")


def resolve_next_trade_date(
    trading_dates: tuple[pd.Timestamp, ...],
    target: pd.Timestamp,
) -> pd.Timestamp | None:
    for date in trading_dates:
        if date >= target:
            return date
    return None


def years_before(date_str: str, years: int) -> str:
    dt = pd.Timestamp(date_str)
    return (dt - pd.DateOffset(years=years)).strftime("%Y%m%d")
