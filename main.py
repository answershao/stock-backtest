"""
研究版回测入口脚本

执行方式:
    python3 main.py
"""

from __future__ import annotations

from stock_backtest.app.app_runner import run_application


def main():
    run_application()


if __name__ == "__main__":
    main()
