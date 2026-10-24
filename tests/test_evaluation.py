from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock, patch

import eval.run_eval as evaluation
from src.cli import main as cli_main, run_mcp_agent
from src.utils.utils import load_json, save_json, save_yaml


class FailingAgent:
    def __call__(self, question, config, return_details, trace):
        trace.append({"type": "tool", "name": "resolve_ticker_to_cik", "status": "completed",
                      "arguments": {"ticker": "AAPL"}, "result": {"cik": "0000320193"}})
        raise RuntimeError("Model unavailable after tool execution")


async def failing_mcp_agent(question, config, trace):
    trace.append({"type": "tool_discovery", "tools": ["resolve_ticker_to_cik"]})
    raise RuntimeError("Connection closed after discovery")


async def failing_orchestrator(question, config, trace):
    trace.append({"type": "agent", "agent": "planner", "status": "error"})
    raise RuntimeError("Planner unavailable")


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.cases = [{"id": "case_a", "question": "Revenue?", "expected": {"value": 1}, "answer_language": "en"}]
        self.config = {"model": "test-model", "timeout_seconds": 1}
        silence = redirect_stdout(StringIO())
        silence.__enter__()
        self.addCleanup(silence.__exit__, None, None, None)

    @patch("eval.run_eval.run_agent")
    @patch("eval.run_eval.run_mcp_agent", new_callable=AsyncMock)
    def test_mcp_transport_uses_application_runner_and_records_inputs(self, mcp_agent, direct):
        mcp_agent.return_value = {"answer": "Answer", "status": "completed",
                                  "verification": {"status": "passed"}}
        snapshot = {"source_sha256": "snapshot"}
        row = evaluation.run_evaluation(self.cases, self.config, transport="mcp", data_snapshot=snapshot)[0]
        direct.assert_not_called()
        mcp_agent.assert_awaited_once()
        self.assertEqual(mcp_agent.await_args.args, (self.cases[0]["question"], self.config))
        self.assertEqual(row["transport"], "mcp")
        self.assertEqual(row["data_snapshot"], snapshot)
        self.assertEqual(row["answer"], "Answer")

    @patch("eval.run_eval.run_agent")
    @patch("eval.run_eval.run_mcp_agent", new_callable=AsyncMock)
    @patch("eval.run_eval.run_mcp_orchestrator", new_callable=AsyncMock)
    def test_multi_agent_uses_orchestrator(self, orchestrator, single, direct):
        orchestrator.return_value = {
            "answer": "Mock answer", "verification": {"status": "passed"},
            "evidence": [{"source_id": 1}], "composition": {"kind": "answer"},
        }
        snapshot = {"source_sha256": "snapshot"}
        row = evaluation.run_evaluation(
            self.cases, self.config, mode="multi_agent", transport="mcp", data_snapshot=snapshot,
        )[0]

        orchestrator.assert_awaited_once_with(self.cases[0]["question"], self.config, trace=[])
        single.assert_not_called()
        direct.assert_not_called()
        self.assertEqual(row["answer"], "Mock answer")
        self.assertEqual(row["status"], "completed")
        self.assertEqual(row["mode"], "multi_agent")
        self.assertEqual(row["transport"], "mcp")
        self.assertEqual(row["data_snapshot"], snapshot)
        self.assertEqual(row["verification"], {"status": "passed"})
        self.assertEqual(row["evidence"], orchestrator.return_value["evidence"])
        self.assertEqual(row["composition"], orchestrator.return_value["composition"])

    @patch("eval.run_eval.run_mcp_orchestrator", new_callable=AsyncMock)
    def test_multi_agent_withheld_answer_is_saved_without_publishing_draft(self, orchestrator):
        orchestrator.return_value = {
            "answer": None, "draft": "Unsupported draft", "evidence": [{"source_id": 1}],
            "verification": {"status": "failed", "supported": False, "issues": ["Missing evidence."]},
        }
        with TemporaryDirectory() as directory:
            output = Path(directory) / "results.json"
            rows = evaluation.run_evaluation(
                self.cases, self.config, mode="multi_agent", transport="mcp", output_path=output,
            )
            self.assertEqual(load_json(output), rows)
        row = rows[0]
        self.assertIsNone(row["answer"])
        self.assertIsNone(row["error"])
        self.assertEqual(row["status"], "withheld")
        self.assertEqual(row["draft"], "Unsupported draft")
        self.assertEqual(row["verification"], orchestrator.return_value["verification"])
        self.assertEqual(row["evidence"], orchestrator.return_value["evidence"])

    @patch("eval.run_eval.run_mcp_orchestrator", side_effect=failing_orchestrator)
    def test_multi_agent_error_preserves_trace_and_continues(self, orchestrator):
        cases = [self.cases[0], {**self.cases[0], "id": "case_b"}]
        rows = evaluation.run_evaluation(cases, self.config, mode="multi_agent", transport="mcp")
        self.assertEqual(orchestrator.await_count, 2)
        self.assertEqual([row["id"] for row in rows], ["case_a", "case_b"])
        for row in rows:
            self.assertEqual(row["status"], "error")
            self.assertIsNone(row["answer"])
            self.assertEqual(row["error"], {"type": "RuntimeError", "message": "Planner unavailable"})
            self.assertEqual(row["trace"], [{"type": "agent", "agent": "planner", "status": "error"}])
            self.assertEqual(row["verification"]["status"], "not_run")
            self.assertEqual(row["transport"], "mcp")

    @patch("eval.run_eval.run_mcp_orchestrator", new_callable=AsyncMock)
    def test_multi_agent_direct_transport_is_rejected_before_execution(self, orchestrator):
        with self.assertRaisesRegex(ValueError, "requires MCP transport"):
            evaluation.run_evaluation(self.cases, self.config, mode="multi_agent", transport="direct")
        orchestrator.assert_not_called()

    @patch("eval.run_eval.run_mcp_agent", side_effect=failing_mcp_agent)
    def test_mcp_error_keeps_discovery_trace(self, mcp_agent):
        row = evaluation.run_evaluation(self.cases, self.config, transport="mcp")[0]
        self.assertEqual(row["status"], "error")
        self.assertEqual(row["transport"], "mcp")
        self.assertEqual(row["trace"][0]["type"], "tool_discovery")
        self.assertIsNone(row["answer"])

    def test_invalid_transport_and_mcp_baseline_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unknown tool transport"):
            evaluation.run_evaluation(self.cases, self.config, transport="invalid")
        with self.assertRaisesRegex(ValueError, "Baseline has no tools"):
            evaluation.run_evaluation(self.cases, self.config, mode="baseline", transport="mcp")

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

    def test_invalid_dataset_metadata_and_nonfinite_expectations_are_rejected(self):
        for changes in ({"id": " case_a"}, {"category": " "}, {"category": 1},
                        {"expected": {"value": float("nan")}},
                        {"expected": {"inputs": [float("inf")]}}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                evaluation.validate_cases([{**self.cases[0], **changes}])

    @patch("eval.run_eval.run_evaluation")
    @patch("eval.run_eval.capture_snapshot")
    @patch("eval.run_eval.load_yaml", side_effect=AssertionError("Offline validation must not load model settings"))
    def test_validate_only_selects_cases_without_models_snapshots_or_output_files(self, config, snapshot, runner):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "eval").mkdir()
            dataset = root / "eval" / "golden_set.jsonl"
            dataset.write_text(
                '{"id":"a","question":"Revenue?","category":"numeric","expected":{"value":1},"answer_language":"en"}\n'
                '{"id":"b","question":"Gelir?","category":"numeric","expected":{"value":1},"answer_language":"tr"}\n',
                encoding="utf-8",
            )
            for mode_args in ([], ["--mode", "multi_agent", "--transport", "mcp"]):
                with self.subTest(arguments=mode_args):
                    output = StringIO()
                    with patch.object(evaluation, "__file__", str(root / "eval" / "run_eval.py")), patch(
                        "sys.argv", ["run_eval", "--validate-only", "--case", "b", *mode_args],
                    ), redirect_stdout(output):
                        evaluation.main()
                    self.assertIn("Validated 1 evaluation cases", output.getvalue())
                    self.assertIn("Languages: tr=1", output.getvalue())
                    self.assertIn("structure only", output.getvalue())
            self.assertEqual(list(root.rglob("*")), [root / "eval", dataset])
        runner.assert_not_called()
        snapshot.assert_not_called()
        config.assert_not_called()

    @patch("eval.run_eval.run_evaluation")
    @patch("eval.run_eval.capture_snapshot")
    @patch("eval.run_eval.load_jsonl")
    def test_eval_cli_rejects_multi_agent_without_mcp_before_loading_data(self, dataset, snapshot, runner):
        for transport_args in ([], ["--transport", "direct"]):
            with self.subTest(arguments=transport_args):
                errors = StringIO()
                with patch("sys.argv", ["run_eval", "--mode", "multi_agent", *transport_args]), redirect_stderr(errors):
                    with self.assertRaises(SystemExit) as raised:
                        evaluation.main()
                self.assertEqual(raised.exception.code, 2)
                self.assertIn("requires --transport mcp", errors.getvalue())
        dataset.assert_not_called()
        snapshot.assert_not_called()
        runner.assert_not_called()

    @patch("eval.run_eval.run_evaluation", return_value=[])
    @patch("eval.run_eval.capture_snapshot", return_value={"source_sha256": "snapshot"})
    @patch("eval.run_eval.load_yaml")
    @patch("eval.run_eval.load_jsonl")
    def test_eval_cli_forwards_multi_agent_settings_and_filename(self, dataset, config, snapshot, runner):
        dataset.return_value = self.cases
        config.return_value = {"llm": self.config}
        with patch("sys.argv", ["run_eval", "--mode", "multi_agent", "--transport", "mcp"]):
            evaluation.main()
        runner.assert_called_once()
        self.assertEqual(runner.call_args.args, (self.cases, self.config))
        arguments = runner.call_args.kwargs
        self.assertEqual(arguments["mode"], "multi_agent")
        self.assertEqual(arguments["transport"], "mcp")
        self.assertEqual(arguments["data_snapshot"], snapshot.return_value)
        self.assertTrue(arguments["output_path"].name.startswith("multi_agent_mcp_"))
        self.assertEqual(arguments["output_path"].suffix, ".json")

    @patch("eval.run_eval.run_evaluation")
    @patch("eval.run_eval.load_yaml")
    def test_validate_only_rejects_unknown_ids_and_invalid_json_before_execution(self, config, runner):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "eval").mkdir()
            dataset = root / "eval" / "golden_set.jsonl"
            for content, arguments, message in (
                ('{"id":"a","question":"Q","expected":{},"answer_language":"en"}\n',
                 ["--case", "missing"], "Unknown case IDs"),
                ('{bad json}\n', [], "Expecting property name"),
            ):
                with self.subTest(arguments=arguments):
                    dataset.write_text(content, encoding="utf-8")
                    errors = StringIO()
                    with patch.object(evaluation, "__file__", str(root / "eval" / "run_eval.py")), patch(
                        "sys.argv", ["run_eval", "--validate-only", *arguments],
                    ), redirect_stderr(errors), self.assertRaises(SystemExit) as raised:
                        evaluation.main()
                    self.assertEqual(raised.exception.code, 2)
                    self.assertIn(message, errors.getvalue())
        runner.assert_not_called()
        config.assert_not_called()

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

    @patch("src.cli.load_yaml", return_value={"llm": {"model": "test-model"}})
    @patch("src.cli.run_mcp_agent", new_callable=AsyncMock)
    @patch("src.cli.run_mcp_orchestrator", new_callable=AsyncMock)
    def test_user_cli_routes_each_mode_to_its_runner(self, multi, single, config):
        for mode_args, selected, unused in (
            ([], single, multi),
            (["--mode", "single_agent"], single, multi),
            (["--mode", "multi_agent"], multi, single),
        ):
            with self.subTest(arguments=mode_args):
                single.reset_mock()
                multi.reset_mock()
                selected.return_value = {"answer": "Mock answer", "evidence": []}
                output = StringIO()
                with patch("sys.argv", ["cli", "Question", "--verbose", *mode_args]), redirect_stdout(output):
                    cli_main()
                selected.assert_awaited_once_with("Question", {"model": "test-model"}, verbose=True)
                unused.assert_not_called()
                self.assertEqual(output.getvalue().strip(), "Mock answer")

    @patch("src.cli.load_yaml", return_value={"llm": {}})
    @patch("src.cli.run_mcp_agent", new_callable=AsyncMock)
    @patch("src.cli.run_mcp_orchestrator", new_callable=AsyncMock)
    def test_user_cli_multi_agent_withheld_and_error_never_print_answer(self, multi, single, config):
        for outcome in ("withheld", "error"):
            with self.subTest(outcome=outcome):
                multi.reset_mock()
                multi.return_value = {
                    "answer": None, "draft": "Unsupported draft",
                    "verification": {"status": "failed", "issues": ["Missing evidence."]},
                }
                multi.side_effect = RuntimeError("Planner unavailable") if outcome == "error" else None
                output, errors = StringIO(), StringIO()
                with patch("sys.argv", ["cli", "Question", "--mode", "multi_agent", "--verbose"]), redirect_stdout(output), redirect_stderr(errors):
                    with self.assertRaises(SystemExit) as raised:
                        cli_main()
                self.assertEqual(raised.exception.code, 1)
                multi.assert_awaited_once()
                single.assert_not_called()
                self.assertEqual(output.getvalue(), "")
                self.assertNotIn("Unsupported draft", errors.getvalue())
                if outcome == "withheld":
                    self.assertIn("Answer withheld", errors.getvalue())
                    self.assertIn("Missing evidence.", errors.getvalue())
                else:
                    self.assertIn("Request failed", errors.getvalue())
                    self.assertIn("Planner unavailable", errors.getvalue())

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
    @patch("src.agents.runtime.load_mcp_tool_schemas")
    @patch("src.agents.runtime.Client")
    @patch("src.agents.runtime.run_agent_async")
    async def test_connection_is_passed_to_agent_and_closed_after_answer(self, agent, client_class, load_schemas):
        connection = client_class.return_value
        client = connection.__aenter__.return_value
        agent.return_value = {"answer": "Verified answer"}
        load_schemas.return_value = [{"type": "function", "function": {"name": "resolve_ticker_to_cik"}}]

        result = await run_mcp_agent("Question", {"model": "test-model"}, verbose=True)

        agent.assert_awaited_once_with(
            "Question", {"model": "test-model"}, verbose=True,
            return_details=True, trace=None, mcp_client=client, tool_schemas=load_schemas.return_value,
        )
        load_schemas.assert_awaited_once_with(client)
        self.assertEqual(result, agent.return_value)
        connection.__aexit__.assert_awaited_once_with(None, None, None)

    @patch("src.agents.runtime.load_mcp_tool_schemas", return_value=[])
    @patch("src.agents.runtime.Client")
    @patch("src.agents.runtime.run_agent_async", side_effect=RuntimeError("Model unavailable"))
    async def test_connection_is_closed_when_agent_fails(self, agent, client_class, load_schemas):
        connection = client_class.return_value
        connection.__aexit__.return_value = False

        with self.assertRaisesRegex(RuntimeError, "Model unavailable"):
            await run_mcp_agent("Question", {})

        connection.__aexit__.assert_awaited_once()
        self.assertIs(connection.__aexit__.await_args.args[0], RuntimeError)

    @patch("src.agents.runtime.load_mcp_tool_schemas", side_effect=ValueError("No tools exposed"))
    @patch("src.agents.runtime.Client")
    @patch("src.agents.runtime.run_agent_async")
    async def test_discovery_failure_closes_connection_before_agent_runs(self, agent, client_class, load_schemas):
        connection = client_class.return_value
        connection.__aexit__.return_value = False

        with self.assertRaisesRegex(ValueError, "No tools exposed"):
            await run_mcp_agent("Question", {})

        agent.assert_not_awaited()
        connection.__aexit__.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
