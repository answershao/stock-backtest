"""
策略回测系统 - 配置定义

配置分组：
1. 运行模式
   - SYSTEM
2. 回测参数
   - BACKTEST
3. 股票池参数
   - UNIVERSE
4. 选股与调仓策略参数
   - STRATEGY
5. 数据源参数
   - DATA_SOURCE
6. 交易成本参数
   - COSTS
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

DEFAULT_STOCK_POOL: List[Tuple[str, str, str]] = [
    ("000858", "五粮液", "食品饮料"),
    ("601888", "中国中免", "商贸零售"),
    ("001914", "招商积余", "房地产"),
    ("600298", "安琪酵母", "食品饮料"),
    ("600085", "同仁堂", "医药生物"),
    ("000423", "东阿阿胶", "医药生物"),
    ("600285", "羚锐制药", "医药生物"),
    ("600305", "恒顺醋业", "食品饮料"),
    ("600529", "山东药玻", "医药生物"),
    ("600161", "天坛生物", "医药生物"),
    ("002304", "洋河股份", "食品饮料"),
    ("603288", "海天味业", "食品饮料"),
    ("000538", "云南白药", "医药生物"),
    ("600887", "伊利股份", "食品饮料"),
    ("600332", "白云山", "医药生物"),
    ("600600", "青岛啤酒", "食品饮料"),
    ("002507", "涪陵榨菜", "食品饮料"),
    ("600809", "山西汾酒", "食品饮料"),
    ("000568", "泸州老窖", "食品饮料"),
    ("600329", "达仁堂", "医药生物"),
    ("600436", "片仔癀", "医药生物"),
    ("000963", "华东医药", "医药生物"),
    ("000999", "华润三九", "医药生物"),
    ("600566", "济川药业", "医药生物"),
    ("002032", "苏泊尔", "家用电器"),
    ("600519", "贵州茅台", "食品饮料"),
    ("000651", "格力电器", "家用电器"),
]


@dataclass
class SystemConfig:
    # 回测运行模式:
    # - value_portfolio: 以文档中的价值组合思想为主线
    # - equal_weight_pool: 仅按股票池做静态等权
    strategy_mode: str = "value_portfolio"  # "value_portfolio" | "equal_weight_pool"


@dataclass
class BacktestConfig:
    # 回测区间
    start_date: str = "2021-01-01"
    end_date: str = "2026-01-31"

    # 初始资金
    initial_capital: float = 5_000_000

    # 调仓计划，格式为 MM-DD，会自动顺延到下一个交易日
    rebalance_schedule: List[str] = field(default_factory=lambda: ["05-01", "11-01"])

    # 基准指数与无风险利率
    benchmark_index: str = "000300"
    risk_free_rate: float = 0.02


@dataclass
class UniverseConfig:
    # 手工白名单股票池。
    # 每项格式: (股票代码, 股票名称, 所属行业)
    stock_pool: List[Tuple[str, str, str]] = field(
        default_factory=lambda: list(DEFAULT_STOCK_POOL)
    )

    # 候选池使用策略:
    # - whitelist: 仅使用 stock_pool
    # - all_quotes: 使用行情数据中实际拉取到的全部股票
    # - fundamentals: 使用基本面数据中出现的全部股票
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
    # 默认仓位执行方式:
    # 价值组合主线下，默认仍使用等权/半等权作为落地方式，
    # 但仓位规则从属于“低估优质股 + 组合调仓”的核心思想。
    target_weight: float = 0.05
    max_single_weight: float = 0.10
    trim_position_ratio: float = 0.5
    weight_tolerance: float = 0.0

    # 组合约束
    # 当前按“27 只白名单，最多持有 20 只”的主干设计。
    max_positions: int = 20
    max_industries: int = 10
    max_positions_per_industry: int = 3

    # 估值历史要求
    valuation_window_years: int = 5
    min_valuation_history_observations: int = 36
    min_listing_days: int = 365 * 3

    # 成长相关阈值
    g_buy_threshold: float = 0.10
    g_sell_threshold: float = 0.10
    g_cap: float = 0.35

    # PEG 阈值
    peg_buy_threshold: float = 1.2
    peg_trim_threshold: float = 1.8

    # 估值分位阈值
    pe_trim_quantile: float = 0.80
    pe_exit_quantile: float = 0.95

    # 质量与换股阈值
    roe_threshold: float = 0.12
    switch_score_gap: float = 20.0

    # 综合评分权重
    score_g_weight: float = 100.0
    score_peg_weight: float = 10.0
    score_pe_percentile_weight: float = 20.0
    score_roe_weight: float = 1.0


@dataclass
class DataSourceConfig:
    # 本地基本面数据路径；不存在时回退到 Tushare
    fundamental_data_path: str = "data/fundamentals.csv"

    # 股票行情/分红缓存目录
    market_cache_dir: str = "data/cache"

    # 日线缓存使用的复权方式:
    # - hfq: 后复权
    # - qfq: 前复权
    # - none: 不复权
    market_cache_quote_adjustment: str = "none"

    # 首次预热缓存时的起始日期；日线会从该日期开始拉取到今天
    market_cache_start_date: str = "1990-01-01"

    # Tushare 相关配置
    tushare_token: str = "AelZc4nygN5K6_YvBZBKnA3Jz1nne6kHBrLMvRnEeKA"
    tushare_http_url: str = "https://tu.brze.top"
    tushare_rate_limit_seconds: float = 0.6


@dataclass
class CostConfig:
    # 交易成本参数
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


def is_value_portfolio_mode(mode: str | None = None) -> bool:
    return (mode or SYSTEM.strategy_mode) == "value_portfolio"


def is_equal_weight_pool_mode(mode: str | None = None) -> bool:
    return (mode or SYSTEM.strategy_mode) == "equal_weight_pool"
