import unittest

import pandas as pd

from backtest.expected_return import (
    ExpectedReturn3YCalculator,
    GrowthInputs,
    build_consensus_growth_from_report_rc,
    calculate_expected_return_3y,
    resolve_target_quarter,
)


class ExpectedReturn3YCalculatorTest(unittest.TestCase):
    def test_calculates_expected_return_with_robust_target_pe(self) -> None:
        result = calculate_expected_return_3y(
            current_pe=10,
            pe_history=[10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 200],
            growth=GrowthInputs(profit_cagr_3y=0.2),
        )

        self.assertTrue(result.valid)
        self.assertIsNotNone(result.expected_return_3y)
        self.assertIsNotNone(result.mean_reversion_return_3y)
        self.assertLess(result.target_pe, 40)
        self.assertEqual(result.growth_source, "profit_cagr_3y")

    def test_returns_invalid_when_current_pe_non_positive(self) -> None:
        result = calculate_expected_return_3y(
            current_pe=0,
            pe_history=[10] * 12,
            growth=GrowthInputs(profit_cagr_3y=0.1),
        )

        self.assertFalse(result.valid)
        self.assertEqual(result.reason, "current_pe_non_positive")

    def test_returns_invalid_when_positive_pe_history_is_insufficient(self) -> None:
        result = calculate_expected_return_3y(
            current_pe=12,
            pe_history=[10, 11, None, 0, -1],
            growth=GrowthInputs(profit_cagr_3y=0.1),
        )

        self.assertFalse(result.valid)
        self.assertEqual(result.reason, "target_pe_missing")

    def test_caps_growth_rate_at_35_percent(self) -> None:
        result = calculate_expected_return_3y(
            current_pe=10,
            pe_history=[10] * 12,
            growth=GrowthInputs(profit_cagr_3y=0.5),
        )

        self.assertTrue(result.valid)
        self.assertEqual(result.g, 0.35)

    def test_uses_growth_priority_order(self) -> None:
        calculator = ExpectedReturn3YCalculator()
        growth = calculator.resolve_growth_rate(
            GrowthInputs(
                future_3y_consensus_cagr=None,
                profit_cagr_3y=0.15,
                profit_cagr_2y=0.2,
                profit_growth_1y=0.3,
            )
        )

        self.assertEqual(growth, (0.15, "profit_cagr_3y"))

    def test_rejects_growth_below_negative_100_percent(self) -> None:
        result = calculate_expected_return_3y(
            current_pe=10,
            pe_history=[10] * 12,
            growth=GrowthInputs(future_3y_consensus_cagr=-1.0),
        )

        self.assertFalse(result.valid)
        self.assertEqual(result.reason, "g_missing")

    def test_builds_consensus_growth_from_latest_report_per_org_and_quarter(self) -> None:
        report_df = pd.DataFrame(
            [
                {"org_name": "A", "quarter": "2017Q4", "report_date": "20150501", "eps": 15.0},
                {"org_name": "B", "quarter": "2017Q4", "report_date": "20150415", "eps": 18.0},
            ]
        )

        end_profit, cagr, org_count = build_consensus_growth_from_report_rc(
            report_df,
            target_quarter="2017Q4",
            base_eps=10.0,
        )

        self.assertEqual(end_profit, 16.5)
        self.assertEqual(org_count, 2)
        self.assertAlmostEqual(cagr, (16.5 / 10.0) ** (1 / 3) - 1)

    def test_resolves_target_quarter_from_base_quarter(self) -> None:
        self.assertEqual(resolve_target_quarter("2025Q4"), "2028Q4")


if __name__ == "__main__":
    unittest.main()
