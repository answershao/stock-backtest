"""
数据字段映射与标准化
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd


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

    required = set(["date", "code", "pe_ttm", "roe", "industry", "net_profit_growth"])
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
