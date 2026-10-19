from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import eval.run_eval as evaluation
from src.cli import main as cli_main, run_mcp_agent
from src.utils.utils import load_json, save_json, save_yaml


class FailingAgent:
    def __call__(self, question, config, return_details, trace):
        trace.append({"type": "tool", "name": "resolve_ticker_to_cik", "status": "completed",
                      "arguments": {"ticker": "AAPL"}, "result": {"cik": "0000320193"}})
        raise RuntimeError("Model unavailable after tool execution")


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.cases = [{"id": "case_a", "question": "Revenue?", "expected": {"value": 1}, "answer_language": "en"}]
        self.config = {"model": "test-model", "timeout_seconds": 1}
        silence = redirect_stdout(StringIO())
        silence.__enter__()
        self.addCleanup(silence.__exit__, None, None, None)

    @patch("eval.run_eval.run_agent")
    @patch("eval.run_eval.run_baseline")
    def test_baseline_never_claims_verification(self, baseline, agent):
        baseline.return_value = "Answer"
        row = evaluation.run_evaluation(self.cases, self.config, "baseline")[0]
        agent.assert_not_called()
        self.assertEqual(row["mode"], "baseline")
        self.assertEqual(row["verification"]["status"], "not_run")
        self.assertIsNone(row["review"])
        self.assertEqual(row["trace"], [])
        self.assertEqual(row["model"], "test-model")
        self.assertEqual(len(row["dataset_sha256"]), 64)

    @patch("eval.run_eval.run_agent")
    def test_agent_withheld_answer_remains_withheld_in_saved_result(self, agent):
        agent.return_value = {
            "answer": None, "status": "withheld", "draft": "Wrong answer", "candidate": "Candidate",
            "evidence": [{"source_id": 1}], "template": {"kind": "answer", "template": "Candidate"},
            "verification": {"status": "failed", "supported": False, "issues": ["Wrong source."]},
        }
        row = evaluation.run_evaluation(self.cases, self.config)[0]
        self.assertIsNone(row["answer"])
        self.assertEqual(row["draft"], "Wrong answer")
        self.assertEqual(row["status"], "withheld")
        self.assertEqual(row["verification"]["status"], "failed")
        self.assertEqual(row["evidence"], [{"source_id": 1}])

    @patch("eval.run_eval.run_agent", new_callable=FailingAgent)
    def test_trace_survives_agent_error(self, agent):
        row = evaluation.run_evaluation(self.cases, self.config)[0]
        self.assertEqual(row["status"], "error")
        self.assertEqual(row["trace"][0]["result"], {"cik": "0000320193"})
        self.assertIsNone(row["answer"])
        self.assertEqual(row["verification"]["status"], "not_run")

    @patch("eval.run_eval.run_baseline")
    def test_errors_continue_and_checkpoint_survives_keyboard_interrupt(self, baseline):
        cases = [{**self.cases[0], "id": str(index)} for index in range(4)]
        baseline.side_effect = ["First", RuntimeError("Unavailable"), "Third", KeyboardInterrupt()]
        with TemporaryDirectory() as directory:
            path = Path(directory) / "run.json"
            with self.assertRaises(KeyboardInterrupt):
                evaluation.run_evaluation(cases, self.config, "baseline", output_path=path)
            saved = load_json(path)
            self.assertEqual([row["status"] for row in saved], ["completed", "error", "completed"])
            self.assertEqual([row["answer"] for row in saved], ["First", None, "Third"])
            self.assertIsNone(saved[2]["error"])

    @patch("eval.run_eval.run_agent")
    def test_invalid_cases_and_existing_output_are_rejected_before_model(self, agent):
        for cases in ([], [None], [self.cases[0], self.cases[0]], [{"id": "x"}]):
            with self.subTest(cases=cases), self.assertRaises(ValueError):
                evaluation.run_evaluation(cases, self.config)
        with TemporaryDirectory() as directory:
            path = Path(directory) / "reviewed.json"
            save_json({"review": "Keep"}, path)
            with self.assertRaises(FileExistsError):
                evaluation.run_evaluation(self.cases, self.config, output_path=path)
            self.assertEqual(load_json(path), {"review": "Keep"})
        agent.assert_not_called()

    @patch("eval.run_eval.run_baseline", return_value="Answer")
    def test_cli_generates_separate_run_files_without_overwriting_reviewed_result(self, baseline):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "eval").mkdir()
            (root / "eval" / "golden_set.jsonl").write_text(
                '{"id":"x","question":"Question","expected":{},"answer_language":"en"}\n', encoding="utf-8",
            )
            save_yaml({"llm": self.config}, root / "configs" / "settings.yaml")
            old = root / "eval" / "results" / "single_agent.json"
            save_json({"review": "Keep"}, old)
            with patch.object(evaluation, "__file__", str(root / "eval" / "run_eval.py")), patch(
                "sys.argv", ["run_eval", "--mode", "baseline"],
            ):
                evaluation.main()
                evaluation.main()
            paths = list(old.parent.glob("baseline_*.json"))
            self.assertEqual(len(paths), 2)
            self.assertEqual(load_json(old), {"review": "Keep"})

    @patch("src.cli.load_yaml", return_value={"llm": {}})
    @patch("src.cli.run_mcp_agent")
    def test_user_cli_does_not_print_rejected_candidate(self, agent, config):
        agent.return_value = {"answer": None, "candidate": "Unsupported claim",
                              "verification": {"status": "failed", "issues": ["Wrong form."]}}
        output, errors = StringIO(), StringIO()
        with patch("sys.argv", ["cli", "Question"]), redirect_stdout(output), redirect_stderr(errors):
            with self.assertRaises(SystemExit) as raised:
                cli_main()
        self.assertEqual(raised.exception.code, 1)
        self.assertEqual(output.getvalue(), "")
        self.assertNotIn("Unsupported claim", errors.getvalue())
        self.assertIn("Answer withheld", errors.getvalue())

    @patch("src.cli.load_yaml", return_value={"llm": {}})
    @patch("src.cli.run_mcp_agent", side_effect=RuntimeError("Tool budget reached"))
    def test_cli_execution_failure_is_reported_without_an_answer(self, agent, config):
        output, errors = StringIO(), StringIO()
        with patch("sys.argv", ["cli", "Question"]), redirect_stdout(output), redirect_stderr(errors):
            with self.assertRaises(SystemExit) as raised:
                cli_main()
        self.assertEqual(raised.exception.code, 1)
        self.assertEqual(output.getvalue(), "")
        self.assertIn("Request failed", errors.getvalue())

    @patch("src.cli.load_yaml", return_value={"llm": {}})
    @patch("src.cli.run_mcp_agent", side_effect=ExceptionGroup(
        "MCP connection failed", [ExceptionGroup("Task failed", [OSError("Server unavailable")])],
    ))
    def test_user_cli_reports_grouped_connection_failure_without_an_answer(self, agent, config):
        output, errors = StringIO(), StringIO()
        with patch("sys.argv", ["cli", "Question"]), redirect_stdout(output), redirect_stderr(errors):
            with self.assertRaises(SystemExit) as raised:
                cli_main()
        self.assertEqual(raised.exception.code, 1)
        self.assertEqual(output.getvalue(), "")
        self.assertIn("Request failed", errors.getvalue())
        self.assertIn("OSError: Server unavailable", errors.getvalue())


class CLIConnectionTests(unittest.IsolatedAsyncioTestCase):
    @patch("src.cli.load_mcp_tool_schemas")
    @patch("src.cli.Client")
    @patch("src.cli.run_agent_async")
    async def test_connection_is_passed_to_agent_and_closed_after_answer(self, agent, client_class, load_schemas):
        connection = client_class.return_value
        client = connection.__aenter__.return_value
        agent.return_value = {"answer": "Verified answer"}
        load_schemas.return_value = [{"type": "function", "function": {"name": "resolve_ticker_to_cik"}}]

        result = await run_mcp_agent("Question", {"model": "test-model"}, verbose=True)

        agent.assert_awaited_once_with(
            "Question", {"model": "test-model"}, verbose=True,
            return_details=True, mcp_client=client, tool_schemas=load_schemas.return_value,
        )
        load_schemas.assert_awaited_once_with(client)
        self.assertEqual(result, agent.return_value)
        connection.__aexit__.assert_awaited_once_with(None, None, None)

    @patch("src.cli.load_mcp_tool_schemas", return_value=[])
    @patch("src.cli.Client")
    @patch("src.cli.run_agent_async", side_effect=RuntimeError("Model unavailable"))
    async def test_connection_is_closed_when_agent_fails(self, agent, client_class, load_schemas):
        connection = client_class.return_value
        connection.__aexit__.return_value = False

        with self.assertRaisesRegex(RuntimeError, "Model unavailable"):
            await run_mcp_agent("Question", {})

        connection.__aexit__.assert_awaited_once()
        self.assertIs(connection.__aexit__.await_args.args[0], RuntimeError)

    @patch("src.cli.load_mcp_tool_schemas", side_effect=ValueError("No tools exposed"))
    @patch("src.cli.Client")
    @patch("src.cli.run_agent_async")
    async def test_discovery_failure_closes_connection_before_agent_runs(self, agent, client_class, load_schemas):
        connection = client_class.return_value
        connection.__aexit__.return_value = False

        with self.assertRaisesRegex(ValueError, "No tools exposed"):
            await run_mcp_agent("Question", {})

        agent.assert_not_awaited()
        connection.__aexit__.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
