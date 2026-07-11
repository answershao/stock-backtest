from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.expected_return import calculate_expected_return_3y_from_tushare, create_tushare_pro
from backtest.expected_return import TushareExpectedReturnRequest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--ts-code",
        default="600519.SH",
        help="股票代码，默认 600519.SH",
    )
    parser.add_argument(
        "--date",
        default="20150630",
        help="计算日期，格式 YYYYMMDD，默认 20150630",
    )
    parser.add_argument(
        "--token",
        default=os.getenv("TUSHARE_TOKEN"),
        help="Tushare token，默认读取环境变量 TUSHARE_TOKEN",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.token:
        raise SystemExit("缺少 Tushare token。请传 --token 或设置环境变量 TUSHARE_TOKEN")

    pro = create_tushare_pro(args.token)
    snapshot = calculate_expected_return_3y_from_tushare(
        pro,
        request=TushareExpectedReturnRequest(
            ts_code=args.ts_code,
            as_of_date=args.date,
        ),
    )
    print("股票:", snapshot.ts_code)
    print("请求日期:", snapshot.requested_as_of_date)
    print("实际使用交易日:", snapshot.as_of_date)
    print("当前 PE_TTM:", snapshot.current_pe)
    print("十年 PE 样本数:", snapshot.target_pe_sample_size)
    print("目标 PE:", snapshot.result.target_pe)
    print(f"三年 CAGR 起点实际 EPS ({snapshot.base_quarter}, 公告日 {snapshot.base_ann_date}):", snapshot.consensus_eps_base)
    print(f"三年 CAGR 终点预测 EPS ({snapshot.target_quarter}):", snapshot.consensus_eps_target)
    print("研报记录数:", snapshot.report_rows, "机构数:", snapshot.report_orgs)
    print(f"三年均值回归年化收益率: {snapshot.result.mean_reversion_return_3y:.2%}")    
    print(f"卖方三年 CAGR: {snapshot.consensus_cagr_3y:.2%}")    
    print(f"期望三年年化收益率: {snapshot.result.expected_return_3y:.2%}")
    print("结果是否有效:", snapshot.result.valid, "原因:", snapshot.result.reason)


if __name__ == "__main__":
    main()
