import unittest
import subprocess
import sys
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest.mock import AsyncMock, patch

from streamlit.testing.v1 import AppTest

from src.reporting import DISCLAIMER
from src.verification.agent_answer import build_fact_catalog, compose_template, render_agent_template


class UITests(unittest.TestCase):
    def test_cold_start_loads_installed_mcp_without_preloaded_project_modules(self):
        script = Path(__file__).resolve().parents[1] / "src/ui.py"
        check = """
import sys
from pathlib import Path
from importlib.metadata import distribution
from streamlit.testing.v1 import AppTest

assert 'mcp' not in sys.modules
app = AppTest.from_file(sys.argv[1], default_timeout=15).run()
assert not app.exception, [error.message for error in app.exception]
assert app.title[0].value == 'FinSight'
import mcp
assert hasattr(mcp, 'Client')
assert Path(mcp.__file__).resolve() == distribution('mcp').locate_file('mcp/__init__.py').resolve()
app.run()
assert not app.exception, [error.message for error in app.exception]
"""
        with TemporaryDirectory() as directory:
            for cwd, flags in ((script.parents[1], []), (Path(directory), ["-I"])):
                with self.subTest(cwd=cwd, isolated=bool(flags)):
                    result = subprocess.run(
                        [sys.executable, *flags, "-c", check, str(script)],
                        cwd=cwd, capture_output=True, text=True, timeout=45,
                    )
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_empty_question_does_not_start_model(self):
        with patch("src.agents.runtime.run_mcp_orchestrator", new_callable=AsyncMock) as runner:
            app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "src/ui.py")).run()
            app.button[0].click().run()
        self.assertFalse(app.exception)
        runner.assert_not_awaited()
        self.assertIn("araştırma sorusu", app.error[0].value)
        self.assertTrue(any(DISCLAIMER == caption.value for caption in app.caption))

    def test_verified_answer_and_sources_are_visible(self):
        result = {
            "answer": "Revenue [Source 1]", "verification": {"supported": True},
            "evidence": [{"source_id": 1, "tool": "get_company_facts", "result": {
                "company": {"ticker": "AAPL"}, "records": [{"accn": "filing-id", "form": "10-K"}],
            }}],
        }
        with patch("src.agents.runtime.run_mcp_orchestrator", new_callable=AsyncMock, return_value=result) as runner:
            app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "src/ui.py")).run()
            app.selectbox[0].select("AAPL")
            app.text_area[0].input("Latest revenue?")
            app.button[0].click().run()
        self.assertFalse(app.exception)
        self.assertIn("Selected company: AAPL", runner.await_args.args[0])
        self.assertIn("Revenue [¹](#source-1)", [item.value for item in app.markdown])
        self.assertTrue(any('id="source-1"' in item.value for item in app.markdown))
        self.assertTrue(any("filing-id" in item.value for item in app.markdown))
        self.assertTrue(any(button.label == "Markdown olarak kaydet" for button in app.button))

    def test_withheld_answer_is_labelled_and_has_no_export_button(self):
        result = {"answer": None, "draft": "Unverified draft", "verification": {
            "supported": False, "issues": ["Unsupported claim"],
        }, "evidence": [{"source_id": 1, "tool": "get_company_facts", "result": {
            "company": {"ticker": "MSFT"}, "records": [{"value": 123, "unit": "USD", "tag": "RevenueTag"}],
        }}]}
        with patch("src.agents.runtime.run_mcp_orchestrator", new_callable=AsyncMock, return_value=result):
            app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "src/ui.py"), default_timeout=15).run()
            app.text_area[0].input("Explain risks")
            app.button[0].click().run()
        self.assertFalse(app.exception)
        self.assertTrue(any("doğrulama" in warning.value for warning in app.warning))
        self.assertFalse(any(button.label == "Markdown olarak kaydet" for button in app.button))
        self.assertEqual(app.dataframe[0].value.iloc[0]["Değer"], 123)
        self.assertTrue(any("tam araştırma notu değildir" in caption.value for caption in app.caption))

    def test_supporting_records_are_in_expander_and_prose_keeps_source_links(self):
        evidence = [{"source_id": 1, "tool": "get_company_facts", "result": {
            "company": {"ticker": "MSFT"}, "records": [{
                "metric": "revenue", "value": 331839000000, "unit": "USD",
                "fiscal_year": 2026, "end": "2026-06-30", "form": "10-K", "accn": "filing-id",
            }],
        }}]
        composition = {"kind": "answer", "text": (
            "Gelir {{1:records/0/value}} {{1:records/0/unit}} oldu. [Source 1]\n\n"
            "Bu değer ilgili mali yıla aittir. [Source 1]"
        ), "facts": ["1:records/0"]}
        answer = render_agent_template(compose_template(composition, build_fact_catalog(evidence)), evidence)
        result = {"answer": answer, "composition": composition, "evidence": evidence,
                  "verification": {"supported": True}}
        with patch("src.agents.runtime.run_mcp_orchestrator", new_callable=AsyncMock, return_value=result):
            app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "src/ui.py")).run()
            app.text_area[0].input("Geliri açıkla")
            app.button[0].click().run()
        self.assertFalse(app.exception)
        prose = next(item.value for item in app.markdown if item.value.startswith("Gelir "))
        self.assertIn("\n\n", prose)
        self.assertIn("[¹](#source-1)", prose)
        self.assertNotIn("MSFT | revenue", prose)
        details = next(item for item in app.expander if item.label == "Veri ve rapor ayrıntıları")
        self.assertIn("MSFT | revenue: 331839000000 USD", details.markdown[0].value)
        self.assertFalse(details.proto.expanded)

    def test_cited_report_context_is_visible_for_source_review(self):
        excerpt = "Customers outside China may change suppliers. <untrusted>"
        result = {"answer": "Report risk [Source 1]", "verification": {"supported": True}, "evidence": [
            {"source_id": 1, "tool": "search_filings", "result": {"matches": [{
                "text": "Short chunk", "context": {"text": excerpt},
                "metadata": {"form": "10-K", "accession_number": "filing-id"},
            }]}},
        ]}
        with patch("src.agents.runtime.run_mcp_orchestrator", new_callable=AsyncMock, return_value=result):
            app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "src/ui.py")).run()
            app.text_area[0].input("Explain risks")
            app.button[0].click().run()
        self.assertFalse(app.exception)
        self.assertIn(excerpt, [item.value for item in app.text])
        self.assertTrue(any(item.label == "Source 1 — kaynak metni" for item in app.expander))

    def test_backend_error_is_shown_without_crashing(self):
        with patch("src.agents.runtime.run_mcp_orchestrator", new_callable=AsyncMock,
                   side_effect=RuntimeError("Model unavailable")):
            app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "src/ui.py")).run()
            app.text_area[0].input("Revenue?")
            app.button[0].click().run()
        self.assertFalse(app.exception)
        self.assertTrue(any("Yanıt oluşturulamadı" in item.value for item in app.error))
        self.assertIn("Model unavailable", app.text[0].value)
