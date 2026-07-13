from __future__ import annotations

import pandas as pd


def normalize_report_rc_frame(data: pd.DataFrame, *, min_rows_per_report: int = 3) -> pd.DataFrame:
    frame = data.copy()
    id_columns = ["report_title", "report_type", "classify", "org_name", "author_name"]
    for column in id_columns:
        if column not in frame.columns:
            frame[column] = pd.NA

    frame["report_date"] = pd.to_datetime(frame["report_date"], format="%Y%m%d", errors="coerce")
    frame["eps"] = pd.to_numeric(frame["eps"], errors="coerce")
    frame = frame.dropna(subset=["report_date", *id_columns]).copy()
    if frame.empty:
        return frame.reset_index(drop=True)

    frame["report_id"] = frame["report_date"].dt.strftime("%Y%m%d")
    for column in id_columns:
        frame["report_id"] = frame["report_id"] + "_" + frame[column].astype(str)
    report_granularity = ["report_id"]
    if "quarter" in frame.columns:
        valid_report_ids = (
            frame.dropna(subset=["quarter"])
            .groupby(report_granularity)["quarter"]
            .nunique()
        )
    else:
        valid_report_ids = frame.groupby(report_granularity).size()
    valid_report_ids = valid_report_ids[valid_report_ids >= min_rows_per_report].index
    frame = frame[frame["report_id"].isin(valid_report_ids)].copy()
    if frame.empty:
        return frame.reset_index(drop=True)

    return frame.sort_values(["report_date", "report_title", "quarter", "org_name"]).reset_index(drop=True)
