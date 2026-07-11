"""
研究版回测策略规则、选股与目标权重生成。
"""

from __future__ import annotations

from collections import Counter

import pandas as pd

from stock_backtest import config as cfg


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
