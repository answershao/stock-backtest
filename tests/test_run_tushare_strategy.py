import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

from src.stock_pool import resolve_stock_pool


class RunTushareStrategyCliTest(unittest.TestCase):
    def test_resolve_stock_pool_from_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "pool.csv"
            path.write_text("name,ts_code\n贵州茅台,600519.SH\n五粮液,000858.SZ\n", encoding="utf-8")

            result = resolve_stock_pool(
                Namespace(
                    stock_pool=None,
                    stock_pool_file=str(path),
                )
            )

        self.assertEqual(result, ["600519.SH", "000858.SZ"])


if __name__ == "__main__":
    unittest.main()
