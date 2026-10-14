from copy import deepcopy
import json
import unittest
from unittest.mock import call, patch

from src.finsight.agents.single_agent import run_agent
from src.finsight.tools.agentic_tools import TOOL_SCHEMAS


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
        chat_patcher = patch("src.finsight.agents.single_agent.send_chat_request")
        self.chat = chat_patcher.start()
        self.addCleanup(chat_patcher.stop)
        tool_patcher = patch("src.finsight.agents.single_agent.execute_tool")
        self.tool = tool_patcher.start()
        self.addCleanup(tool_patcher.stop)

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
        self.chat.assert_not_called()
        self.tool.assert_not_called()

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

    def test_tool_failure_is_propagated_without_requesting_a_final_answer(self):
        self.chat.return_value = {
            "role": "assistant", "tool_calls": [{"function": {"name": "unknown_tool", "arguments": {}}}],
        }
        self.tool.side_effect = ValueError("Unknown tool: unknown_tool")
        with self.assertRaisesRegex(ValueError, "Unknown tool"):
            run_agent("Question", self.config)
        self.chat.assert_called_once()

    def test_model_failure_is_propagated(self):
        self.chat.side_effect = RuntimeError("Model unavailable")
        with self.assertRaisesRegex(RuntimeError, "Model unavailable"):
            run_agent("Question", self.config)
        self.tool.assert_not_called()


if __name__ == "__main__":
    unittest.main()
