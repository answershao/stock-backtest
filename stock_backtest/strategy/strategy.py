"""
研究版回测策略门面模块
"""

from __future__ import annotations

import pandas as pd

from stock_backtest.strategy.strategy_rules import build_signal_table
from stock_backtest.strategy.strategy_selection import (
    apply_switch_rule,
    build_rebalance_logs,
    build_target_weights,
    fill_new_positions,
    select_full_position_codes,
    split_signal_groups,
)


def prepare_signal_table(snapshot, as_of, current_codes):
    return build_signal_table(snapshot, as_of, current_codes)


def generate_target_weights(snapshot, as_of, current_codes):
    signal_table = prepare_signal_table(snapshot, as_of, current_codes)
    if signal_table.empty:
        return {}, signal_table, pd.DataFrame(
            columns=["date", "code", "action", "reason", "before_weight", "after_weight", "signal_value"]
        )

    current_full, trimmed, sells, new_candidates = split_signal_groups(signal_table)
    trimmed_codes = trimmed.sort_values(["score", "code"], ascending=[False, True])["code"].tolist()
    selected_full = select_full_position_codes(current_full, trimmed_codes)
    available_new = new_candidates.sort_values(["score", "code"], ascending=[False, True])["code"].tolist()

    selected_full, available_new = apply_switch_rule(selected_full, trimmed_codes, available_new, signal_table)
    selected_full = fill_new_positions(selected_full, trimmed_codes, available_new, signal_table)

    target_weights = build_target_weights(trimmed_codes, selected_full)
    rebalance_logs = build_rebalance_logs(as_of, sells, trimmed, signal_table, selected_full, target_weights)
    return target_weights, signal_table, rebalance_logs
