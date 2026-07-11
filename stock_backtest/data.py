"""
数据获取、标准化与回测输入装配。
"""

from __future__ import annotations

import time
from datetime import date, timedelta
from pathlib import Path
from typing import Optional, Set

import pandas as pd

from stock_backtest import config as cfg
from stock_backtest.models import BacktestInputs, MarketContext


def as_ratio(series):
    numeric = pd.to_numeric(series, errors="coerce")
    mask = numeric.abs() > 1.5
    numeric.loc[mask] = numeric.loc[mask] / 100.0
    return numeric


def normalize_quote_frame(df):
    if df is None or df.empty:
        return pd.DataFrame()
    data = df.rename(columns={"trade_date": "date"}).copy()
    data["date"] = pd.to_datetime(data["date"]).dt.date
    return data.sort_values("date").reset_index(drop=True)


def normalize_dividend_frame(df):
    empty = pd.DataFrame(columns=["date", "cash_dividend", "bonus_ratio", "transfer_ratio"])
    if df is None or df.empty:
        return empty
    data = df.copy()
    if "div_proc" in data.columns:
        data = data[data["div_proc"].isin(["实施", "实施方案", "完成"])]
    if "ex_date" not in data.columns:
        return empty
    data["date"] = pd.to_datetime(data["ex_date"], errors="coerce").dt.date
    data["cash_dividend"] = pd.to_numeric(data.get("cash_div_tax"), errors="coerce").fillna(0.0)
    data["bonus_ratio"] = pd.to_numeric(data.get("stk_div"), errors="coerce").fillna(0.0)
    data["transfer_ratio"] = pd.to_numeric(data.get("stk_bo_rate"), errors="coerce").fillna(0.0)
    data = data.dropna(subset=["date"])
    return data[["date", "cash_dividend", "bonus_ratio", "transfer_ratio"]]


def normalize_trade_calendar(df):
    if df is None or df.empty:
        raise RuntimeError("交易日历获取失败")
    data = df.copy()
    data["cal_date"] = pd.to_datetime(data["cal_date"]).dt.date
    return set(data["cal_date"])


def normalize_benchmark_frame(df):
    if df is None or df.empty:
        return pd.DataFrame(columns=["date", "close"])
    data = df.rename(columns={"trade_date": "date"}).copy()
    data["date"] = pd.to_datetime(data["date"]).dt.date
    data = data.sort_values("date").reset_index(drop=True)
    return data[["date", "close"]]


def merge_research_fundamentals(daily_basic, fina, code, industry, listing_date):
    if daily_basic is None or daily_basic.empty:
        return pd.DataFrame()

    base = daily_basic.rename(columns={"trade_date": "date"}).copy()
    base["date"] = pd.to_datetime(base["date"])
    base = base.sort_values("date")

    if fina is not None and not fina.empty:
        fina_data = fina.rename(columns={"end_date": "date", "netprofit_yoy": "net_profit_growth"}).copy()
        fina_data["date"] = pd.to_datetime(fina_data["date"])
        fina_data = fina_data.sort_values("date")
        merged = pd.merge_asof(
            base,
            fina_data[["date", "roe", "net_profit_growth"]],
            on="date",
            direction="backward",
        )
    else:
        merged = base.copy()
        merged["roe"] = pd.NA
        merged["net_profit_growth"] = pd.NA

    merged["code"] = code
    merged["industry"] = industry
    merged["listing_date"] = listing_date
    merged["date"] = merged["date"].dt.date
    return merged[["date", "code", "pe_ttm", "pb", "roe", "industry", "net_profit_growth", "listing_date"]]


def standardize_fundamentals(df):
    rename_map = {
        "trade_date": "date",
        "datetime": "date",
        "ticker": "code",
        "symbol": "code",
        "证券代码": "code",
        "股票代码": "code",
        "pe": "pe_ttm",
        "PE_TTM": "pe_ttm",
        "pe_ttm_m": "pe_ttm",
        "pb_lf": "pb",
        "PB": "pb",
        "ROE": "roe",
        "industry_name": "industry",
        "申万一级行业": "industry",
        "净利润增速": "net_profit_growth",
        "profit_growth": "net_profit_growth",
        "g": "g_forward_3y",
        "growth_3y": "g_forward_3y",
        "forward_g": "g_forward_3y",
        "listingDate": "listing_date",
        "上市日期": "listing_date",
    }
    data = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns}).copy()

    required = {"date", "code", "pe_ttm", "roe", "industry", "net_profit_growth"}
    missing = required - set(data.columns)
    if missing:
        raise ValueError("基本面数据缺少必需字段: %s" % sorted(missing))

    data["date"] = pd.to_datetime(data["date"]).dt.date
    data["code"] = data["code"].astype(str).str.extract(r"(\d{6})", expand=False).fillna(data["code"].astype(str))

    for col in ("roe", "net_profit_growth", "g_forward_3y", "net_profit_growth_3y_cagr", "net_profit_growth_2y_cagr"):
        if col in data.columns:
            data[col] = as_ratio(data[col])

    for col in ("pe_ttm", "pb"):
        if col in data.columns:
            data[col] = pd.to_numeric(data[col], errors="coerce")

    if "listing_date" in data.columns:
        data["listing_date"] = pd.to_datetime(data["listing_date"], errors="coerce").dt.date

    if "is_st" in data.columns:
        data["is_st"] = data["is_st"].fillna(False).astype(bool)

    data["industry"] = data["industry"].astype(str).str.strip()
    return data.sort_values(["code", "date"]).reset_index(drop=True)


def load_fundamentals_csv_frame(path):
    csv_path = Path(path)
    if not csv_path.exists():
        raise FileNotFoundError(
            "未找到基本面数据文件: %s. 请准备包含 date/code/pe_ttm/roe/industry/net_profit_growth 的 CSV。"
            % csv_path
        )
    df = pd.read_csv(csv_path)
    if df.empty:
        raise ValueError("基本面数据为空: %s" % csv_path)
    return df


def require_tushare():
    try:
        import tushare as ts
        from tushare.pro import client as ts_client
    except ImportError as exc:
        raise ImportError("未安装 tushare。请先执行: pip install tushare") from exc

    ts_client.DataApi._DataApi__http_url = cfg.DATA_SOURCE.tushare_http_url
    pro = ts.pro_api(cfg.DATA_SOURCE.tushare_token)
    return ts, pro


def throttle():
    time.sleep(cfg.DATA_SOURCE.tushare_rate_limit_seconds)


def to_ts_code(code, asset="E"):
    code = str(code).strip()
    if code.endswith((".SH", ".SZ")):
        return code.upper()
    if asset == "I":
        suffix = ".SZ" if code.startswith(("000", "399", "980")) else ".SH"
        return "%s%s" % (code, suffix)
    suffix = ".SH" if code.startswith(("5", "6", "9")) else ".SZ"
    return "%s%s" % (code, suffix)


def date_to_ts(value):
    return value.replace("-", "")


def fetch_trade_calendar_raw(start, end):
    _, pro = require_tushare()
    df = pro.trade_cal(exchange="", start_date=date_to_ts(start), end_date=date_to_ts(end), is_open="1")
    throttle()
    return df


def fetch_daily_quotes_raw(symbols, start, end):
    ts, pro = require_tushare()
    result = {}
    start_fmt = date_to_ts(start)
    end_fmt = date_to_ts(end)
    for code in symbols:
        df = ts.pro_bar(
            api=pro,
            ts_code=to_ts_code(code),
            adj="hfq",
            asset="E",
            start_date=start_fmt,
            end_date=end_fmt,
        )
        throttle()
        result[code] = df
    return result


def fetch_dividends_raw(symbols):
    _, pro = require_tushare()
    result = {}
    for code in symbols:
        df = pro.dividend(ts_code=to_ts_code(code))
        throttle()
        result[code] = df
    return result


def fetch_benchmark_raw(index_code, start, end):
    ts, pro = require_tushare()
    ts_code = to_ts_code(index_code, asset="I")
    df = pro.index_daily(ts_code=ts_code, start_date=date_to_ts(start), end_date=date_to_ts(end))
    throttle()
    if df is None or df.empty:
        df = ts.pro_bar(api=pro, ts_code=ts_code, asset="I", start_date=date_to_ts(start), end_date=date_to_ts(end))
        throttle()
    return df


def fetch_stock_basic_raw():
    _, pro = require_tushare()
    df = pro.stock_basic(exchange="", list_status="L", fields="ts_code,symbol,name,industry,list_date")
    throttle()
    return df


def fetch_daily_basic_raw(code, start, end):
    _, pro = require_tushare()
    df = pro.daily_basic(
        ts_code=to_ts_code(code),
        start_date=date_to_ts(start),
        end_date=date_to_ts(end),
        fields="ts_code,trade_date,pe_ttm,pb",
    )
    throttle()
    return df


def fetch_fina_indicator_raw(code, start, end):
    _, pro = require_tushare()
    df = pro.fina_indicator(
        ts_code=to_ts_code(code),
        start_date=date_to_ts(start),
        end_date=date_to_ts(end),
        fields="ts_code,end_date,roe,netprofit_yoy",
    )
    throttle()
    return df


def fetch_daily_quotes(symbols, start, end):
    raw_result = fetch_daily_quotes_raw(symbols, start, end)
    result = {}
    for code, raw_df in raw_result.items():
        try:
            df = normalize_quote_frame(raw_df)
            if df.empty:
                print("  %s 无日线数据，跳过" % code)
                continue
            result[code] = df
            print("  %s 日线数据获取完成 (%s 条)" % (code, len(df)))
        except Exception as exc:
            print("  %s 日线数据获取失败: %s" % (code, exc))
    return result


def fetch_dividends(symbols):
    raw_result = fetch_dividends_raw(symbols)
    result = {}
    empty = pd.DataFrame(columns=["date", "cash_dividend", "bonus_ratio", "transfer_ratio"])
    for code, raw_df in raw_result.items():
        try:
            df = normalize_dividend_frame(raw_df)
            result[code] = df if not df.empty else empty.copy()
            print("  %s 分红数据获取完成 (%s 条)" % (code, len(result[code])))
        except Exception as exc:
            print("  %s 分红数据获取失败: %s，默认为无分红" % (code, exc))
            result[code] = empty.copy()
    return result


def fetch_trade_calendar(start, end):
    trade_dates = normalize_trade_calendar(fetch_trade_calendar_raw(start, end))
    print("  交易日历获取完成 (%s 个交易日)" % len(trade_dates))
    return trade_dates


def fetch_benchmark(index_code, start, end):
    try:
        df = normalize_benchmark_frame(fetch_benchmark_raw(index_code, start, end))
        print("  基准指数 %s 获取完成 (%s 条)" % (index_code, len(df)))
        return df
    except Exception as exc:
        print("  基准指数获取失败: %s，将跳过基准对比" % exc)
        return pd.DataFrame(columns=["date", "close"])


def fetch_research_fundamentals(symbols, start, end):
    stock_basic = fetch_stock_basic_raw()
    if stock_basic is None or stock_basic.empty:
        raise RuntimeError("stock_basic 获取失败")

    stock_basic = stock_basic.copy()
    stock_basic["code"] = stock_basic["symbol"].astype(str)
    stock_basic["listing_date"] = pd.to_datetime(stock_basic["list_date"], errors="coerce").dt.date
    stock_basic = stock_basic[stock_basic["code"].isin(symbols)].copy()

    frames = []
    for code in symbols:
        try:
            daily_basic = fetch_daily_basic_raw(code, start, end)
            fina = fetch_fina_indicator_raw(code, start, end)
            meta = stock_basic[stock_basic["code"] == code]
            if meta.empty:
                continue

            merged = merge_research_fundamentals(
                daily_basic=daily_basic,
                fina=fina,
                code=code,
                industry=meta["industry"].iloc[0],
                listing_date=meta["listing_date"].iloc[0],
            )
            if merged.empty:
                continue
            frames.append(merged)
            print("  %s 基本面数据获取完成 (%s 条)" % (code, len(merged)))
        except Exception as exc:
            print("  %s 基本面数据获取失败: %s" % (code, exc))

    if not frames:
        raise RuntimeError("未获取到任何研究版基本面数据")
    return standardize_fundamentals(pd.concat(frames, ignore_index=True))


def load_fundamentals_csv(path):
    return standardize_fundamentals(load_fundamentals_csv_frame(Path(path)))


def next_trade_date(target_date: date, trade_dates: Set[date], max_lookahead: int = 30) -> Optional[date]:
    for offset in range(max_lookahead):
        candidate = target_date + timedelta(days=offset)
        if candidate in trade_dates:
            return candidate
    return None


def generate_rebalance_dates(start: date, end: date, schedule: list[str], trade_dates: Set[date]) -> list[date]:
    theoretical_dates = []
    for year in range(start.year, end.year + 1):
        for mmdd in schedule:
            month, day = mmdd.split("-")
            theoretical_dates.append(date(year, int(month), int(day)))

    actual_dates = []
    for theoretical_date in sorted(d for d in theoretical_dates if start <= d <= end):
        actual_date = next_trade_date(theoretical_date, trade_dates)
        if actual_date is not None and actual_date <= end:
            actual_dates.append(actual_date)
    return actual_dates


def load_fundamentals_for_mode() -> Optional[pd.DataFrame]:
    if cfg.SYSTEM.strategy_mode != "research_quant":
        return None

    csv_path = Path(cfg.DATA_SOURCE.fundamental_data_path)
    if csv_path.exists():
        print(f"使用本地基本面文件: {csv_path}")
        return load_fundamentals_csv(csv_path)

    print("本地基本面文件不存在，改为从 Tushare 拉取研究版基本面数据")
    return fetch_research_fundamentals(cfg.UNIVERSE.stock_codes, cfg.BACKTEST.start_date, cfg.BACKTEST.end_date)


def load_backtest_inputs() -> BacktestInputs:
    print("开始获取交易日历...")
    trade_dates = fetch_trade_calendar(cfg.BACKTEST.start_date, cfg.BACKTEST.end_date)

    print("开始获取股票行情...")
    quotes = fetch_daily_quotes(cfg.UNIVERSE.stock_codes, cfg.BACKTEST.start_date, cfg.BACKTEST.end_date)

    print("开始获取分红数据...")
    dividends = fetch_dividends(cfg.UNIVERSE.stock_codes)

    print("开始获取基准指数...")
    benchmark = fetch_benchmark(cfg.BACKTEST.benchmark_index, cfg.BACKTEST.start_date, cfg.BACKTEST.end_date)

    print("开始获取/加载基本面数据...")
    fundamentals = load_fundamentals_for_mode()

    return BacktestInputs(
        quotes=quotes,
        dividends=dividends,
        trade_dates=trade_dates,
        benchmark_df=benchmark,
        fundamentals=fundamentals,
    )


def resolve_candidate_codes(quotes: dict, fundamentals: Optional[pd.DataFrame]) -> list:
    if cfg.UNIVERSE.candidate_pool_mode == "whitelist":
        return list(cfg.UNIVERSE.stock_codes)
    if cfg.UNIVERSE.candidate_pool_mode == "all_quotes":
        return sorted(quotes.keys())
    if fundamentals is not None and not fundamentals.empty:
        return sorted(fundamentals["code"].dropna().astype(str).unique().tolist())
    return list(cfg.UNIVERSE.stock_codes)


def build_dividend_map(dividends: dict) -> dict:
    result = {}
    for code, df in dividends.items():
        event_map = {}
        if df is None or df.empty:
            result[code] = event_map
            continue
        for _, row in df.iterrows():
            trade_date = row["date"]
            if isinstance(trade_date, pd.Timestamp):
                trade_date = trade_date.date()
            event_map[trade_date] = (
                float(row.get("cash_dividend", 0.0) or 0.0),
                float(row.get("bonus_ratio", 0.0) or 0.0),
                float(row.get("transfer_ratio", 0.0) or 0.0),
            )
        result[code] = event_map
    return result


def build_price_index(quotes: dict) -> dict:
    return {code: dict(zip(df["date"], df["close"])) for code, df in quotes.items()}


def build_benchmark_map(benchmark_df: pd.DataFrame) -> dict:
    if benchmark_df is None or benchmark_df.empty:
        return {}
    return dict(zip(benchmark_df["date"], benchmark_df["close"]))


def build_market_context(inputs: BacktestInputs) -> MarketContext:
    start = date.fromisoformat(cfg.BACKTEST.start_date)
    end = date.fromisoformat(cfg.BACKTEST.end_date)
    candidate_codes = resolve_candidate_codes(inputs.quotes, inputs.fundamentals)
    sorted_trade_dates = sorted(d for d in inputs.trade_dates if start <= d <= end)
    if not sorted_trade_dates:
        raise RuntimeError("回测区间内无交易日数据")

    return MarketContext(
        start=start,
        end=end,
        candidate_codes=candidate_codes,
        stock_names=dict(cfg.UNIVERSE.stock_name_map),
        price_index=build_price_index(inputs.quotes),
        dividend_map=build_dividend_map(inputs.dividends),
        benchmark_map=build_benchmark_map(inputs.benchmark_df),
        sorted_trade_dates=sorted_trade_dates,
        rebalance_dates=generate_rebalance_dates(start, end, cfg.BACKTEST.rebalance_schedule, inputs.trade_dates),
    )
