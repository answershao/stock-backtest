"""
研究版回测因子门面模块
"""

from __future__ import annotations

from stock_backtest.factors.factor_snapshot import build_factor_snapshot_frame


def build_factor_snapshot(fundamentals, as_of, candidate_codes):
    return build_factor_snapshot_frame(fundamentals, as_of, candidate_codes)
