"""
回测脚本入口。

执行方式:
    python3 main.py
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

import config as cfg
from backtest import run_backtest
from data import fetch_benchmark, fetch_daily_quotes, fetch_dividends, fetch_trade_calendar
from metrics import annual_returns, compute_metrics, metrics_report
from plot import plot_annual_returns, plot_holdings_heatmap, plot_nav_and_drawdown

# ============================================================
# 回测入口参数
# 在这里统一修改策略、数据源和交易参数
# ============================================================

# 回测时间范围
START_DATE = "2018-06-30"
END_DATE = "2026-06-30"

# 数据源配置
TUSHARE_TOKEN = "AelZc4nygN5K6_YvBZBKnA3Jz1nne6kHBrLMvRnEeKA"
TUSHARE_PROXY_URL = "https://tu.brze.top"
CACHE_DIR = "cache"
CACHE_ENABLED = True
CACHE_FORCE_REFRESH = False
PRICE_ADJ = None

# 资金与仓位
INITIAL_CAPITAL = 5_000_000
TARGET_WEIGHT = 0.05
WEIGHT_TOLERANCE = 0.001

# 调仓与分红
REBALANCE_SCHEDULE = ["05-01", "08-01", "11-01", "02-01"]
DIVIDEND_MODE = "reinvest"

# 股票池
STOCK_POOL = [
    ("603288", "海天味业"),
    ("600529", "山东药玻"),
    ("600298", "安琪酵母"),
    ("600329", "达仁堂"),
    ("600332", "白云山"),
    ("600285", "羚锐制药"),
    ("002507", "涪陵榨菜"),
    ("600161", "天坛生物"),
    ("600085", "同仁堂"),
    ("600887", "伊利股份"),
    ("000538", "云南白药"),
    ("600809", "山西汾酒"),
    ("600305", "恒顺醋业"),
    ("601888", "中国中免"),
    ("001914", "招商积余"),
    ("000423", "东阿阿胶"),
    ("600600", "青岛啤酒"),
    ("002304", "洋河股份"),
    ("000568", "泸州老窖"),
    ("000858", "五粮液"),
]

# 交易成本
COMMISSION_RATE = 0.0001
COMMISSION_MIN = 0
STAMP_TAX_RATE = 0.0005
TRANSFER_FEE_RATE = 0.00001

# 指标参数
BENCHMARK_INDEX = "000300.SH"
RISK_FREE_RATE = 0.02


def _apply_runtime_config() -> None:
    """将 main.py 入口参数同步到全局配置模块。"""
    cfg.START_DATE = START_DATE
    cfg.END_DATE = END_DATE

    cfg.TUSHARE_TOKEN = TUSHARE_TOKEN
    cfg.TUSHARE_PROXY_URL = TUSHARE_PROXY_URL
    cfg.CACHE_DIR = CACHE_DIR
    cfg.CACHE_ENABLED = CACHE_ENABLED
    cfg.CACHE_FORCE_REFRESH = CACHE_FORCE_REFRESH
    cfg.PRICE_ADJ = PRICE_ADJ

    cfg.INITIAL_CAPITAL = INITIAL_CAPITAL
    cfg.TARGET_WEIGHT = TARGET_WEIGHT
    cfg.WEIGHT_TOLERANCE = WEIGHT_TOLERANCE

    cfg.REBALANCE_SCHEDULE = REBALANCE_SCHEDULE
    cfg.DIVIDEND_MODE = DIVIDEND_MODE

    cfg.STOCK_POOL = STOCK_POOL
    cfg.STOCK_CODES = [code for code, _ in STOCK_POOL]

    cfg.COMMISSION_RATE = COMMISSION_RATE
    cfg.COMMISSION_MIN = COMMISSION_MIN
    cfg.STAMP_TAX_RATE = STAMP_TAX_RATE
    cfg.TRANSFER_FEE_RATE = TRANSFER_FEE_RATE

    cfg.BENCHMARK_INDEX = BENCHMARK_INDEX
    cfg.RISK_FREE_RATE = RISK_FREE_RATE


def _make_output_dir() -> Path:
    """创建本次回测的输出目录。"""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path("output") / ts
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def _save_trade_records(output_dir: Path, trades: list) -> None:
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


def _save_rebalance_details(output_dir: Path, trades: list) -> None:
    """按调仓日汇总保存调仓明细。"""
    if not trades:
        pd.DataFrame(
            columns=[
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
        ).to_csv(output_dir / "rebalance_details.csv", index=False, encoding="utf-8-sig")
        return

    rows = []
    for t in trades:
        rows.append(
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
        )

    detail_df = pd.DataFrame(rows).sort_values(
        by=["rebalance_date", "action", "code"],
        ascending=[True, True, True],
    )
    detail_df.to_csv(output_dir / "rebalance_details.csv", index=False, encoding="utf-8-sig")

    summary_df = detail_df.groupby("rebalance_date", as_index=False).agg(
        trade_count=("code", "count"),
        buy_count=("action", lambda s: int((s == "BUY").sum())),
        sell_count=("action", lambda s: int((s == "SELL").sum())),
        buy_amount=(
            "amount",
            lambda s: float(
                detail_df.loc[s.index][detail_df.loc[s.index, "action"] == "BUY"]["amount"].sum()
            ),
        ),
        sell_amount=(
            "amount",
            lambda s: float(
                detail_df.loc[s.index][detail_df.loc[s.index, "action"] == "SELL"]["amount"].sum()
            ),
        ),
        total_fee=("total_fee", "sum"),
    )
    summary_df.to_csv(output_dir / "rebalance_summary.csv", index=False, encoding="utf-8-sig")


def _save_rebalance_weights(output_dir: Path, rebalance_weights: pd.DataFrame) -> None:
    """保存每次调仓前后的仓位占比与现金仓位。"""
    if rebalance_weights.empty:
        rebalance_weights.to_csv(
            output_dir / "rebalance_weights.csv", index=False, encoding="utf-8-sig"
        )
        return

    stock_name_map = dict(cfg.STOCK_POOL)
    rows = []
    weight_cols = [
        col for col in rebalance_weights.columns if col.endswith("_weight") and col != "cash_weight"
    ]
    for _, row in rebalance_weights.iterrows():
        base = {
            "rebalance_date": row["rebalance_date"],
            "phase": row["phase"],
            "total_value": row["total_value"],
            "cash": row["cash"],
            "cash_weight": row["cash_weight"],
            "code": "CASH",
            "name": "现金",
            "weight": row["cash_weight"],
        }
        rows.append(base)

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
                    "name": stock_name_map.get(code, code),
                    "weight": row[col],
                }
            )

    detail_df = pd.DataFrame(rows).sort_values(
        by=["rebalance_date", "phase", "code"],
        ascending=[True, True, True],
    )
    detail_df.to_csv(output_dir / "rebalance_weights.csv", index=False, encoding="utf-8-sig")


def main() -> None:
    _apply_runtime_config()

    print("开始获取回测数据...")
    quotes = fetch_daily_quotes(cfg.STOCK_CODES, cfg.START_DATE, cfg.END_DATE)
    dividends = fetch_dividends(cfg.STOCK_CODES)
    trade_dates = fetch_trade_calendar(cfg.START_DATE, cfg.END_DATE)
    benchmark = fetch_benchmark(cfg.BENCHMARK_INDEX, cfg.START_DATE, cfg.END_DATE)

    print("\n开始执行回测...")
    daily, trades, holdings, rebalance_weights = run_backtest(
        quotes, dividends, trade_dates, benchmark
    )

    print("\n开始计算指标...")
    metrics = compute_metrics(daily, trades)
    annual_df = annual_returns(daily)

    output_dir = _make_output_dir()
    daily.to_csv(output_dir / "daily_records.csv", index=False, encoding="utf-8-sig")
    holdings.to_csv(output_dir / "holdings.csv", index=False, encoding="utf-8-sig")
    rebalance_weights.to_csv(
        output_dir / "rebalance_weights_wide.csv", index=False, encoding="utf-8-sig"
    )
    annual_df.to_csv(output_dir / "annual_returns.csv", index=False, encoding="utf-8-sig")
    _save_trade_records(output_dir, trades)
    _save_rebalance_details(output_dir, trades)
    _save_rebalance_weights(output_dir, rebalance_weights)

    with open(output_dir / "metrics.txt", "w", encoding="utf-8") as f:
        f.write(metrics_report(metrics))

    fig_nav, fig_dd = plot_nav_and_drawdown(daily, trades)
    fig_nav.savefig(output_dir / "nav_curve.png", dpi=160, bbox_inches="tight")
    fig_dd.savefig(output_dir / "drawdown_curve.png", dpi=160, bbox_inches="tight")

    fig_annual = plot_annual_returns(annual_df)
    fig_annual.savefig(output_dir / "annual_returns.png", dpi=160, bbox_inches="tight")

    fig_holdings = plot_holdings_heatmap(holdings)
    fig_holdings.savefig(output_dir / "holdings_heatmap.png", dpi=160, bbox_inches="tight")

    print("\n回测完成。")
    print(f"分红模式: {cfg.DIVIDEND_MODE}")
    print(f"结果目录: {output_dir.resolve()}")
    print(metrics_report(metrics))


if __name__ == "__main__":
    main()
