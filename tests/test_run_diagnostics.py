import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock, patch

from src.agents.runtime import run_mcp_orchestrator, save_run_trace


class RunDiagnosticsTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name) / "runs"
        patcher = patch("src.agents.runtime.TRACE_DIRECTORY", self.directory)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_records_are_unique_and_do_not_copy_secret_configuration(self):
        config = {"model": "test", "think": False, "api_key": "SECRET_KEY", "SEC_USER_AGENT": "SECRET_EMAIL"}
        trace = [{"type": "model", "input_tokens": 100, "output_tokens": 20}]
        first = Path(save_run_trace("Question", config, trace, {"answer": None}))
        second = Path(save_run_trace("Question", config, trace, error=ValueError("Bad response")))
        self.assertNotEqual(first, second)
        self.assertEqual(first.parent, self.directory)
        text = first.read_text()
        self.assertNotIn("SECRET", text)
        self.assertEqual(json.loads(text)["trace"], trace)
        self.assertEqual(json.loads(second.read_text())["error"]["type"], "ValueError")

    @patch("src.agents.runtime.Client")
    @patch("src.agents.runtime.load_mcp_tool_schemas", new_callable=AsyncMock, return_value=[])
    @patch("src.agents.runtime.run_orchestrator", new_callable=AsyncMock)
    async def test_runtime_error_keeps_trace_and_original_exception(self, run, schemas, client):
        client.return_value.__aexit__.return_value = False
        error = RuntimeError("Model disconnected")
        run.side_effect = error
        with self.assertRaises(RuntimeError) as raised:
            await run_mcp_orchestrator("Question", {"model": "test"})
        self.assertIs(raised.exception, error)
        paths = list(self.directory.glob("*.json"))
        self.assertEqual(len(paths), 1)
        self.assertEqual(json.loads(paths[0].read_text())["error"]["message"], "Model disconnected")

    @patch("src.agents.runtime.save_run_trace", side_effect=OSError("Disk full"))
    @patch("src.agents.runtime.Client")
    @patch("src.agents.runtime.load_mcp_tool_schemas", new_callable=AsyncMock, return_value=[])
    @patch("src.agents.runtime.run_orchestrator", new_callable=AsyncMock)
    async def test_logging_failure_does_not_discard_answer(self, run, schemas, client, save):
        run.return_value = {"answer": "Verified answer", "verification": {"supported": True}}
        result = await run_mcp_orchestrator("Question", {})
        self.assertEqual(result["answer"], "Verified answer")
        self.assertIn("Disk full", result["trace_error"])
