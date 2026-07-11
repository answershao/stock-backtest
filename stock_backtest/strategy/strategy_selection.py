"""
策略组合选择与目标仓位生成
"""

from __future__ import annotations

from collections import Counter

import pandas as pd

from stock_backtest.core import config as cfg


def industry_counts(selected_codes, snapshot):
    industry_map = snapshot.set_index("code")["industry"].to_dict()
    return Counter(industry_map.get(code, "") for code in selected_codes if industry_map.get(code, ""))


def can_add_to_portfolio(selected_codes, candidate_code, snapshot):
    industry_map = snapshot.set_index("code")["industry"].to_dict()
    candidate_industry = industry_map.get(candidate_code, "")
    if not candidate_industry:
        return False

    counts = industry_counts(selected_codes, snapshot)
    if counts[candidate_industry] >= cfg.STRATEGY.max_positions_per_industry:
        return False

    industries_after = set(ind for ind in counts if ind)
    industries_after.add(candidate_industry)
    if len(industries_after) > cfg.STRATEGY.max_industries:
        return False

    return True


def split_signal_groups(signal_table):
    current_full = signal_table[
        signal_table["is_current"] & ~signal_table["sell_flag"] & ~signal_table["trim_flag"]
    ].copy()
    trimmed = signal_table[
        signal_table["is_current"] & ~signal_table["sell_flag"] & signal_table["trim_flag"]
    ].copy()
    sells = signal_table[signal_table["is_current"] & signal_table["sell_flag"]].copy()
    new_candidates = signal_table[~signal_table["is_current"] & signal_table["buy_eligible"]].copy()
    return current_full, trimmed, sells, new_candidates


def select_full_position_codes(current_full, trimmed_codes):
    selected_full = current_full.sort_values(["score", "code"], ascending=[False, True])["code"].tolist()
    slots_left = max(cfg.STRATEGY.max_positions - len(trimmed_codes), 0)
    if len(selected_full) > slots_left:
        selected_full = selected_full[:slots_left]
    return selected_full


def apply_switch_rule(selected_full, trimmed_codes, available_new, signal_table):
    current_pool = signal_table.set_index("code")
    while available_new and selected_full:
        worst_code = min(
            selected_full,
            key=lambda code: current_pool.at[code, "score"] if pd.notna(current_pool.at[code, "score"]) else float("-inf"),
        )
        new_code = available_new[0]
        new_score = current_pool.at[new_code, "score"]
        old_score = current_pool.at[worst_code, "score"]
        if pd.isna(new_score) or pd.isna(old_score) or (new_score - old_score) < cfg.STRATEGY.switch_score_gap:
            break
        trial_codes = [code for code in selected_full if code != worst_code] + trimmed_codes
        if not can_add_to_portfolio(trial_codes, new_code, signal_table):
            available_new.pop(0)
            continue
        selected_full.remove(worst_code)
        selected_full.append(new_code)
        available_new.pop(0)
    return selected_full, available_new


def fill_new_positions(selected_full, trimmed_codes, available_new, signal_table):
    for new_code in available_new:
        if len(selected_full) + len(trimmed_codes) >= cfg.STRATEGY.max_positions:
            break
        trial_codes = selected_full + trimmed_codes
        if not can_add_to_portfolio(trial_codes, new_code, signal_table):
            continue
        selected_full.append(new_code)
    return selected_full


def build_target_weights(trimmed_codes, selected_full):
    target_weights = {}
    for code in trimmed_codes:
        target_weights[code] = min(
            cfg.STRATEGY.target_weight * cfg.STRATEGY.trim_position_ratio,
            cfg.STRATEGY.max_single_weight,
        )
    for code in selected_full:
        target_weights[code] = min(cfg.STRATEGY.target_weight, cfg.STRATEGY.max_single_weight)
    return target_weights


def build_rebalance_logs(as_of, sells, trimmed, signal_table, selected_full, target_weights):
    log_rows = []
    for _, row in sells.iterrows():
        log_rows.append(
            {
                "date": as_of,
                "code": row["code"],
                "action": "EXIT",
                "reason": "卖出信号",
                "before_weight": None,
                "after_weight": 0.0,
                "signal_value": row["score"],
            }
        )
    for _, row in trimmed.iterrows():
        log_rows.append(
            {
                "date": as_of,
                "code": row["code"],
                "action": "TRIM",
                "reason": "高估减仓",
                "before_weight": None,
                "after_weight": target_weights[row["code"]],
                "signal_value": row["score"],
            }
        )
    selected_set = set(selected_full)
    for _, row in signal_table.iterrows():
        if row["code"] in selected_set and not row["is_current"]:
            log_rows.append(
                {
                    "date": as_of,
                    "code": row["code"],
                    "action": "BUY",
                    "reason": "新开仓/换股补位",
                    "before_weight": 0.0,
                    "after_weight": target_weights[row["code"]],
                    "signal_value": row["score"],
                }
            )
    return pd.DataFrame(log_rows)
