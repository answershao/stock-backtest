import tempfile
import unittest
from pathlib import Path

import pandas as pd

from src.data.tushare_cache import TushareDataCache
from src.data.tushare_cache_prefetch import fetch_open_trade_dates_cached


class TushareDataCacheTest(unittest.TestCase):
    def test_load_or_fetch_hits_file_after_first_fetch(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = TushareDataCache(Path(tmpdir), cache_only=False)
            calls = {"count": 0}

            def fetcher() -> pd.DataFrame:
                calls["count"] += 1
                return pd.DataFrame([{"cal_date": "20240102", "is_open": 1}])

            first = cache.load_or_fetch(
                dataset="trade_cal",
                key_parts=["20240101", "20240131", "is_open_1"],
                fetcher=fetcher,
            )
            second = cache.load_or_fetch(
                dataset="trade_cal",
                key_parts=["20240101", "20240131", "is_open_1"],
                fetcher=fetcher,
            )

        self.assertEqual(calls["count"], 1)
        self.assertEqual(len(first), 1)
        self.assertEqual(len(second), 1)

    def test_fetch_open_trade_dates_cached_avoids_second_network_call(self) -> None:
        class FakePro:
            def __init__(self) -> None:
                self.calls = 0

            def trade_cal(self, **kwargs) -> pd.DataFrame:
                self.calls += 1
                return pd.DataFrame(
                    [
                        {"cal_date": "20240102", "is_open": 1},
                        {"cal_date": "20240103", "is_open": 1},
                    ]
                )

        with tempfile.TemporaryDirectory() as tmpdir:
            pro = FakePro()
            cache = TushareDataCache(Path(tmpdir), cache_only=False)

            first = fetch_open_trade_dates_cached(
                pro,
                start_date="20240101",
                end_date="20240131",
                cache=cache,
            )
            second = fetch_open_trade_dates_cached(
                pro,
                start_date="20240101",
                end_date="20240131",
                cache=cache,
            )

        self.assertEqual(pro.calls, 1)
        self.assertEqual(first, second)

    def test_cache_only_raises_when_file_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = TushareDataCache(Path(tmpdir), cache_only=True)

            with self.assertRaises(FileNotFoundError):
                cache.load_or_fetch(
                    dataset="daily",
                    key_parts=["600519.SH", "20200101", "20241231", "close"],
                    fetcher=lambda: pd.DataFrame(),
                )


if __name__ == "__main__":
    unittest.main()
