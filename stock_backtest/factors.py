"""
研究版回测因子计算与快照组装。
"""

from __future__ import annotations

from datetime import timedelta

import numpy as np
import pandas as pd

from stock_backtest import config as cfg


def pick_growth_value(row):
    for col in ("g_forward_3y", "net_profit_growth_3y_cagr", "net_profit_growth_2y_cagr", "net_profit_growth"):
        if col in row and pd.notna(row[col]):
            value = float(row[col])
            if value <= -1:
                return np.nan
            return min(value, cfg.STRATEGY.g_cap)
    return np.nan


def calc_peg(pe_ttm, growth):
    if pd.isna(pe_ttm) or pd.isna(growth) or growth <= 0:
        return np.nan
    return float(pe_ttm) / (float(growth) * 100.0)


def calc_percentile(values, current):
    if values.empty or pd.isna(current):
        return np.nan
    return float((values <= current).mean())


def valuation_window_start(as_of):
    return as_of - timedelta(days=cfg.STRATEGY.valuation_window_years * 366)


def build_valuation_metrics(hist, as_of):
    valuation_hist = hist[(hist["date"] >= valuation_window_start(as_of)) & (hist["pe_ttm"] > 0)]["pe_ttm"].dropna()
    valuation_obs = int(len(valuation_hist))
    if valuation_obs < cfg.STRATEGY.min_valuation_history_observations:
        return {
            "valuation_obs": valuation_obs,
            "pe_mean": np.nan,
            "pe_p80": np.nan,
            "pe_p95": np.nan,
            "pe_percentile": np.nan,
        }

    latest_pe = hist.iloc[-1]["pe_ttm"]
    return {
        "valuation_obs": valuation_obs,
        "pe_mean": float(valuation_hist.mean()),
        "pe_p80": float(valuation_hist.quantile(cfg.STRATEGY.pe_trim_quantile)),
        "pe_p95": float(valuation_hist.quantile(cfg.STRATEGY.pe_exit_quantile)),
        "pe_percentile": calc_percentile(valuation_hist, latest_pe),
    }


def calc_score(growth, peg, pe_percentile, roe):
    if pd.isna(growth) or pd.isna(peg) or pd.isna(pe_percentile) or pd.isna(roe):
        return np.nan
    return (
        growth * cfg.STRATEGY.score_g_weight
        - peg * cfg.STRATEGY.score_peg_weight
        - pe_percentile * cfg.STRATEGY.score_pe_percentile_weight
        + roe * 100.0 * cfg.STRATEGY.score_roe_weight
    )


def build_single_factor_row(hist, as_of, code):
    latest = hist.iloc[-1]
    valuation = build_valuation_metrics(hist, as_of)
    growth = pick_growth_value(latest)
    roe = latest.get("roe")
    roe = float(roe) if pd.notna(roe) else np.nan
    peg = calc_peg(latest.get("pe_ttm"), growth)
    score = calc_score(growth, peg, valuation["pe_percentile"], roe)
    is_st = bool(latest.get("is_st", False)) if "is_st" in latest else False

    return {
        "date": as_of,
        "code": code,
        "industry": latest.get("industry", cfg.UNIVERSE.stock_industry_map.get(code, "")),
        "pe_ttm": latest.get("pe_ttm"),
        "pb": latest.get("pb"),
        "roe": roe,
        "g": growth,
        "peg": peg,
        "pe_mean": valuation["pe_mean"],
        "pe_p80": valuation["pe_p80"],
        "pe_p95": valuation["pe_p95"],
        "pe_percentile": valuation["pe_percentile"],
        "score": score,
        "listing_date": latest.get("listing_date"),
        "is_st": is_st,
        "valuation_obs": valuation["valuation_obs"],
    }


def build_factor_snapshot(fundamentals, as_of, candidate_codes):
    if fundamentals.empty:
        raise ValueError("fundamentals 为空，无法生成研究版因子。")

    records = []
    for code in candidate_codes:
        hist = fundamentals[(fundamentals["code"] == code) & (fundamentals["date"] <= as_of)].copy()
        if hist.empty:
            continue
        hist = hist.sort_values("date")
        records.append(build_single_factor_row(hist, as_of, code))

    return pd.DataFrame(records).sort_values(["industry", "code"]).reset_index(drop=True)
