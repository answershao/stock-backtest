"""
Tushare 客户端与原始数据抓取
"""

from __future__ import annotations

import time

from stock_backtest.core import config as cfg


def require_tushare():
    try:
        import tushare as ts
        from tushare.pro import client as ts_client
    except ImportError as exc:
        raise ImportError("未安装 tushare。请先执行: pip install tushare") from exc

    ts_client.DataApi._DataApi__http_url = cfg.DATA_SOURCE.tushare_http_url
    pro = ts.pro_api(cfg.DATA_SOURCE.tushare_token)
    return ts, pro


def throttle():
    time.sleep(cfg.DATA_SOURCE.tushare_rate_limit_seconds)


def to_ts_code(code, asset="E"):
    code = str(code).strip()
    if code.endswith((".SH", ".SZ")):
        return code.upper()
    if asset == "I":
        suffix = ".SZ" if code.startswith(("000", "399", "980")) else ".SH"
        return "%s%s" % (code, suffix)
    suffix = ".SH" if code.startswith(("5", "6", "9")) else ".SZ"
    return "%s%s" % (code, suffix)


def date_to_ts(value):
    return value.replace("-", "")


def fetch_trade_calendar_raw(start, end):
    _, pro = require_tushare()
    df = pro.trade_cal(
        exchange="",
        start_date=date_to_ts(start),
        end_date=date_to_ts(end),
        is_open="1",
    )
    throttle()
    return df


def fetch_daily_quotes_raw(symbols, start, end):
    ts, pro = require_tushare()
    result = {}
    start_fmt = date_to_ts(start)
    end_fmt = date_to_ts(end)
    for code in symbols:
        df = ts.pro_bar(
            api=pro,
            ts_code=to_ts_code(code),
            adj="hfq",
            asset="E",
            start_date=start_fmt,
            end_date=end_fmt,
        )
        throttle()
        result[code] = df
    return result


def fetch_dividends_raw(symbols):
    _, pro = require_tushare()
    result = {}
    for code in symbols:
        df = pro.dividend(ts_code=to_ts_code(code))
        throttle()
        result[code] = df
    return result


def fetch_benchmark_raw(index_code, start, end):
    ts, pro = require_tushare()
    ts_code = to_ts_code(index_code, asset="I")
    df = pro.index_daily(
        ts_code=ts_code,
        start_date=date_to_ts(start),
        end_date=date_to_ts(end),
    )
    throttle()
    if df is None or df.empty:
        df = ts.pro_bar(
            api=pro,
            ts_code=ts_code,
            asset="I",
            start_date=date_to_ts(start),
            end_date=date_to_ts(end),
        )
        throttle()
    return df


def fetch_stock_basic_raw():
    _, pro = require_tushare()
    df = pro.stock_basic(exchange="", list_status="L", fields="ts_code,symbol,name,industry,list_date")
    throttle()
    return df


def fetch_daily_basic_raw(code, start, end):
    _, pro = require_tushare()
    df = pro.daily_basic(
        ts_code=to_ts_code(code),
        start_date=date_to_ts(start),
        end_date=date_to_ts(end),
        fields="ts_code,trade_date,pe_ttm,pb",
    )
    throttle()
    return df


def fetch_fina_indicator_raw(code, start, end):
    _, pro = require_tushare()
    df = pro.fina_indicator(
        ts_code=to_ts_code(code),
        start_date=date_to_ts(start),
        end_date=date_to_ts(end),
        fields="ts_code,end_date,roe,netprofit_yoy",
    )
    throttle()
    return df
