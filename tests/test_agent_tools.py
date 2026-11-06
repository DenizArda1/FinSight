import inspect
import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from src.tools.agentic_tools import (
    TOOL_FUNCTIONS, TOOL_SCHEMAS, get_agent_tool_schemas,
)
from src.tools.dispatcher import execute_tool
from src.tools.financial_metrics import get_company_facts
from src.utils.utils import load_yaml, save_json, save_yaml


class FinancialAgentToolTests(unittest.TestCase):
    def setUp(self):
        self.config = load_yaml(Path(__file__).resolve().parents[1] / "configs" / "metrics.yaml")
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        patcher = patch("src.tools.financial_metrics.PROJECT_ROOT", self.root)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.cik = "0000000001"
        self.processed = self.root / "financial_data" / "processed" / self.cik
        save_yaml(self.config, self.root / "configs" / "metrics.yaml")
        save_json({
            "cik": self.cik, "ticker": "TEST", "name": "Test Company",
            "filings": [{"form": "10-K", "reportDate": f"{year}-12-31"} for year in (2023, 2024, 2025)],
        }, self.root / "financial_data" / "raw" / self.cik / "manifest.json")
        self.revenue = []
        for year, value in ((2023, 100), (2024, 110), (2025, 121)):
            self.revenue.append({
                "cik": self.cik, "metric": "revenue", "unit": "USD", "value": value,
                "start": f"{year}-01-01", "end": f"{year}-12-31", "fiscal_year": year,
                "period_label": f"FY{year} (period end: {year}-12-31)", "form": "10-K",
                "tag": "Revenues", "filed": f"{year + 1}-02-01", "accn": f"report-{year}",
            })
        save_json(self.revenue, self.processed / "revenue.json")
        for metric, fraction in (("net_income", 0.25), ("operating_income", 0.3), ("gross_profit", 0.6)):
            save_json([
                {**row, "metric": metric, "tag": self.config["metrics"][metric]["tags"][0],
                 "value": row["value"] * fraction} for row in self.revenue
            ], self.processed / f"{metric}.json")

    def test_all_schemas_match_registered_signatures_and_config(self):
        self.assertEqual(len(TOOL_SCHEMAS), 6)
        self.assertEqual({schema["function"]["name"] for schema in TOOL_SCHEMAS}, set(TOOL_FUNCTIONS))
        json.dumps(TOOL_SCHEMAS)
        definitions = {schema["function"]["name"]: schema["function"] for schema in TOOL_SCHEMAS}
        for name, definition in definitions.items():
            parameters = inspect.signature(TOOL_FUNCTIONS[name]).parameters
            self.assertEqual(set(parameters), set(definition["parameters"]["properties"]))
            required = {key for key, value in parameters.items() if value.default is inspect.Parameter.empty}
            self.assertEqual(required, set(definition["parameters"]["required"]))
        self.assertEqual(set(definitions["get_company_facts"]["parameters"]["properties"]["concept"]["enum"]), set(self.config["metrics"]))
        self.assertEqual(set(definitions["compute_metrics"]["parameters"]["properties"]["metrics"]["items"]["enum"]), set(self.config["calculations"]))

    def test_facts_keep_requested_periods_and_provenance(self):
        result = execute_tool("get_company_facts", {"cik": self.cik, "concept": "revenue", "years": 2})
        self.assertEqual([{key: value for key, value in row.items() if key != "amendment_note"} for row in result["records"]], list(reversed(self.revenue[1:])))
        self.assertEqual(result["missing_period_ends"], [])
        self.assertEqual(result["company"]["ticker"], "TEST")

    def test_cost_categories_are_separate_source_preserving_base_metrics(self):
        for concept, value, tag in (
            ("cost_of_revenue", 40, "CostOfGoodsAndServicesSold"),
            ("operating_expenses", 20, "OperatingExpenses"),
        ):
            record = {**self.revenue[-1], "metric": concept, "value": value, "tag": tag}
            save_json([record], self.processed / f"{concept}.json")
            result = execute_tool("get_company_facts", {
                "cik": self.cik, "concept": concept, "years": 1,
            })
            self.assertEqual([{key: value for key, value in row.items() if key != "amendment_note"} for row in result["records"]], [record])
            self.assertEqual(result["missing_period_ends"], [])
            self.assertEqual(result["definition"]["description"], self.config["metrics"][concept]["description"])
            self.assertEqual(result["definition"]["tags"], self.config["metrics"][concept]["tags"])
        self.assertNotIn("CostOfGoodsSold", self.config["metrics"]["cost_of_revenue"]["tags"])
        self.assertEqual(self.config["metrics"]["operating_expenses"]["tags"], ["OperatingExpenses"])

    def test_missing_latest_period_is_not_replaced_with_older_record(self):
        save_json(self.revenue[:2], self.processed / "revenue.json")
        result = get_company_facts(self.cik, "revenue", years=1)
        self.assertEqual(result["records"], [])
        self.assertEqual(result["missing_period_ends"], ["2025-12-31"])

    def test_bad_cik_and_years_are_rejected_before_file_access(self):
        with patch("src.tools.financial_metrics.load_yaml") as load:
            for cik in (None, 1, "1", "../../file", "abcdefghij"):
                with self.subTest(cik=cik), self.assertRaises(ValueError):
                    get_company_facts(cik, "revenue")
            for years in (0, 6, True, "2", 2.5):
                with self.subTest(years=years), self.assertRaises(ValueError):
                    execute_tool("compute_metrics", {"cik": self.cik, "metrics": ["net_margin"], "years": years})
            load.assert_not_called()

    def test_concept_and_unit_are_restricted(self):
        for concept in ("net_margin", "../../secret", None):
            with self.subTest(concept=concept), self.assertRaisesRegex(ValueError, "Unknown base metric"):
                get_company_facts(self.cik, concept)
        with self.assertRaisesRegex(ValueError, "Unsupported unit"):
            get_company_facts(self.cik, "revenue", unit="USD/shares")

    def test_corrupt_prepared_identity_unit_and_duplicate_period_are_rejected(self):
        cases = [
            [{**self.revenue[0], "cik": "0000000002"}],
            [{**self.revenue[0], "metric": "net_income"}],
            [{**self.revenue[0], "unit": "USD/shares"}],
            [self.revenue[0], self.revenue[0]],
        ]
        for records in cases:
            save_json(records, self.processed / "revenue.json")
            with self.subTest(records=records), self.assertRaises(ValueError):
                get_company_facts(self.cik, "revenue")

    def test_missing_prepared_file_is_an_error_not_missing_financial_data(self):
        (self.processed / "revenue.json").unlink()
        with self.assertRaisesRegex(FileNotFoundError, "preparation pipeline"):
            get_company_facts(self.cik, "revenue")

    def test_all_calculations_preserve_sources_without_writing_files(self):
        before = {str(path): path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        with patch("src.tools.financial_metrics.get_company_facts", wraps=get_company_facts) as get:
            result = execute_tool("compute_metrics", {"cik": self.cik, "metrics": list(self.config["calculations"]), "years": 3})
        self.assertEqual(get.call_count, 4)
        rows = result["results"]
        for name, ratio in (("net_margin", 0.25), ("operating_margin", 0.3), ("gross_margin", 0.6)):
            self.assertEqual(len(rows[name]), 3)
            self.assertAlmostEqual(rows[name][0]["value"], ratio)
            self.assertEqual(rows[name][0]["inputs"]["revenue"]["accn"], "report-2025")
            self.assertEqual(rows[name][0]["fiscal_year"], 2025)
        self.assertEqual(len(rows["revenue_growth"]), 2)
        self.assertAlmostEqual(rows["revenue_growth"][0]["value"], 0.1)
        self.assertAlmostEqual(rows["revenue_cagr"][0]["value"], 0.1)
        self.assertEqual(rows["revenue_cagr"][0]["periods"], 2)
        self.assertEqual(result["warnings"], [])
        after = {str(path): path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        self.assertEqual(before, after)

    def test_missing_gross_profit_keeps_other_calculations_available(self):
        save_json([], self.processed / "gross_profit.json")
        result = execute_tool("compute_metrics", {"cik": self.cik, "metrics": ["gross_margin", "net_margin"]})
        self.assertEqual(result["results"]["gross_margin"], [])
        self.assertEqual(len(result["results"]["net_margin"]), 3)
        self.assertTrue(result["warnings"])

    def test_one_year_is_insufficient_for_growth_and_cagr(self):
        result = execute_tool("compute_metrics", {"cik": self.cik, "metrics": ["revenue_growth", "revenue_cagr"], "years": 1})
        self.assertEqual(result["results"], {"revenue_growth": [], "revenue_cagr": []})
        self.assertEqual(len(result["warnings"]), 2)

    def test_missing_year_does_not_shorten_the_requested_growth_window(self):
        save_json([self.revenue[0], self.revenue[2]], self.processed / "revenue.json")
        result = execute_tool("compute_metrics", {"cik": self.cik, "metrics": ["revenue_growth", "revenue_cagr"], "years": 3})
        self.assertEqual(result["results"], {"revenue_growth": [], "revenue_cagr": []})
        self.assertTrue(any("2024-12-31" in warning for warning in result["warnings"]))

    def test_invalid_calculations_are_rejected(self):
        for metrics in ([], "net_margin", [1], ["revenue"], ["net_margin", "net_margin"]):
            with self.subTest(metrics=metrics), self.assertRaises(ValueError):
                execute_tool("compute_metrics", {"cik": self.cik, "metrics": metrics})

    def test_model_supplied_values_cannot_override_calculation_inputs(self):
        with self.assertRaises(ValueError):
            execute_tool("compute_metrics", {"cik": self.cik, "metrics": ["net_margin"], "revenue": 999})

    def test_schema_rejects_invalid_search_before_executing_tool(self):
        with patch.dict(TOOL_FUNCTIONS, {"search_filings": unittest.mock.Mock()}) as functions:
            search = functions["search_filings"]
            for extra in ({"section": "Item 99"}, {"top_k": True}, {"fiscal_year": 0}, {"unknown": 1}):
                with self.subTest(extra=extra), self.assertRaises(ValueError):
                    execute_tool("search_filings", {"ticker": "AAPL", "query": "Risks", **extra})
            search.assert_not_called()


class AgentToolSelectionTests(unittest.TestCase):
    def test_selects_only_the_tools_for_each_agent_in_discovery_order(self):
        expected = {
            "financial_data": [
                "resolve_ticker_to_cik", "get_company_facts", "compute_metrics", "compare_companies",
            ],
            "filing_rag": [
                "resolve_ticker_to_cik", "search_filings", "get_filing_section",
            ],
        }
        for agent_name, names in expected.items():
            with self.subTest(agent_name=agent_name):
                selected = get_agent_tool_schemas(agent_name, TOOL_SCHEMAS)
                self.assertEqual([item["function"]["name"] for item in selected], names)
                reversed_selection = get_agent_tool_schemas(
                    agent_name, list(reversed(TOOL_SCHEMAS)),
                )
                self.assertEqual(
                    [item["function"]["name"] for item in reversed_selection],
                    list(reversed(names)),
                )

    def test_preserves_discovered_schema_and_does_not_share_mutable_objects(self):
        discovered = deepcopy(TOOL_SCHEMAS)
        discovered[0]["function"]["description"] = "Description from MCP"
        original = deepcopy(discovered)
        selected = get_agent_tool_schemas("financial_data", discovered)
        self.assertEqual(selected[0], discovered[0])
        selected[0]["function"]["description"] = "Changed by caller"
        selected[0]["function"]["parameters"]["properties"].clear()
        self.assertEqual(discovered, original)

    def test_rejects_unknown_agents(self):
        for agent_name in ("unknown", "writer", "", None, []):
            with self.subTest(agent_name=agent_name):
                with self.assertRaisesRegex(ValueError, "Unknown agent"):
                    get_agent_tool_schemas(agent_name, TOOL_SCHEMAS)

    def test_missing_required_tool_is_reported(self):
        discovered = [
            schema for schema in TOOL_SCHEMAS
            if schema["function"]["name"] != "compute_metrics"
        ]
        with self.assertRaisesRegex(ValueError, "Missing tools.*compute_metrics"):
            get_agent_tool_schemas("financial_data", discovered)
        self.assertEqual(len(get_agent_tool_schemas("filing_rag", discovered)), 3)
        with self.assertRaisesRegex(ValueError, "Missing tools"):
            get_agent_tool_schemas("financial_data", [])

    def test_rejects_duplicate_selected_tools(self):
        discovered = TOOL_SCHEMAS + [deepcopy(TOOL_SCHEMAS[0])]
        with self.assertRaisesRegex(ValueError, "Duplicate tool schema"):
            get_agent_tool_schemas("financial_data", discovered)

    def test_rejects_malformed_schema_inputs(self):
        for schemas in (None, {}, "tools", [None], [{}], [{"function": []}],
                        [{"function": {"name": None}}], [{"function": {"name": " "}}]):
            with self.subTest(schemas=schemas):
                with self.assertRaises(ValueError):
                    get_agent_tool_schemas("financial_data", schemas)


if __name__ == "__main__":
    unittest.main()
