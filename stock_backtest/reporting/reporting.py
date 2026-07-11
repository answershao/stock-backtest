"""
结果导出模块
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from stock_backtest.core.models import BacktestResult


def export_backtest_result(result: BacktestResult, output_dir: Path) -> None:
    output_dir.mkdir(exist_ok=True)
    result.daily.to_csv(output_dir / "daily.csv", index=False)
    result.holdings.to_csv(output_dir / "holdings.csv", index=False)
    result.rebalance_logs.to_csv(output_dir / "rebalance_logs.csv", index=False)

    trade_rows = [
        {
            "date": trade.date,
            "code": trade.code,
            "name": trade.name,
            "action": trade.action,
            "price": trade.price,
            "shares": trade.shares,
            "amount": trade.amount,
            "commission": trade.commission,
            "stamp_tax": trade.stamp_tax,
            "transfer_fee": trade.transfer_fee,
            "reason": trade.reason,
        }
        for trade in result.trades
    ]
    pd.DataFrame(trade_rows).to_csv(output_dir / "trades.csv", index=False)
