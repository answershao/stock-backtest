from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from src.data.tushare_cache import sanitize_cache_key_parts

REPORT_RC_PAGE_LIMIT = 3000


@dataclass(frozen=True)
class CacheValidationIssue:
    path: Path
    message: str


@dataclass(frozen=True)
class CacheValidationResult:
    issues: tuple[CacheValidationIssue, ...]

    @property
    def ok(self) -> bool:
        return not self.issues


def validate_tushare_cache(
    *,
    cache_dir: str | Path,
    stock_pool: list[str],
    required_datasets: tuple[str, ...] | None = None,
) -> CacheValidationResult:
    cache_root = Path(cache_dir)
    datasets = required_datasets or ("trade_cal", "daily_basic", "report_rc", "fina_indicator", "dividend")
    issues: list[CacheValidationIssue] = []

    trade_cal_path = cache_root / "trade_cal" / "full__is_open_1.csv"
    trade_cal = _read_csv_with_issues(trade_cal_path, issues)
    trade_dates: set[str] = set()
    if "trade_cal" in datasets and trade_cal is not None:
        trade_dates = _validate_trade_cal_frame(trade_cal_path, trade_cal, issues)

    for dataset in datasets:
        if dataset == "trade_cal":
            if trade_cal is None and not trade_cal_path.exists():
                issues.append(CacheValidationIssue(trade_cal_path, "缺少交易日历缓存文件"))
            continue

        for ts_code in stock_pool:
            path = _build_stock_cache_path(cache_root=cache_root, dataset=dataset, ts_code=ts_code)
            frame = _read_csv_with_issues(path, issues)
            if frame is None:
                if not path.exists():
                    issues.append(CacheValidationIssue(path, "缺少缓存文件"))
                continue
            _validate_stock_dataset_frame(
                path=path,
                dataset=dataset,
                ts_code=ts_code,
                frame=frame,
                trade_dates=trade_dates,
                issues=issues,
            )

    return CacheValidationResult(issues=tuple(issues))


def _build_stock_cache_path(*, cache_root: Path, dataset: str, ts_code: str) -> Path:
    suffix = []
    if dataset == "daily_basic":
        suffix = ["pe_ttm", "close"]
    return cache_root / dataset / ("__".join(sanitize_cache_key_parts([ts_code, *suffix])) + ".csv")


def _read_csv_with_issues(path: Path, issues: list[CacheValidationIssue]) -> pd.DataFrame | None:
    if not path.exists():
        return None
    try:
        return pd.read_csv(path)
    except Exception as exc:
        issues.append(CacheValidationIssue(path, f"CSV 读取失败: {exc}"))
        return None


def _validate_trade_cal_frame(
    path: Path,
    frame: pd.DataFrame,
    issues: list[CacheValidationIssue],
) -> set[str]:
    required_columns = {"cal_date", "is_open"}
    if not _require_columns(path, frame, required_columns, issues):
        return set()

    trade_dates = _validate_yyyymmdd_column(path, frame, "cal_date", issues)
    if "is_open" in frame.columns and not frame.empty:
        is_open = pd.to_numeric(frame["is_open"], errors="coerce")
        if is_open.isna().any():
            issues.append(CacheValidationIssue(path, "is_open 存在非数字值"))
        elif not (is_open == 1).all():
            issues.append(CacheValidationIssue(path, "is_open 存在非 1 的记录"))
    return trade_dates


def _validate_stock_dataset_frame(
    *,
    path: Path,
    dataset: str,
    ts_code: str,
    frame: pd.DataFrame,
    trade_dates: set[str],
    issues: list[CacheValidationIssue],
) -> None:
    if dataset == "daily_basic":
        if not _require_columns(path, frame, {"ts_code", "trade_date", "pe_ttm", "close"}, issues):
            return
        _validate_ts_code_column(path, frame, ts_code, issues)
        dates = _validate_yyyymmdd_column(path, frame, "trade_date", issues)
        _validate_trade_date_membership(path, dates, trade_dates, issues)
        return

    if dataset == "report_rc":
        if not _require_columns(path, frame, {"report_date", "quarter", "org_name", "eps"}, issues):
            return
        _validate_yyyymmdd_column(path, frame, "report_date", issues)
        _validate_report_rc_completeness(path, frame, issues)
        return

    if dataset == "fina_indicator":
        if not _require_columns(path, frame, {"ann_date", "end_date", "eps"}, issues):
            return
        _validate_yyyymmdd_column(path, frame, "ann_date", issues)
        _validate_yyyymmdd_column(path, frame, "end_date", issues)
        return

    if dataset == "dividend":
        if not _require_columns(path, frame, {"ts_code", "ex_date", "cash_div", "stk_div", "stk_bo_rate", "stk_co_rate", "div_proc"}, issues):
            return
        _validate_ts_code_column(path, frame, ts_code, issues)
        _validate_yyyymmdd_column(path, frame, "ex_date", issues)
        return

    issues.append(CacheValidationIssue(path, f"不支持校验的数据集: {dataset}"))


def _require_columns(
    path: Path,
    frame: pd.DataFrame,
    required_columns: set[str],
    issues: list[CacheValidationIssue],
) -> bool:
    missing = sorted(required_columns - set(frame.columns))
    if missing:
        issues.append(CacheValidationIssue(path, f"缺少关键列: {', '.join(missing)}"))
        return False
    return True


def _validate_ts_code_column(
    path: Path,
    frame: pd.DataFrame,
    expected_ts_code: str,
    issues: list[CacheValidationIssue],
) -> None:
    if frame.empty:
        return
    values = frame["ts_code"].astype(str)
    invalid = sorted(set(values[values != expected_ts_code].tolist()))
    if invalid:
        issues.append(CacheValidationIssue(path, f"ts_code 与文件名不一致: 期望 {expected_ts_code}，实际包含 {', '.join(invalid[:3])}"))


def _validate_yyyymmdd_column(
    path: Path,
    frame: pd.DataFrame,
    column: str,
    issues: list[CacheValidationIssue],
) -> set[str]:
    if frame.empty:
        return set()

    raw_values = frame[column].astype(str)
    parsed = pd.to_datetime(raw_values, format="%Y%m%d", errors="coerce")
    if parsed.isna().any():
        issues.append(CacheValidationIssue(path, f"{column} 存在非法日期"))
        return set()

    normalized = parsed.dt.strftime("%Y%m%d")
    if not normalized.equals(raw_values):
        issues.append(CacheValidationIssue(path, f"{column} 存在非 YYYYMMDD 格式"))

    if not parsed.is_monotonic_increasing:
        issues.append(CacheValidationIssue(path, f"{column} 未按升序排列"))

    if normalized.duplicated().any():
        issues.append(CacheValidationIssue(path, f"{column} 存在重复值"))

    return set(normalized.tolist())


def _validate_trade_date_membership(
    path: Path,
    dates: set[str],
    trade_dates: set[str],
    issues: list[CacheValidationIssue],
) -> None:
    if not dates or not trade_dates:
        return
    invalid = sorted(dates - trade_dates)
    if invalid:
        issues.append(CacheValidationIssue(path, f"存在非交易日数据: {', '.join(invalid[:3])}"))


def _validate_report_rc_completeness(
    path: Path,
    frame: pd.DataFrame,
    issues: list[CacheValidationIssue],
) -> None:
    if frame.empty:
        return

    row_count = len(frame)
    if row_count >= REPORT_RC_PAGE_LIMIT and row_count % REPORT_RC_PAGE_LIMIT == 0:
        issues.append(
            CacheValidationIssue(
                path,
                f"研报行数为 {REPORT_RC_PAGE_LIMIT} 的整倍数，可能命中分页截断，建议确认是否已拉取完整",
            )
        )
