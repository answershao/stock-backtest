"""
回测结果导出模块。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from config import BacktestConfig


def make_output_dir() -> Path:
    """创建本次回测的输出目录。"""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path("output") / ts
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def save_trade_records(output_dir: Path, trades: list) -> None:
    """保存交易明细。"""
    trade_rows = [
        {
            "date": t.date,
            "code": t.code,
            "name": t.name,
            "action": t.action,
            "price": t.price,
            "shares": t.shares,
            "amount": t.amount,
            "commission": t.commission,
            "stamp_tax": t.stamp_tax,
            "transfer_fee": t.transfer_fee,
            "reason": t.reason,
        }
        for t in trades
    ]
    pd.DataFrame(trade_rows).to_csv(output_dir / "trades.csv", index=False, encoding="utf-8-sig")


def save_rebalance_details(output_dir: Path, trades: list) -> None:
    """按调仓日汇总保存调仓明细。"""
    columns = [
        "rebalance_date",
        "action",
        "code",
        "name",
        "price",
        "shares",
        "amount",
        "commission",
        "stamp_tax",
        "transfer_fee",
        "total_fee",
        "reason",
    ]
    if not trades:
        pd.DataFrame(columns=columns).to_csv(
            output_dir / "rebalance_details.csv",
            index=False,
            encoding="utf-8-sig",
        )
        return

    detail_df = pd.DataFrame(
        [
            {
                "rebalance_date": t.date,
                "action": t.action,
                "code": t.code,
                "name": t.name,
                "price": t.price,
                "shares": t.shares,
                "amount": t.amount,
                "commission": t.commission,
                "stamp_tax": t.stamp_tax,
                "transfer_fee": t.transfer_fee,
                "total_fee": t.commission + t.stamp_tax + t.transfer_fee,
                "reason": t.reason,
            }
            for t in trades
        ]
    ).sort_values(by=["rebalance_date", "action", "code"], ascending=[True, True, True])
    detail_df.to_csv(output_dir / "rebalance_details.csv", index=False, encoding="utf-8-sig")

    grouped = detail_df.groupby(["rebalance_date", "action"], as_index=False)["amount"].sum()
    grouped = grouped.pivot(index="rebalance_date", columns="action", values="amount").fillna(0.0)
    grouped.columns = [str(col).lower() + "_amount" for col in grouped.columns]
    grouped = grouped.reset_index()

    counts = detail_df.groupby("rebalance_date", as_index=False).agg(
        trade_count=("code", "count"),
        buy_count=("action", lambda s: int((s == "BUY").sum())),
        sell_count=("action", lambda s: int((s == "SELL").sum())),
        total_fee=("total_fee", "sum"),
    )
    summary_df = counts.merge(grouped, on="rebalance_date", how="left")
    for col in ["buy_amount", "sell_amount"]:
        if col not in summary_df.columns:
            summary_df[col] = 0.0
    summary_df.to_csv(output_dir / "rebalance_summary.csv", index=False, encoding="utf-8-sig")


def save_rebalance_weights(
    config: BacktestConfig,
    output_dir: Path,
    rebalance_weights: pd.DataFrame,
) -> None:
    """保存每次调仓前后的仓位占比与现金仓位。"""
    if rebalance_weights.empty:
        rebalance_weights.to_csv(
            output_dir / "rebalance_weights.csv",
            index=False,
            encoding="utf-8-sig",
        )
        return

    rows = []
    weight_cols = [
        col for col in rebalance_weights.columns if col.endswith("_weight") and col != "cash_weight"
    ]
    for _, row in rebalance_weights.iterrows():
        rows.append(
            {
                "rebalance_date": row["rebalance_date"],
                "phase": row["phase"],
                "total_value": row["total_value"],
                "cash": row["cash"],
                "cash_weight": row["cash_weight"],
                "code": "CASH",
                "name": "现金",
                "weight": row["cash_weight"],
            }
        )
        for col in weight_cols:
            code = col.removesuffix("_weight")
            rows.append(
                {
                    "rebalance_date": row["rebalance_date"],
                    "phase": row["phase"],
                    "total_value": row["total_value"],
                    "cash": row["cash"],
                    "cash_weight": row["cash_weight"],
                    "code": code,
                    "name": config.stock_name_map.get(code, code),
                    "weight": row[col],
                }
            )

    pd.DataFrame(rows).sort_values(
        by=["rebalance_date", "phase", "code"],
        ascending=[True, True, True],
    ).to_csv(output_dir / "rebalance_weights.csv", index=False, encoding="utf-8-sig")
