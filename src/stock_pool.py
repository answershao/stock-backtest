from __future__ import annotations

import argparse


def resolve_stock_pool(args: argparse.Namespace) -> list[str]:
    raw = args.stock_pool
    if not isinstance(raw, dict):
        return []
    return [str(code).strip() for code in raw.keys() if str(code).strip()]
