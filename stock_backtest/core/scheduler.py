"""
交易日与调仓日调度
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import List, Optional, Set


def next_trade_date(target_date: date, trade_dates: Set[date], max_lookahead: int = 30) -> Optional[date]:
    for offset in range(max_lookahead):
        candidate = target_date + timedelta(days=offset)
        if candidate in trade_dates:
            return candidate
    return None


def generate_rebalance_dates(start: date, end: date, schedule: List[str], trade_dates: Set[date]) -> List[date]:
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
