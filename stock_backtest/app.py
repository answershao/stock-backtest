"""
应用运行层

负责串联：
1. 输入装配
2. 回测执行
3. 指标计算
4. 结果导出
"""

from __future__ import annotations

from pathlib import Path

from stock_backtest.backtest import run_backtest_result
from stock_backtest.data import load_backtest_inputs
from stock_backtest.reporting import compute_metrics, export_backtest_result, metrics_report


def run_application(output_dir=Path("outputs")):
    inputs = load_backtest_inputs()
    result = run_backtest_result(inputs)

    metrics = compute_metrics(result.daily, result.trades)
    print(metrics_report(metrics))

    export_backtest_result(result, output_dir)
    print("回测结果已输出到: %s" % output_dir.resolve())

    return result, metrics
