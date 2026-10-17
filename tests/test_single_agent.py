from copy import deepcopy
import json
import unittest
from unittest.mock import call, patch

from src.agents.single_agent import run_agent
from src.tools.agentic_tools import TOOL_SCHEMAS


def approved_answer(question, draft, trace, config):
    return {"answer": draft, "draft": draft, "candidate": draft, "evidence": [],
            "verification": {"status": "passed", "supported": True, "issues": []}}


class RecordingChat:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.requests = []

    def __call__(self, messages, config, tools):
        self.requests.append({"messages": deepcopy(messages), "config": config, "tools": tools})
        return next(self.responses)


class SingleAgentTests(unittest.TestCase):
    def setUp(self):
        self.config = {"model": "test-model"}
        chat_patcher = patch("src.agents.single_agent.send_chat_request")
        self.chat = chat_patcher.start()
        self.addCleanup(chat_patcher.stop)
        tool_patcher = patch("src.agents.single_agent.execute_tool")
        self.tool = tool_patcher.start()
        self.addCleanup(tool_patcher.stop)
        verification_patcher = patch("src.agents.single_agent.finalize_agent_answer", side_effect=approved_answer)
        self.finalizer = verification_patcher.start()
        self.addCleanup(verification_patcher.stop)

    def test_final_answer_returns_without_running_tools(self):
        self.chat.return_value = {"role": "assistant", "content": "Please specify a company."}
        self.assertEqual(run_agent("Which company?", self.config), "Please specify a company.")
        self.chat.assert_called_once()
        self.tool.assert_not_called()

    def test_multiple_tools_are_run_before_next_model_request(self):
        tool_message = {
            "role": "assistant", "content": "", "thinking": "Resolve both companies.",
            "tool_calls": [
                {"function": {"name": "resolve_ticker_to_cik", "arguments": {"ticker": "NVDA"}}},
                {"function": {"name": "resolve_ticker_to_cik", "arguments": {"ticker": "AAPL"}}},
            ],
        }
        recorder = RecordingChat([tool_message, {"role": "assistant", "content": "Resolved both companies."}])
        self.chat.side_effect = recorder
        self.tool.side_effect = [{"ticker": "NVDA", "name": "Şirket"}, {"ticker": "AAPL"}]

        answer = run_agent("Resolve NVDA and AAPL.", self.config)

        self.assertEqual(answer, "Resolved both companies.")
        self.assertEqual(self.tool.call_args_list, [
            call("resolve_ticker_to_cik", {"ticker": "NVDA"}),
            call("resolve_ticker_to_cik", {"ticker": "AAPL"}),
        ])
        self.assertEqual(len(recorder.requests[0]["messages"]), 2)
        history = recorder.requests[1]["messages"]
        self.assertEqual([message["role"] for message in history], ["system", "user", "assistant", "tool", "tool"])
        self.assertEqual(history[2], tool_message)
        self.assertEqual(history[3]["tool_name"], "resolve_ticker_to_cik")
        self.assertEqual(json.loads(history[3]["content"]), {"ticker": "NVDA", "name": "Şirket"})
        self.assertEqual(json.loads(history[4]["content"]), {"ticker": "AAPL"})
        self.assertEqual(recorder.requests[1]["tools"], TOOL_SCHEMAS)

    def test_final_answer_on_last_allowed_step_is_accepted(self):
        self.chat.side_effect = [
            {"role": "assistant", "tool_calls": [{"function": {"name": "resolve_ticker_to_cik", "arguments": {"ticker": "NVDA"}}}]},
            {"role": "assistant", "content": "Done."},
        ]
        self.tool.return_value = {"cik": "0001045810"}
        self.assertEqual(run_agent("Resolve NVDA.", self.config, max_steps=2), "Done.")
        self.assertEqual(self.chat.call_count, 2)

    def test_repeated_tool_requests_stop_at_step_limit(self):
        self.chat.return_value = {
            "role": "assistant", "tool_calls": [{"function": {"name": "resolve_ticker_to_cik", "arguments": {"ticker": "NVDA"}}}],
        }
        self.tool.return_value = {"cik": "0001045810"}
        with self.assertRaisesRegex(RuntimeError, "maximum number of steps"):
            run_agent("Resolve NVDA.", self.config, max_steps=2)
        self.assertEqual(self.chat.call_count, 2)

    def test_invalid_inputs_are_rejected_before_requests(self):
        for question in (None, 1, "", "  "):
            with self.subTest(question=question), self.assertRaises(ValueError):
                run_agent(question, self.config)
        for max_steps in (None, True, 0, -1, 1.5, "6"):
            with self.subTest(max_steps=max_steps), self.assertRaises(ValueError):
                run_agent("Question", self.config, max_steps=max_steps)
        for max_tool_calls in (None, True, 0, -1, 1.5, "10"):
            with self.subTest(max_tool_calls=max_tool_calls), self.assertRaises(ValueError):
                run_agent("Question", self.config, max_tool_calls=max_tool_calls)
        self.chat.assert_not_called()
        self.tool.assert_not_called()

    def test_tool_budget_stops_extra_calls_in_one_response(self):
        self.chat.return_value = {
            "role": "assistant",
            "tool_calls": [
                {"function": {"name": "resolve_ticker_to_cik", "arguments": {"ticker": ticker}}}
                for ticker in ("NVDA", "AAPL", "MSFT")
            ],
        }
        self.tool.return_value = {"cik": "0001045810"}
        with self.assertRaisesRegex(RuntimeError, "maximum number of tool calls"):
            run_agent("Resolve three companies.", self.config, max_tool_calls=2)
        self.assertEqual(self.tool.call_args_list, [
            call("resolve_ticker_to_cik", {"ticker": "NVDA"}),
            call("resolve_ticker_to_cik", {"ticker": "AAPL"}),
        ])
        self.chat.assert_called_once()

    def test_tool_budget_is_shared_across_model_requests(self):
        self.chat.return_value = {
            "role": "assistant",
            "tool_calls": [{"function": {"name": "resolve_ticker_to_cik", "arguments": {"ticker": "NVDA"}}}],
        }
        self.tool.return_value = {"cik": "0001045810"}
        with self.assertRaisesRegex(RuntimeError, "maximum number of tool calls"):
            run_agent("Resolve NVDA.", self.config, max_tool_calls=2)
        self.assertEqual(self.tool.call_count, 2)
        self.assertEqual(self.chat.call_count, 3)

    def test_final_answer_is_allowed_after_using_entire_tool_budget(self):
        self.chat.side_effect = [
            {"role": "assistant", "tool_calls": [{"function": {"name": "resolve_ticker_to_cik", "arguments": {"ticker": "NVDA"}}}]},
            {"role": "assistant", "content": "Done."},
        ]
        self.tool.return_value = {"cik": "0001045810"}
        self.assertEqual(run_agent("Resolve NVDA.", self.config, max_tool_calls=1), "Done.")
        self.tool.assert_called_once()
        self.assertEqual(self.chat.call_count, 2)

    def test_blank_and_non_text_final_answers_are_rejected(self):
        for content in (None, "", " \n ", 5):
            self.chat.return_value = {"role": "assistant", "content": content}
            with self.subTest(content=content), self.assertRaisesRegex(ValueError, "Final answer"):
                run_agent("Question", self.config)
        self.tool.assert_not_called()

    def test_malformed_tool_calls_are_rejected(self):
        for calls in (None, {}, "invalid", [None], [{}], [{"function": None}]):
            self.chat.return_value = {"role": "assistant", "tool_calls": calls}
            with self.subTest(calls=calls), self.assertRaises(ValueError):
                run_agent("Question", self.config)
        self.tool.assert_not_called()

    def test_tool_error_is_returned_to_model_and_corrected(self):
        recorder = RecordingChat([
            {"role": "assistant", "tool_calls": [{"function": {"name": "unknown_tool", "arguments": {}}}]},
            {"role": "assistant", "tool_calls": [{"function": {"name": "resolve_ticker_to_cik", "arguments": {"ticker": "NVDA"}}}]},
            {"role": "assistant", "content": "CIK: 0001045810."},
        ])
        self.chat.side_effect = recorder
        self.tool.side_effect = [ValueError("Unknown tool: unknown_tool"), {"cik": "0001045810"}]

        self.assertEqual(run_agent("Resolve NVDA.", self.config), "CIK: 0001045810.")

        error_message = recorder.requests[1]["messages"][-1]
        self.assertEqual(error_message["role"], "tool")
        self.assertEqual(error_message["tool_name"], "unknown_tool")
        self.assertEqual(json.loads(error_message["content"]), {
            "error": {"type": "ValueError", "message": "Unknown tool: unknown_tool"},
        })
        self.assertEqual(self.tool.call_args_list, [
            call("unknown_tool", {}),
            call("resolve_ticker_to_cik", {"ticker": "NVDA"}),
        ])
        self.assertEqual(json.loads(recorder.requests[2]["messages"][-1]["content"]), {"cik": "0001045810"})

    def test_expected_tool_errors_are_returned_as_error_results(self):
        for error in (TypeError("Missing required argument: ticker"), FileNotFoundError("Prepared data is unavailable")):
            with self.subTest(error=type(error).__name__):
                recorder = RecordingChat([
                    {"role": "assistant", "tool_calls": [{"function": {"name": "resolve_ticker_to_cik", "arguments": {}}}]},
                    {"role": "assistant", "content": "Required data is unavailable."},
                ])
                self.chat.side_effect = recorder
                self.tool.side_effect = error
                self.assertEqual(run_agent("Question", self.config), "Required data is unavailable.")
                self.assertEqual(json.loads(recorder.requests[1]["messages"][-1]["content"]), {
                    "error": {"type": type(error).__name__, "message": str(error)},
                })

    def test_failed_tool_attempts_consume_tool_budget(self):
        self.chat.return_value = {
            "role": "assistant", "tool_calls": [{"function": {"name": "unknown_tool", "arguments": {}}}],
        }
        self.tool.side_effect = ValueError("Unknown tool: unknown_tool")
        with self.assertRaisesRegex(RuntimeError, "maximum number of tool calls"):
            run_agent("Question", self.config, max_tool_calls=2)
        self.assertEqual(self.tool.call_count, 2)
        self.assertEqual(self.chat.call_count, 3)

    def test_unexpected_tool_failure_is_propagated(self):
        self.chat.return_value = {
            "role": "assistant", "tool_calls": [{"function": {"name": "resolve_ticker_to_cik", "arguments": {}}}],
        }
        self.tool.side_effect = RuntimeError("Unexpected failure")
        with self.assertRaisesRegex(RuntimeError, "Unexpected failure"):
            run_agent("Question", self.config)
        self.chat.assert_called_once()

    def test_model_failure_is_propagated(self):
        self.chat.side_effect = RuntimeError("Model unavailable")
        with self.assertRaisesRegex(RuntimeError, "Model unavailable"):
            run_agent("Question", self.config)
        self.tool.assert_not_called()

    def test_failed_verification_never_returns_the_draft(self):
        self.chat.return_value = {"role": "assistant", "content": "Wrong answer."}
        self.finalizer.side_effect = None
        self.finalizer.return_value = {
            "answer": None, "draft": "Wrong answer.", "evidence": [],
            "verification": {"status": "failed", "supported": False, "issues": ["Wrong language."]},
        }
        result = run_agent("Question", self.config, return_details=True)
        self.assertIsNone(result["answer"])
        self.assertEqual(result["status"], "withheld")
        with self.assertRaisesRegex(RuntimeError, "did not pass verification"):
            run_agent("Question", self.config)

    def test_tool_evidence_reaches_verification_and_trace_is_preserved(self):
        self.chat.side_effect = [
            {"role": "assistant", "thinking": "Private reasoning", "tool_calls": [
                {"function": {"name": "resolve_ticker_to_cik", "arguments": {"ticker": "NVDA"}}},
            ]},
            {"role": "assistant", "content": "Done."},
        ]
        self.tool.return_value = {"cik": "0001045810"}
        trace = []
        result = run_agent("Resolve NVDA.", self.config, return_details=True, trace=trace)
        tools = [event for event in result["trace"] if event["type"] == "tool"]
        self.assertEqual(tools[0]["result"], {"cik": "0001045810"})
        self.assertEqual(tools[0]["arguments"], {"ticker": "NVDA"})
        self.assertEqual(self.finalizer.call_args.args[2], trace)
        self.assertNotIn("Private reasoning", json.dumps(result))
        self.assertEqual(result["tool_call_count"], 1)

    def test_fatal_error_preserves_prior_tool_trace(self):
        self.chat.side_effect = [
            {"role": "assistant", "tool_calls": [
                {"function": {"name": "resolve_ticker_to_cik", "arguments": {"ticker": "NVDA"}}},
            ]},
            RuntimeError("Model unavailable"),
        ]
        self.tool.return_value = {"cik": "0001045810"}
        trace = []
        with self.assertRaises(RuntimeError):
            run_agent("Question", self.config, trace=trace)
        self.assertEqual(trace[1]["result"], {"cik": "0001045810"})
        self.assertEqual(trace[-1]["status"], "error")

    def test_guessed_cik_is_rejected_before_financial_tool_execution(self):
        recorder = RecordingChat([
            {"role": "assistant", "tool_calls": [{"function": {
                "name": "get_company_facts", "arguments": {"cik": "0000012518", "concept": "revenue"},
            }}]},
            {"role": "assistant", "tool_calls": [{"function": {
                "name": "resolve_ticker_to_cik", "arguments": {"ticker": "AAPL"},
            }}]},
            {"role": "assistant", "tool_calls": [{"function": {
                "name": "get_company_facts", "arguments": {"cik": "0000320193", "concept": "revenue"},
            }}]},
            {"role": "assistant", "content": "Done."},
        ])
        self.chat.side_effect = recorder
        self.tool.side_effect = [{"ticker": "AAPL", "cik": "0000320193"}, {"records": []}]
        result = run_agent("Apple revenue?", self.config, return_details=True)
        self.assertEqual(self.tool.call_args_list, [
            call("resolve_ticker_to_cik", {"ticker": "AAPL"}),
            call("get_company_facts", {"cik": "0000320193", "concept": "revenue"}),
        ])
        error = json.loads(recorder.requests[1]["messages"][-1]["content"])["error"]
        self.assertIn("Resolve the ticker", error["message"])
        self.assertEqual(result["tool_call_count"], 3)

    def test_cik_resolution_does_not_leak_between_runs(self):
        self.chat.side_effect = [
            {"role": "assistant", "tool_calls": [{"function": {
                "name": "resolve_ticker_to_cik", "arguments": {"ticker": "AAPL"},
            }}]},
            {"role": "assistant", "content": "Done."},
            {"role": "assistant", "tool_calls": [{"function": {
                "name": "get_company_facts", "arguments": {"cik": "0000320193", "concept": "revenue"},
            }}]},
            {"role": "assistant", "content": "Done."},
        ]
        self.tool.return_value = {"ticker": "AAPL", "cik": "0000320193"}
        run_agent("Resolve Apple", self.config)
        second = run_agent("Apple revenue?", self.config, return_details=True)
        self.tool.assert_called_once()
        self.assertEqual([event for event in second["trace"] if event["type"] == "tool"][0]["status"], "error")


if __name__ == "__main__":
    unittest.main()
