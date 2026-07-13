import tempfile
import unittest
from pathlib import Path

import pandas as pd

from src.plotting import plot_expected_return_frame


class PlottingTest(unittest.TestCase):
    def test_plot_expected_return_frame_writes_file(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "date": pd.Timestamp("2024-01-02"),
                    "close": 10.0,
                    "mean_reversion_return_3y": 0.08,
                    "consensus_cagr_3y": 0.12,
                    "expected_return_3y": 0.21,
                },
                {
                    "date": pd.Timestamp("2024-01-03"),
                    "close": 10.5,
                    "mean_reversion_return_3y": 0.09,
                    "consensus_cagr_3y": 0.11,
                    "expected_return_3y": 0.20,
                },
            ]
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "expected_return.png"
            plot_expected_return_frame(
                frame,
                ts_code="600519.SH",
                start_date="20240102",
                end_date="20240103",
                output=output,
            )

            self.assertTrue(output.exists())
            self.assertGreater(output.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
