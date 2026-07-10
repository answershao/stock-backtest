"""
策略回测系统配置。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BacktestConfig:
    start_date: str
    end_date: str
    tushare_token: str
    tushare_proxy_url: str
    cache_dir: str
    cache_enabled: bool
    cache_force_refresh: bool
    price_adj: str | None
    initial_capital: float
    target_weight: float
    weight_tolerance: float
    rebalance_schedule: list[str]
    dividend_mode: str
    stock_pool: list[tuple[str, str]]
    commission_rate: float
    commission_min: float
    stamp_tax_rate: float
    transfer_fee_rate: float
    benchmark_index: str
    risk_free_rate: float

    @property
    def stock_codes(self) -> list[str]:
        return [code for code, _ in self.stock_pool]

    @property
    def stock_name_map(self) -> dict[str, str]:
        return dict(self.stock_pool)


DEFAULT_CONFIG = BacktestConfig(
    start_date="2021-01-04",
    end_date="2026-06-30",
    tushare_token="AelZc4nygN5K6_YvBZBKnA3Jz1nne6kHBrLMvRnEeKA",
    tushare_proxy_url="https://tu.brze.top",
    cache_dir="cache",
    cache_enabled=True,
    cache_force_refresh=False,
    price_adj=None,
    initial_capital=5_000_000,
    target_weight=0.05,
    weight_tolerance=0.001,
    rebalance_schedule=["05-01", "11-01"],
    dividend_mode="reinvest",
    stock_pool=[
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
    ],
    commission_rate=0.0001,
    commission_min=0,
    stamp_tax_rate=0.0005,
    transfer_fee_rate=0.00001,
    benchmark_index="000300.SH",
    risk_free_rate=0.02,
)
