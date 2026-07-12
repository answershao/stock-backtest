from __future__ import annotations

from pathlib import Path
from typing import Union

import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.ticker import PercentFormatter
import pandas as pd

from backtest.data.tushare import ExpectedReturnTimeseriesRequest, build_expected_return_timeseries


def build_expected_return_frame(
    *,
    ts_code: str,
    start_date: str,
    end_date: str,
    cache_dir: Union[str, Path],
    pe_history_years: int = 10,
) -> pd.DataFrame:
    return build_expected_return_timeseries(
        ExpectedReturnTimeseriesRequest(
            ts_code=ts_code,
            start_date=start_date,
            end_date=end_date,
            cache_dir=cache_dir,
            pe_history_years=pe_history_years,
        )
    )


def configure_matplotlib_font() -> None:
    candidates = [
        "Microsoft YaHei",
        "SimHei",
        "Noto Sans SC",
        "WenQuanYi Zen Hei",
    ]
    available = {font.name for font in font_manager.fontManager.ttflist}
    for name in candidates:
        if name in available:
            plt.rcParams["font.family"] = name
            break
    plt.rcParams["axes.unicode_minus"] = False


def plot_expected_return_frame(frame: pd.DataFrame, *, ts_code: str, start_date: str, end_date: str, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    configure_matplotlib_font()
    fig, ax = plt.subplots(figsize=(14, 7))
    ax2 = ax.twinx()
    ax.plot(frame["date"], frame["mean_reversion_return_3y"], label="三年均值回归年化收益率", linewidth=2)
    ax.plot(frame["date"], frame["consensus_cagr_3y"], label="卖方三年 CAGR", linewidth=2)
    ax.plot(frame["date"], frame["expected_return_3y"], label="期望三年年化收益率", linewidth=2.4)
    ax2.plot(frame["date"], frame["close"], label="股价", color="#6b6b6b", linewidth=1.6, alpha=0.75)
    ax.set_title(f"{ts_code} {start_date}-{end_date} 逐日三年收益率")
    ax.set_xlabel("日期")
    ax.set_ylabel("收益率")
    ax2.set_ylabel("股价")
    ax.yaxis.set_major_formatter(PercentFormatter(xmax=1, decimals=0))
    ax.grid(True, linestyle="--", alpha=0.35)
    lines1, labels1 = ax.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax.legend(lines1 + lines2, labels1 + labels2, loc="upper left")
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(output, dpi=160)
    plt.close(fig)


def plot_portfolio_history(
    portfolio_history: pd.DataFrame,
    *,
    rebalance_dates: tuple[pd.Timestamp, ...] = (),
    output: Path,
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    configure_matplotlib_font()
    frame = portfolio_history.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    fig, ax = plt.subplots(figsize=(14, 7))
    ax.plot(frame["date"], frame["equity"], label="总资产", linewidth=2.4, color="#1f77b4")
    ax.plot(frame["date"], frame["cash"], label="现金", linewidth=1.4, color="#ff7f0e", alpha=0.8)

    for date in rebalance_dates:
        ax.axvline(date, color="#999999", linestyle="--", linewidth=0.9, alpha=0.45)
        row = frame[frame["date"] == pd.Timestamp(date)]
        if not row.empty:
            ax.scatter(row["date"], row["equity"], color="#d62728", s=28, zorder=5)

    ax.set_title("回测总金额变化")
    ax.set_xlabel("日期")
    ax.set_ylabel("金额")
    ax.grid(True, linestyle="--", alpha=0.3)
    ax.legend(loc="upper left")
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(output, dpi=160)
    plt.close(fig)


def plot_rebalance_actions(rebalance_report: pd.DataFrame, *, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    configure_matplotlib_font()
    frame = rebalance_report.copy()
    if frame.empty:
        frame = pd.DataFrame([{"date": pd.Timestamp("1970-01-01"), "action": "HOLD"}])
    frame["date"] = pd.to_datetime(frame["date"])
    counts = frame.groupby(["date", "action"]).size().unstack(fill_value=0).sort_index()
    action_order = [action for action in ["BUY", "SELL", "HOLD"] if action in counts.columns]
    colors = {"BUY": "#2ca02c", "SELL": "#d62728", "HOLD": "#7f7f7f"}

    fig, ax = plt.subplots(figsize=(14, 7))
    bottom = pd.Series(0, index=counts.index)
    for action in action_order:
        ax.bar(
            counts.index,
            counts[action],
            bottom=bottom,
            label=action,
            color=colors.get(action),
            width=6,
        )
        bottom = bottom + counts[action]

    ax.set_title("调仓日个股处理分布")
    ax.set_xlabel("日期")
    ax.set_ylabel("股票数量")
    ax.grid(True, axis="y", linestyle="--", alpha=0.3)
    ax.legend(loc="upper left")
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(output, dpi=160)
    plt.close(fig)


def build_stock_report(
    price_df: pd.DataFrame,
    trade_log: pd.DataFrame,
    *,
    stock_pool: list[str] | tuple[str, ...] | None = None,
) -> pd.DataFrame:
    prices = price_df.copy()
    prices["date"] = pd.to_datetime(prices["date"])
    prices["code"] = prices["code"].astype(str)
    prices["close"] = pd.to_numeric(prices["close"], errors="coerce")
    prices = prices.dropna(subset=["date", "code", "close"])

    trades = trade_log.copy()
    if trades.empty:
        return pd.DataFrame(columns=["code", "open_date", "close_date", "open_price", "close_price", "avg_cost", "realized_pnl", "unrealized_pnl", "holding_days", "status"])
    trades["date"] = pd.to_datetime(trades["date"])
    trades["code"] = trades["code"].astype(str)
    trades["shares"] = pd.to_numeric(trades["shares"], errors="coerce")
    trades["price"] = pd.to_numeric(trades["price"], errors="coerce")
    trades["signed_trade_value"] = pd.to_numeric(trades["signed_trade_value"], errors="coerce")
    trades = trades.dropna(subset=["date", "code", "shares", "price", "signed_trade_value"])

    if stock_pool is not None:
        allowed = {str(code) for code in stock_pool}
        trades = trades[trades["code"].isin(allowed)]

    rows: list[dict[str, object]] = []
    for code, group in trades.sort_values(["date", "code"]).groupby("code"):
        code_prices = prices[prices["code"] == code].sort_values("date")
        if code_prices.empty:
            continue

        open_date = None
        open_price = None
        avg_cost = 0.0
        shares = 0.0
        realized_pnl = 0.0
        intervals: list[dict[str, object]] = []

        for trade in group.sort_values("date").itertuples(index=False):
            trade_value = float(trade.signed_trade_value)
            qty = float(trade.shares)
            price = float(trade.price)
            if trade.action == "BUY":
                if abs(shares) <= 1e-12:
                    open_date = trade.date
                    open_price = price
                avg_cost = ((avg_cost * shares) + trade_value) / (shares + qty) if shares > 0 else price
                shares += qty
            else:
                sell_qty = qty
                if shares <= 0:
                    continue
                pnl = sell_qty * (price - avg_cost)
                realized_pnl += pnl
                shares -= sell_qty
                if shares <= 1e-12:
                    intervals.append(
                        {
                            "code": code,
                            "open_date": open_date,
                            "close_date": trade.date,
                            "open_price": open_price,
                            "close_price": price,
                            "avg_cost": avg_cost,
                            "realized_pnl": realized_pnl,
                            "holding_days": (pd.Timestamp(trade.date) - pd.Timestamp(open_date)).days if open_date is not None else None,
                            "status": "closed",
                        }
                    )
                    open_date = None
                    open_price = None
                    avg_cost = 0.0
                    shares = 0.0

        last_price = float(code_prices.iloc[-1]["close"])
        unrealized_pnl = 0.0 if shares <= 0 else shares * (last_price - avg_cost)
        if shares > 0 and open_date is not None:
            intervals.append(
                {
                    "code": code,
                    "open_date": open_date,
                    "close_date": None,
                    "open_price": open_price,
                    "close_price": None,
                    "avg_cost": avg_cost,
                    "realized_pnl": realized_pnl,
                    "holding_days": (code_prices.iloc[-1]["date"] - pd.Timestamp(open_date)).days,
                    "status": "open",
                    "unrealized_pnl": unrealized_pnl,
                }
            )

        for interval in intervals:
            rows.append(
                {
                    "code": code,
                    "open_date": interval.get("open_date"),
                    "close_date": interval.get("close_date"),
                    "open_price": interval.get("open_price"),
                    "close_price": interval.get("close_price"),
                    "avg_cost": interval.get("avg_cost"),
                    "realized_pnl": interval.get("realized_pnl"),
                    "unrealized_pnl": interval.get("unrealized_pnl", 0.0),
                    "holding_days": interval.get("holding_days"),
                    "status": interval.get("status"),
                    "last_price": last_price,
                    "trades": int(len(group)),
                }
            )

    return pd.DataFrame(rows).sort_values(["code", "open_date"]).reset_index(drop=True)


def plot_stock_lifecycle(
    price_df: pd.DataFrame,
    trade_log: pd.DataFrame,
    *,
    code: str,
    expected_return_frame: pd.DataFrame | None = None,
    holdings_value_frame: pd.DataFrame | None = None,
    stock_name: str | None = None,
    output: Path,
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    configure_matplotlib_font()

    prices = price_df.copy()
    prices["date"] = pd.to_datetime(prices["date"])
    prices["code"] = prices["code"].astype(str)
    prices["close"] = pd.to_numeric(prices["close"], errors="coerce")
    prices = prices[(prices["code"] == code) & prices["close"].notna()].sort_values("date")
    if prices.empty:
        return

    trades = trade_log.copy()
    trades["date"] = pd.to_datetime(trades["date"])
    trades["code"] = trades["code"].astype(str)
    trades["price"] = pd.to_numeric(trades["price"], errors="coerce")
    trades = trades[(trades["code"] == code) & trades["price"].notna()].sort_values("date")

    fig, ax = plt.subplots(figsize=(14, 7))
    ax2 = ax.twinx()
    ax.plot(prices["date"], prices["close"], color="#1f77b4", linewidth=1.8, label="收盘价")

    if expected_return_frame is not None and not expected_return_frame.empty:
        signal_frame = expected_return_frame.copy()
        signal_frame["date"] = pd.to_datetime(signal_frame["date"])
        ax2.plot(signal_frame["date"], signal_frame["mean_reversion_return_3y"], linewidth=1.4, color="#2ca02c", alpha=0.9, label="三年均值回归年化")
        ax2.plot(signal_frame["date"], signal_frame["consensus_cagr_3y"], linewidth=1.4, color="#9467bd", alpha=0.9, label="卖方三年 CAGR")
        ax2.plot(signal_frame["date"], signal_frame["expected_return_3y"], linewidth=1.8, color="#d62728", alpha=0.95, label="期望三年年化")

    if holdings_value_frame is not None and not holdings_value_frame.empty:
        holding_frame = holdings_value_frame.copy()
        holding_frame["date"] = pd.to_datetime(holding_frame["date"])
        ax.fill_between(
            holding_frame["date"],
            0,
            holding_frame["holding_value"],
            color="#ffbb78",
            alpha=0.18,
            label="持仓金额",
        )
        ax.plot(
            holding_frame["date"],
            holding_frame["holding_value"],
            color="#ff7f0e",
            linewidth=1.4,
            alpha=0.85,
            label="持仓金额",
        )

    buy_trades = trades[trades["action"] == "BUY"]
    sell_trades = trades[trades["action"] == "SELL"]
    if not buy_trades.empty:
        ax.scatter(buy_trades["date"], buy_trades["price"], marker="^", s=55, color="#2ca02c", label="买入")
    if not sell_trades.empty:
        ax.scatter(sell_trades["date"], sell_trades["price"], marker="v", s=55, color="#d62728", label="卖出")

    intervals = _build_holding_intervals_for_plot(trades)
    for start, end in intervals:
        ax.axvspan(start, end, color="#f0f0f0", alpha=0.45)

    report = build_stock_report(price_df, trade_log, stock_pool=[code])
    if not report.empty:
        latest = report.iloc[-1]
        display_name = f"{code} {stock_name}" if stock_name else code
        title = f"{display_name} | 成本 {round(float(latest['avg_cost']), 2)} | 实现盈亏 {round(float(latest['realized_pnl']), 2)}"
    else:
        title = f"{code} {stock_name}" if stock_name else code

    ax.set_title(title)
    ax.set_xlabel("日期")
    ax.set_ylabel("价格 / 持仓金额")
    ax2.set_ylabel("三年年化收益率")
    ax2.yaxis.set_major_formatter(PercentFormatter(xmax=1, decimals=0))
    ax.grid(True, linestyle="--", alpha=0.3)
    lines1, labels1 = ax.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax.legend(lines1 + lines2, labels1 + labels2, loc="upper left")
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(output, dpi=160)
    plt.close(fig)


def plot_stock_lifecycle_reports(
    price_df: pd.DataFrame,
    trade_log: pd.DataFrame,
    *,
    output_dir: Path,
    cache_dir: str | Path | None = None,
    stock_name_map: dict[str, str] | None = None,
    stock_pool: list[str] | tuple[str, ...] | None = None,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    report = build_stock_report(price_df, trade_log, stock_pool=stock_pool)
    if report.empty:
        return output_dir

    report_path = output_dir / "stock_report_summary.csv"
    report.to_csv(report_path, index=False)
    for code in report["code"].drop_duplicates().tolist():
        expected_return_frame = None
        if cache_dir is not None:
            code_prices = price_df[price_df["code"] == code].sort_values("date")
            if not code_prices.empty:
                expected_return_frame = build_expected_return_frame(
                    ts_code=code,
                    start_date=code_prices.iloc[0]["date"].strftime("%Y-%m-%d"),
                    end_date=code_prices.iloc[-1]["date"].strftime("%Y-%m-%d"),
                    cache_dir=cache_dir,
                )
        holdings_value_frame = build_daily_holding_value_frame(price_df, trade_log, code=code)
        plot_stock_lifecycle(
            price_df,
            trade_log,
            code=code,
            expected_return_frame=expected_return_frame,
            holdings_value_frame=holdings_value_frame,
            stock_name=(stock_name_map or {}).get(code),
            output=output_dir / f"{code}.png",
        )
    return output_dir


def _build_holding_intervals_for_plot(trade_log: pd.DataFrame) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    intervals: list[tuple[pd.Timestamp, pd.Timestamp]] = []
    open_date: pd.Timestamp | None = None
    shares = 0.0
    for trade in trade_log.sort_values("date").itertuples(index=False):
        qty = float(trade.shares)
        if trade.action == "BUY":
            if abs(shares) <= 1e-12:
                open_date = pd.Timestamp(trade.date)
            shares += qty
        elif trade.action == "SELL":
            shares -= qty
            if shares <= 1e-12 and open_date is not None:
                intervals.append((open_date, pd.Timestamp(trade.date)))
                open_date = None
                shares = 0.0
    return intervals


def build_daily_holding_value_frame(
    price_df: pd.DataFrame,
    trade_log: pd.DataFrame,
    *,
    code: str,
) -> pd.DataFrame:
    prices = price_df.copy()
    prices["date"] = pd.to_datetime(prices["date"])
    prices["code"] = prices["code"].astype(str)
    prices["close"] = pd.to_numeric(prices["close"], errors="coerce")
    prices = prices[(prices["code"] == code) & prices["close"].notna()].sort_values("date")
    if prices.empty:
        return pd.DataFrame(columns=["date", "holding_shares", "holding_value"])

    trades = trade_log.copy()
    trades["date"] = pd.to_datetime(trades["date"])
    trades["code"] = trades["code"].astype(str)
    trades["shares"] = pd.to_numeric(trades["shares"], errors="coerce")
    trades = trades[(trades["code"] == code) & trades["shares"].notna()].sort_values("date")

    share_changes: dict[pd.Timestamp, float] = {}
    for trade in trades.itertuples(index=False):
        signed_shares = float(trade.shares) if trade.action == "BUY" else -float(trade.shares)
        key = pd.Timestamp(trade.date)
        share_changes[key] = share_changes.get(key, 0.0) + signed_shares

    rows: list[dict[str, object]] = []
    shares = 0.0
    for row in prices.itertuples(index=False):
        date = pd.Timestamp(row.date)
        shares += share_changes.get(date, 0.0)
        rows.append(
            {
                "date": date,
                "holding_shares": shares,
                "holding_value": shares * float(row.close),
            }
        )
    return pd.DataFrame(rows)
