from __future__ import annotations

from pathlib import Path
from typing import Union

import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.ticker import PercentFormatter
import pandas as pd

from src.data.tushare import ExpectedReturnTimeseriesRequest, build_expected_return_timeseries


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


def configure_matplotlib_font() -> bool:
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
            plt.rcParams["axes.unicode_minus"] = False
            return True
    plt.rcParams["axes.unicode_minus"] = False
    return False


def plot_expected_return_frame(
    frame: pd.DataFrame,
    *,
    ts_code: str,
    stock_name: str | None = None,
    start_date: str,
    end_date: str,
    output: Path,
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    has_cjk_font = configure_matplotlib_font()
    labels = _chart_labels(has_cjk_font=has_cjk_font)
    fig, ax = plt.subplots(figsize=(14, 7))
    ax2 = ax.twinx()
    ax.plot(frame["date"], frame["mean_reversion_return_3y"], label=labels["mean_reversion"], linewidth=2)
    ax.plot(frame["date"], frame["consensus_cagr_3y"], label=labels["consensus_cagr"], linewidth=2)
    ax.plot(frame["date"], frame["expected_return_3y"], label=labels["expected_return"], linewidth=2.4)
    ax2.plot(frame["date"], frame["close"], label=labels["close"], color="#6b6b6b", linewidth=1.6, alpha=0.75)
    display_name = _format_stock_display_name(ts_code=ts_code, stock_name=stock_name)
    ax.set_title(labels["title"].format(stock=display_name, start_date=start_date, end_date=end_date))
    ax.set_xlabel(labels["x"])
    ax.set_ylabel(labels["y"])
    ax2.set_ylabel(labels["close"])
    ax.yaxis.set_major_formatter(PercentFormatter(xmax=1, decimals=0))
    ax.grid(True, linestyle="--", alpha=0.35)
    lines1, labels1 = ax.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax.legend(lines1 + lines2, labels1 + labels2, loc="upper left")
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(output, dpi=160)
    plt.close(fig)


def _format_stock_display_name(*, ts_code: str, stock_name: str | None) -> str:
    if stock_name and stock_name.strip():
        return f"{ts_code} {stock_name.strip()}"
    return ts_code


def _chart_labels(*, has_cjk_font: bool) -> dict[str, str]:
    if has_cjk_font:
        return {
            "mean_reversion": "三年均值回归年化收益率",
            "consensus_cagr": "卖方三年 CAGR",
            "expected_return": "期望三年年化收益率",
            "close": "股价",
            "title": "{stock} {start_date}-{end_date} 逐日三年收益率",
            "x": "日期",
            "y": "收益率",
        }
    return {
        "mean_reversion": "3Y Mean Reversion Return",
        "consensus_cagr": "Sell-side 3Y CAGR",
        "expected_return": "Expected 3Y Annual Return",
        "close": "Close",
        "title": "{stock} {start_date}-{end_date} Daily 3Y Return",
        "x": "Date",
        "y": "Return",
    }
