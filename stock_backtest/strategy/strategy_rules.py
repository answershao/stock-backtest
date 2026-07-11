"""
策略规则判断
"""

from __future__ import annotations

from datetime import date
from typing import Optional

import pandas as pd

from stock_backtest.core import config as cfg


def listing_days(listing_date_value, as_of):
    if pd.isna(listing_date_value):
        return None
    listing_date = pd.to_datetime(listing_date_value).date()
    return (as_of - listing_date).days


def build_is_st_series(data):
    if "is_st" in data.columns:
        return data["is_st"].astype(bool)
    return pd.Series(False, index=data.index)


def apply_listing_days(data, as_of):
    result = data.copy()
    result["listing_days"] = result["listing_date"].apply(lambda value: listing_days(value, as_of))
    return result


def base_exclusion_rule(data):
    is_st = build_is_st_series(data)
    return (
        data["pe_ttm"].isna()
        | (data["pe_ttm"] <= 0)
        | data["roe"].isna()
        | data["industry"].isna()
        | data["industry"].astype(str).str.strip().eq("")
        | data["valuation_obs"].lt(cfg.STRATEGY.min_valuation_history_observations)
        | data["listing_days"].fillna(0).lt(cfg.STRATEGY.min_listing_days)
        | is_st
    )


def sell_rule(data):
    return (
        data["g"].isna()
        | (data["g"] < cfg.STRATEGY.g_sell_threshold)
        | data["pe_ttm"].isna()
        | ((~data["pe_p95"].isna()) & (data["pe_ttm"] >= data["pe_p95"]))
        | data["base_excluded"]
    )


def trim_rule(data):
    return (
        ~data["sell_flag"]
        & (
            ((~data["pe_p80"].isna()) & (data["pe_ttm"] >= data["pe_p80"]))
            | ((~data["peg"].isna()) & (data["peg"] >= cfg.STRATEGY.peg_trim_threshold))
        )
    )


def buy_rule(data):
    return (
        ~data["base_excluded"]
        & (data["g"] > cfg.STRATEGY.g_buy_threshold)
        & ((~data["peg"].isna()) & (data["peg"] < cfg.STRATEGY.peg_buy_threshold))
        & ((~data["pe_mean"].isna()) & (data["pe_ttm"] <= data["pe_mean"]))
        & (data["roe"] >= cfg.STRATEGY.roe_threshold)
    )


def build_signal_table(snapshot, as_of, current_codes):
    if snapshot.empty:
        return snapshot.copy()

    data = apply_listing_days(snapshot, as_of)
    data["base_excluded"] = base_exclusion_rule(data)
    data["sell_flag"] = sell_rule(data)
    data["trim_flag"] = trim_rule(data)
    data["buy_eligible"] = buy_rule(data)
    data["is_current"] = data["code"].isin(current_codes)
    return data.sort_values(["score", "code"], ascending=[False, True]).reset_index(drop=True)
