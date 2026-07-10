"""
回测脚本入口。

执行方式:
    python3 -m src.app
"""

from __future__ import annotations

from pathlib import Path

from .backtest import run_backtest
from .config import BacktestConfig
from .data import fetch_benchmark, fetch_daily_quotes, fetch_dividends, fetch_trade_calendar
from .metrics import annual_returns, compute_metrics, metrics_report
from .plot import plot_annual_returns, plot_holdings_heatmap, plot_nav_and_drawdown
from .reporting import (
    make_output_dir,
    save_rebalance_details,
    save_rebalance_weights,
    save_trade_records,
)

# 本项目所有常用可修改参数统一放在 main 入口，日常调整只需要改这里。
MAIN_STOCK_POOL: list[tuple[str, str]] = [
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

MAIN_RUNTIME_PARAMS = {
    "start_date": "2015-06-30",
    "end_date": "2026-06-30",
    "tushare_token": "AelZc4nygN5K6_YvBZBKnA3Jz1nne6kHBrLMvRnEeKA",
    "tushare_proxy_url": "https://tu.brze.top",
    "cache_dir": "cache",
    "cache_enabled": True,
    "cache_force_refresh": False,
    "price_adj": None,
    "initial_capital": 5_000_000,
    "target_weight": 0.05,
    "weight_tolerance": 0.001,
    "rebalance_schedule": ["05-01", "08-01", "11-01", "02-01"],
    "dividend_mode": "reinvest",
    "commission_rate": 0.0001,
    "commission_min": 0,
    "stamp_tax_rate": 0.0005,
    "transfer_fee_rate": 0.00001,
    "benchmark_index": "000300.SH",
    "risk_free_rate": 0.02,
}


def build_runtime_config() -> BacktestConfig:
    """根据 main 入口中的集中参数构建运行配置。"""
    return BacktestConfig(
        stock_pool=MAIN_STOCK_POOL,
        **MAIN_RUNTIME_PARAMS,
    )


def export_results(
    config: BacktestConfig,
    daily,
    trades,
    holdings,
    rebalance_weights,
    annual_df,
    metrics: dict,
    output_dir: Path,
) -> None:
    """落盘保存回测结果、报告和图表。"""
    daily.to_csv(output_dir / "daily_records.csv", index=False, encoding="utf-8-sig")
    holdings.to_csv(output_dir / "holdings.csv", index=False, encoding="utf-8-sig")
    rebalance_weights.to_csv(
        output_dir / "rebalance_weights_wide.csv",
        index=False,
        encoding="utf-8-sig",
    )
    annual_df.to_csv(
        output_dir / "annual_returns.csv",
        index=False,
        encoding="utf-8-sig",
    )
    save_trade_records(output_dir, trades)
    save_rebalance_details(output_dir, trades)
    save_rebalance_weights(config, output_dir, rebalance_weights)

    with open(output_dir / "metrics.txt", "w", encoding="utf-8") as f:
        f.write(metrics_report(config, metrics))
    fig_nav, fig_dd = plot_nav_and_drawdown(config, daily, trades)
    fig_nav.savefig(output_dir / "nav_curve.png", dpi=160, bbox_inches="tight")
    fig_dd.savefig(output_dir / "drawdown_curve.png", dpi=160, bbox_inches="tight")

    fig_annual = plot_annual_returns(annual_df)
    fig_annual.savefig(output_dir / "annual_returns.png", dpi=160, bbox_inches="tight")

    fig_holdings = plot_holdings_heatmap(config, holdings)
    fig_holdings.savefig(output_dir / "holdings_heatmap.png", dpi=160, bbox_inches="tight")


def main() -> None:
    config = build_runtime_config()

    print("开始获取回测数据...")
    quotes = fetch_daily_quotes(config, config.stock_codes, config.start_date, config.end_date)
    dividends = fetch_dividends(config, config.stock_codes)
    trade_dates = fetch_trade_calendar(config, config.start_date, config.end_date)
    benchmark = fetch_benchmark(
        config,
        config.benchmark_index,
        config.start_date,
        config.end_date,
    )

    print("\n开始执行回测...")
    daily, trades, holdings, rebalance_weights = run_backtest(
        config,
        quotes,
        dividends,
        trade_dates,
        benchmark,
    )

    print("\n开始计算指标...")
    metrics = compute_metrics(config, daily, trades)
    annual_df = annual_returns(config, daily)
    output_dir = make_output_dir()
    export_results(
        config,
        daily,
        trades,
        holdings,
        rebalance_weights,
        annual_df,
        metrics,
        output_dir,
    )

    print("\n回测完成。")
    print(f"分红模式: {config.dividend_mode}")
    print(f"结果目录: {output_dir.resolve()}")
    print(metrics_report(config, metrics))


if __name__ == "__main__":
    main()
