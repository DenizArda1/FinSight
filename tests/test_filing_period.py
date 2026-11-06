import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import chromadb

from src.agents.specialist import run_specialist
from src.rag.retrieval import get_latest_report_metadata
from src.tools.agentic_tools import TOOL_SCHEMAS
from src.tools.report_search import search_company_reports
from src.utils.utils import save_json


def model_search(arguments):
    return {"role": "assistant", "content": "", "tool_calls": [
        {"function": {"name": "search_filings", "arguments": arguments}},
    ]}


async def call_local_report_tool(client, name, arguments):
    if name != "search_filings":
        raise ValueError("Unexpected test tool")
    return search_company_reports(**arguments)


class FilingPeriodIntegrationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.company = {"ticker": "NVDA", "name": "NVIDIA", "cik": "0001045810"}
        client = chromadb.EphemeralClient()
        name = "period-test-" + uuid4().hex
        self.collection = client.create_collection(name, embedding_function=None)
        self.addCleanup(client.delete_collection, name)
        for year, text, vector in ((2026, "Export restrictions may reduce demand.", [0.0, 1.0]),
                                   (2027, "New report risk.", [1.0, 0.0])):
            accession = f"0001045810-{str(year)[2:]}-000001"
            report_date = f"{year}-01-31"
            url = f"https://example.com/nvda/{year}"
            directory = self.root / "financial_data/processed/0001045810/filings" / accession
            document = {"company": self.company, "text": "Intro|" + text + "|Next",
                        "filing": {"accessionNumber": accession, "form": "10-K", "fiscal_year": year,
                                   "reportDate": report_date, "url": url}}
            section = {"section": "Item 1A", "text": text, "start": 6, "end": 6 + len(text)}
            save_json(document, directory / "text.json")
            save_json([section], directory / "sections.json")
            metadata = {"ticker": "NVDA", "cik": "0001045810", "fiscal_year": year,
                        "accession_number": accession, "form": "10-K", "report_date": report_date,
                        "source_url": url, "section": "Item 1A", "start": section["start"],
                        "end": section["end"], "section_start": section["start"], "section_end": section["end"]}
            self.collection.add(ids=[accession + ":1"], documents=[text], metadatas=[metadata], embeddings=[vector])
        patchers = [
            patch("src.rag.index_identity.verify_collection_identity", return_value={"embedding_digest": "test"}),
            patch("src.tools.report_search.PROJECT_ROOT", self.root),
            patch("src.tools.report_search.resolve_company", return_value=self.company),
            patch("src.tools.report_search.load_yaml", return_value={"embedding": {}, "vector_store": {}}),
            patch("src.tools.report_search.get_vector_collection", return_value=self.collection),
            patch("src.rag.retrieval.embed_text", return_value=[1.0, 0.0]),
        ]
        for patcher in patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

    async def test_latest_attempt_is_rejected_then_explicit_year_selects_older_report(self):
        self.assertEqual(get_latest_report_metadata(self.collection, "NVDA")["fiscal_year"], 2027)
        task = {"id": "risks", "agent": "filing_rag", "instruction": "Read NVIDIA FY2026 risks.", "fiscal_year": 2026}
        base = {"ticker": "NVDA", "query": "export risk", "section": "Item 1A", "top_k": 1}
        with patch("src.agents.specialist.send_chat_request", side_effect=[
            model_search({**base, "latest": True}),
            model_search({**base, "fiscal_year": 2026}),
            {"role": "assistant", "content": "Requested-year evidence retrieved."},
        ]), patch("src.agents.specialist.call_mcp_tool", new_callable=AsyncMock, side_effect=call_local_report_tool) as call_tool:
            result = await run_specialist(task, {}, object(), TOOL_SCHEMAS)
        self.assertEqual(call_tool.await_count, 1)
        self.assertEqual(call_tool.await_args.args[2]["fiscal_year"], 2026)
        events = [event for event in result["trace"] if event["type"] == "tool"]
        self.assertEqual([event["status"] for event in events], ["error", "completed"])
        self.assertIn("FY2026", events[0]["result"]["error"]["message"])
        matches = events[1]["result"]["matches"]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["metadata"]["fiscal_year"], 2026)
        self.assertEqual(matches[0]["context"]["text"], "Export restrictions may reduce demand.")

    async def test_missing_requested_year_does_not_fall_back_to_latest(self):
        task = {"id": "risks", "agent": "filing_rag", "instruction": "Read NVIDIA FY2025 risks.", "fiscal_year": 2025}
        with patch("src.agents.specialist.send_chat_request", side_effect=[
            model_search({"ticker": "NVDA", "query": "risk", "fiscal_year": 2025, "section": "Item 1A"}),
            {"role": "assistant", "content": "No matching report in the requested year."},
        ]), patch("src.agents.specialist.call_mcp_tool", new_callable=AsyncMock, side_effect=call_local_report_tool):
            result = await run_specialist(task, {}, object(), TOOL_SCHEMAS)
        event = next(event for event in result["trace"] if event["type"] == "tool")
        self.assertEqual(event["status"], "completed")
        self.assertEqual(event["result"]["matches"], [])
        self.assertEqual(event["result"]["fiscal_year"], 2025)


if __name__ == "__main__":
    unittest.main()
