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
