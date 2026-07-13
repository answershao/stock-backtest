from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class StrategyConfig:
    max_positions: int = 20
    target_weight: float = 0.05
    entry_threshold: float = 0.20
    exit_threshold: float = 0.0
    rebalance_month_days: tuple[str, ...] = ("05-01", "11-01")
    initial_cash: float = 1_000_000.0


@dataclass(frozen=True)
class BacktestResult:
    portfolio_history: pd.DataFrame
    trade_log: pd.DataFrame
    holdings_history: pd.DataFrame
    rebalance_dates: tuple[pd.Timestamp, ...]


def run_expected_return_strategy(
    price_df: pd.DataFrame,
    signal_df: pd.DataFrame,
    *,
    start_date: str,
    end_date: str | None = None,
    stock_pool: list[str] | tuple[str, ...] | None = None,
    config: StrategyConfig | None = None,
    dividend_df: pd.DataFrame | None = None,
) -> BacktestResult:
    """
    Minimal backtest for the core strategy idea in design.md.

    Assumptions:
    - Trades are executed at the rebalance day's close.
    - Buy quantities are rounded down to the nearest 100 shares (A-share lot rule).
    - ``signal_df.expected_return_3y`` is precomputed outside this module.
    """

    cfg = config or StrategyConfig()
    prices = _prepare_price_data(price_df, stock_pool=stock_pool)
    signals = _prepare_signal_data(signal_df, stock_pool=stock_pool)
    dividends = _prepare_dividend_data(dividend_df, stock_pool=stock_pool)

    trading_dates = tuple(prices.index.get_level_values("date").unique().sort_values())
    if not trading_dates:
        raise ValueError("price_df does not contain any trading dates.")

    start_ts = _resolve_start_date(trading_dates, pd.Timestamp(start_date))
    end_ts = pd.Timestamp(end_date) if end_date else trading_dates[-1]
    trading_dates = tuple(date for date in trading_dates if start_ts <= date <= end_ts)
    if not trading_dates:
        raise ValueError("No trading dates available in the requested backtest window.")

    rebalance_dates = _resolve_rebalance_dates(
        trading_dates=trading_dates,
        start_date=start_ts,
        end_date=end_ts,
        month_days=cfg.rebalance_month_days,
    )
    event_dates = {start_ts, *rebalance_dates}

    cash = float(cfg.initial_cash)
    holdings: dict[str, float] = {}
    trades: list[dict[str, object]] = []
    snapshots: list[dict[str, object]] = []
    portfolio_rows: list[dict[str, object]] = []

    for date in trading_dates:
        cash, dividend_cash = _apply_cash_dividends(date, holdings, cash, dividends)

        if date in event_dates:
            snapshot = _build_signal_snapshot(signals, date)
            if date == start_ts:
                target_codes = _select_initial_positions(snapshot, cfg)
            else:
                target_codes = _select_rebalanced_positions(snapshot, holdings, cfg)

            holdings, cash, new_trades = _rebalance_to_targets(
                date=date,
                prices=prices,
                holdings=holdings,
                cash=cash,
                target_codes=target_codes,
                snapshot=snapshot,
                config=cfg,
            )
            trades.extend(new_trades)
            snapshots.extend(_capture_holdings_snapshot(date, holdings, prices, snapshot, cash))

        portfolio_rows.append(_capture_portfolio_row(date, prices, holdings, cash, dividend_cash))

    return BacktestResult(
        portfolio_history=pd.DataFrame(portfolio_rows),
        trade_log=pd.DataFrame(trades),
        holdings_history=pd.DataFrame(snapshots),
        rebalance_dates=rebalance_dates,
    )


def _prepare_price_data(
    price_df: pd.DataFrame,
    *,
    stock_pool: list[str] | tuple[str, ...] | None,
) -> pd.DataFrame:
    required = {"date", "code", "close"}
    missing = required - set(price_df.columns)
    if missing:
        raise ValueError(f"price_df missing columns: {sorted(missing)}")

    data = price_df.copy()
    data["date"] = pd.to_datetime(data["date"])
    data["code"] = data["code"].astype(str)
    data["close"] = pd.to_numeric(data["close"], errors="coerce")
    data = data.dropna(subset=["date", "code", "close"])
    if stock_pool is not None:
        allowed = {str(code) for code in stock_pool}
        data = data[data["code"].isin(allowed)]
    if data.empty:
        raise ValueError("price_df is empty after preprocessing.")
    return data.sort_values(["date", "code"]).set_index(["date", "code"])


def _prepare_signal_data(
    signal_df: pd.DataFrame,
    *,
    stock_pool: list[str] | tuple[str, ...] | None,
) -> pd.DataFrame:
    required = {"date", "code", "expected_return_3y"}
    missing = required - set(signal_df.columns)
    if missing:
        raise ValueError(f"signal_df missing columns: {sorted(missing)}")

    data = signal_df.copy()
    data["date"] = pd.to_datetime(data["date"])
    data["code"] = data["code"].astype(str)
    data["expected_return_3y"] = pd.to_numeric(data["expected_return_3y"], errors="coerce")
    data = data.dropna(subset=["date", "code"])
    if stock_pool is not None:
        allowed = {str(code) for code in stock_pool}
        data = data[data["code"].isin(allowed)]
    return data.sort_values(["date", "code"]).set_index(["date", "code"])


def _prepare_dividend_data(
    dividend_df: pd.DataFrame | None,
    *,
    stock_pool: list[str] | tuple[str, ...] | None,
) -> pd.DataFrame:
    if dividend_df is None:
        empty = pd.DataFrame(columns=["cash_div"])
        empty.index = pd.MultiIndex.from_arrays([[], []], names=["date", "code"])
        return empty

    required = {"date", "code", "cash_div"}
    missing = required - set(dividend_df.columns)
    if missing:
        raise ValueError(f"dividend_df missing columns: {sorted(missing)}")

    data = dividend_df.copy()
    data["date"] = pd.to_datetime(data["date"])
    data["code"] = data["code"].astype(str)
    data["cash_div"] = pd.to_numeric(data["cash_div"], errors="coerce")
    data = data.dropna(subset=["date", "code", "cash_div"])
    data = data[data["cash_div"] != 0]
    if stock_pool is not None:
        allowed = {str(code) for code in stock_pool}
        data = data[data["code"].isin(allowed)]
    if data.empty:
        empty = pd.DataFrame(columns=["cash_div"])
        empty.index = pd.MultiIndex.from_arrays([[], []], names=["date", "code"])
        return empty
    return data.sort_values(["date", "code"]).set_index(["date", "code"])


def _resolve_start_date(trading_dates: tuple[pd.Timestamp, ...], requested: pd.Timestamp) -> pd.Timestamp:
    for date in trading_dates:
        if date >= requested:
            return date
    raise ValueError("start_date is after the last available trading date.")


def _resolve_rebalance_dates(
    *,
    trading_dates: tuple[pd.Timestamp, ...],
    start_date: pd.Timestamp,
    end_date: pd.Timestamp,
    month_days: tuple[str, ...],
) -> tuple[pd.Timestamp, ...]:
    resolved: list[pd.Timestamp] = []
    first_year = start_date.year
    last_year = end_date.year

    for year in range(first_year, last_year + 1):
        for month_day in month_days:
            target = pd.Timestamp(f"{year}-{month_day}")
            if target < start_date or target > end_date:
                continue
            actual = next((date for date in trading_dates if date >= target), None)
            if actual is None or actual > end_date:
                continue
            if actual not in resolved:
                resolved.append(actual)

    return tuple(sorted(resolved))


def _build_signal_snapshot(signals: pd.DataFrame, date: pd.Timestamp) -> pd.DataFrame:
    try:
        snapshot = signals.xs(date, level="date").reset_index()
    except KeyError:
        return pd.DataFrame(columns=["code", "expected_return_3y"])
    return snapshot.sort_values(["expected_return_3y", "code"], ascending=[False, True]).reset_index(drop=True)


def _apply_cash_dividends(
    date: pd.Timestamp,
    holdings: dict[str, float],
    cash: float,
    dividends: pd.DataFrame,
) -> tuple[float, float]:
    if dividends.empty or not holdings:
        return cash, 0.0

    try:
        todays_dividends = dividends.xs(date, level="date")
    except KeyError:
        return cash, 0.0

    dividend_cash = 0.0
    for code, row in todays_dividends.iterrows():
        shares = holdings.get(str(code), 0.0)
        if abs(shares) < 1e-12:
            continue
        cash_div = float(row["cash_div"])
        dividend_cash += shares * cash_div
    return cash + dividend_cash, dividend_cash


def _select_initial_positions(snapshot: pd.DataFrame, config: StrategyConfig) -> list[str]:
    eligible = snapshot[snapshot["expected_return_3y"] > config.entry_threshold]
    return eligible["code"].head(config.max_positions).tolist()


def _select_rebalanced_positions(
    snapshot: pd.DataFrame,
    holdings: dict[str, float],
    config: StrategyConfig,
) -> list[str]:
    signal_map = dict(zip(snapshot["code"], snapshot["expected_return_3y"]))

    kept_codes: list[str] = []
    for code in holdings:
        value = signal_map.get(code)
        if value is None or pd.isna(value) or value >= config.exit_threshold:
            kept_codes.append(code)

    slots = max(config.max_positions - len(kept_codes), 0)
    if slots == 0:
        return kept_codes[: config.max_positions]

    candidates = snapshot[
        (~snapshot["code"].isin(kept_codes))
        & (snapshot["expected_return_3y"] > config.entry_threshold)
    ]
    new_codes = candidates["code"].head(slots).tolist()
    return kept_codes + new_codes


def _rebalance_to_targets(
    *,
    date: pd.Timestamp,
    prices: pd.DataFrame,
    holdings: dict[str, float],
    cash: float,
    target_codes: list[str],
    snapshot: pd.DataFrame,
    config: StrategyConfig,
) -> tuple[dict[str, float], float, list[dict[str, object]]]:
    signal_map = dict(zip(snapshot["code"], snapshot["expected_return_3y"]))
    prices_today = prices.xs(date, level="date")

    equity_before = cash + sum(holdings.get(code, 0.0) * float(prices_today.loc[code, "close"]) for code in holdings)
    target_values = {code: equity_before * config.target_weight for code in target_codes}

    next_holdings = dict(holdings)
    trade_rows: list[dict[str, object]] = []

    for code, shares in list(next_holdings.items()):
        current_price = float(prices_today.loc[code, "close"])
        current_value = shares * current_price
        target_value = target_values.get(code, 0.0)
        delta_value = target_value - current_value
        if abs(delta_value) < 1e-12:
            continue

        delta_shares = delta_value / current_price
        if delta_shares > 0:
            # 买入：向下取整到 100 的整数倍
            delta_shares = int(delta_shares / 100.0) * 100
        else:
            # 卖出：绝对值向下取整到 100 的整数倍
            delta_shares = -int(abs(delta_shares) / 100.0) * 100

        if abs(delta_shares) < 1:
            continue
        next_holdings[code] = shares + delta_shares
        cash -= delta_shares * current_price
        if abs(next_holdings[code]) < 1e-12:
            del next_holdings[code]
        trade_rows.append(
            _trade_row(
                date=date,
                code=code,
                delta_shares=delta_shares,
                price=current_price,
                expected_return_3y=signal_map.get(code),
            )
        )

    for code, target_value in target_values.items():
        if code in holdings:
            continue
        current_price = float(prices_today.loc[code, "close"])
        shares = int(target_value / current_price / 100.0) * 100
        if shares <= 0:
            continue
        next_holdings[code] = float(shares)
        cash -= shares * current_price
        trade_rows.append(
            _trade_row(
                date=date,
                code=code,
                delta_shares=shares,
                price=current_price,
                expected_return_3y=signal_map.get(code),
            )
        )

    return next_holdings, cash, trade_rows


def _trade_row(
    *,
    date: pd.Timestamp,
    code: str,
    delta_shares: float,
    price: float,
    expected_return_3y: float | None,
) -> dict[str, object]:
    trade_value = delta_shares * price
    return {
        "date": date,
        "code": code,
        "action": "BUY" if delta_shares > 0 else "SELL",
        "shares": abs(delta_shares),
        "price": price,
        "trade_value": abs(trade_value),
        "signed_trade_value": trade_value,
        "expected_return_3y": expected_return_3y,
    }


def _capture_holdings_snapshot(
    date: pd.Timestamp,
    holdings: dict[str, float],
    prices: pd.DataFrame,
    snapshot: pd.DataFrame,
    cash: float,
) -> list[dict[str, object]]:
    signal_map = dict(zip(snapshot["code"], snapshot["expected_return_3y"]))
    prices_today = prices.xs(date, level="date")
    holdings_value = sum(shares * float(prices_today.loc[code, "close"]) for code, shares in holdings.items())
    equity = cash + holdings_value

    rows: list[dict[str, object]] = []
    for code, shares in sorted(holdings.items()):
        price = float(prices_today.loc[code, "close"])
        market_value = shares * price
        rows.append(
            {
                "date": date,
                "code": code,
                "shares": shares,
                "close": price,
                "market_value": market_value,
                "weight": 0.0 if equity == 0 else market_value / equity,
                "expected_return_3y": signal_map.get(code),
            }
        )
    return rows


def _capture_portfolio_row(
    date: pd.Timestamp,
    prices: pd.DataFrame,
    holdings: dict[str, float],
    cash: float,
    dividend_cash: float,
) -> dict[str, object]:
    prices_today = prices.xs(date, level="date")
    holdings_value = sum(shares * float(prices_today.loc[code, "close"]) for code, shares in holdings.items())
    equity = cash + holdings_value
    return {
        "date": date,
        "cash": cash,
        "holdings_value": holdings_value,
        "equity": equity,
        "positions": len(holdings),
        "dividend_cash": dividend_cash,
    }
