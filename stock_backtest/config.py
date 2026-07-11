"""
策略回测系统 - 配置定义

优先使用对象化配置：
- SYSTEM
- BACKTEST
- UNIVERSE
- STRATEGY
- DATA_SOURCE
- COSTS
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple


@dataclass
class SystemConfig:
    strategy_mode: str = "research_quant"  # "research_quant" | "static_equal_weight"


@dataclass
class BacktestConfig:
    start_date: str = "2024-01-01"
    end_date: str = "2024-03-31"
    initial_capital: float = 5_000_000
    rebalance_schedule: List[str] = field(default_factory=lambda: ["01-15", "03-15"])
    benchmark_index: str = "000300"
    risk_free_rate: float = 0.02


@dataclass
class UniverseConfig:
    stock_pool: List[Tuple[str, str, str]] = field(
        default_factory=lambda: [
            ("603288", "海天味业", "食品饮料"),
        ]
    )
    candidate_pool_mode: str = "whitelist"  # "whitelist" | "all_quotes" | "fundamentals"

    @property
    def stock_codes(self) -> List[str]:
        return [code for code, _, _ in self.stock_pool]

    @property
    def stock_name_map(self) -> Dict[str, str]:
        return {code: name for code, name, _ in self.stock_pool}

    @property
    def stock_industry_map(self) -> Dict[str, str]:
        return {code: industry for code, _, industry in self.stock_pool}


@dataclass
class StrategyConfig:
    target_weight: float = 0.05
    max_single_weight: float = 0.10
    trim_position_ratio: float = 0.5
    weight_tolerance: float = 0.0

    max_positions: int = 1
    max_industries: int = 1
    max_positions_per_industry: int = 1

    valuation_window_years: int = 5
    min_valuation_history_observations: int = 36
    min_listing_days: int = 365 * 3

    g_buy_threshold: float = 0.10
    g_sell_threshold: float = 0.10
    g_cap: float = 0.35

    peg_buy_threshold: float = 1.2
    peg_trim_threshold: float = 1.8

    pe_trim_quantile: float = 0.80
    pe_exit_quantile: float = 0.95

    roe_threshold: float = 0.12
    switch_score_gap: float = 20.0

    score_g_weight: float = 100.0
    score_peg_weight: float = 10.0
    score_pe_percentile_weight: float = 20.0
    score_roe_weight: float = 1.0


@dataclass
class DataSourceConfig:
    fundamental_data_path: str = "data/fundamentals.csv"
    tushare_token: str = "AelZc4nygN5K6_YvBZBKnA3Jz1nne6kHBrLMvRnEeKA"
    tushare_http_url: str = "https://tu.brze.top"
    tushare_rate_limit_seconds: float = 0.6


@dataclass
class CostConfig:
    commission_rate: float = 0.0001
    commission_min: float = 0
    stamp_tax_rate: float = 0.0005
    transfer_fee_rate: float = 0.00001


SYSTEM = SystemConfig()
BACKTEST = BacktestConfig()
UNIVERSE = UniverseConfig()
STRATEGY = StrategyConfig()
DATA_SOURCE = DataSourceConfig()
COSTS = CostConfig()
