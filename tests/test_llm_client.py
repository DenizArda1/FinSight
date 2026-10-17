import unittest
from unittest.mock import patch

import requests

from src.llm.client import generate_response, send_chat_request
from src.verification.grounding import verify_report_answer


class LLMClientTests(unittest.TestCase):
    def setUp(self):
        self.config = {"model": "test-model", "base_url": "http://localhost:11434/", "timeout_seconds": 180}
        patcher = patch("src.llm.client.requests.post")
        self.post = patcher.start()
        self.addCleanup(patcher.stop)

    def test_writer_uses_chat_without_forcing_json(self):
        self.post.return_value.json.return_value = {"message": {"content": "Answer [Source 1]."}}
        messages = [{"role": "user", "content": "Question"}]
        self.assertEqual(generate_response(messages, self.config), "Answer [Source 1].")
        self.post.assert_called_once_with(
            "http://localhost:11434/api/chat",
            json={"model": "test-model", "messages": messages, "stream": False}, timeout=180,
        )

    def test_verifier_requests_json_and_parses_negative_verdict(self):
        self.post.return_value.json.return_value = {
            "message": {"content": '{"supported": false, "issues": ["Unsupported tax claim."]}'},
        }
        result = verify_report_answer("Risks?", "Tax claim [Source 1].", "Source text", self.config)
        payload = self.post.call_args.kwargs["json"]
        self.assertEqual(payload["format"], "json")
        self.assertIn("Tax claim [Source 1].", payload["messages"][1]["content"])
        self.assertIn("Source text", payload["messages"][1]["content"])
        self.assertEqual(result, {"supported": False, "issues": ["Unsupported tax claim."]})

    def test_tool_request_preserves_complete_message_with_empty_content(self):
        message = {
            "role": "assistant", "content": "", "thinking": "Resolve the company first.",
            "tool_calls": [{"function": {
                "index": 0, "name": "resolve_ticker_to_cik", "arguments": {"ticker": "NVDA"},
            }}],
        }
        self.post.return_value.json.return_value = {"message": message}
        tools = [{"type": "function", "function": {
            "name": "resolve_ticker_to_cik",
            "parameters": {"type": "object", "properties": {"ticker": {"type": "string"}}},
        }}]
        messages = [{"role": "user", "content": "Find NVIDIA's CIK."}]

        result = send_chat_request(messages, self.config, tools=tools)

        self.assertEqual(result, message)
        self.post.assert_called_once_with(
            "http://localhost:11434/api/chat",
            json={"model": "test-model", "messages": messages, "stream": False, "tools": tools},
            timeout=180,
        )

    def test_text_entry_point_still_rejects_tool_only_message(self):
        self.post.return_value.json.return_value = {"message": {
            "role": "assistant", "content": "",
            "tool_calls": [{"function": {"name": "resolve_ticker_to_cik", "arguments": {"ticker": "NVDA"}}}],
        }}
        with self.assertRaisesRegex(ValueError, "content must be a non-empty string"):
            generate_response([], self.config)

    def test_malformed_and_empty_responses_are_rejected(self):
        for payload in (None, [], {}, {"message": None}, {"message": {}},
                        {"message": {"content": 1}}, {"message": {"content": " \n "}}):
            self.post.return_value.json.return_value = payload
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                generate_response([], self.config)

    def test_http_error_is_propagated_before_parsing(self):
        self.post.return_value.raise_for_status.side_effect = requests.HTTPError("Server error")
        with self.assertRaises(requests.HTTPError):
            generate_response([], self.config)
        self.post.return_value.json.assert_not_called()

    def test_generation_options_are_forwarded(self):
        self.post.return_value.json.return_value = {"message": {"content": "Answer"}}
        config = {**self.config, "options": {"temperature": 0, "num_ctx": 16384}}
        generate_response([], config)
        self.assertEqual(self.post.call_args.kwargs["json"]["options"], config["options"])

    def test_truncated_model_answer_is_rejected(self):
        for flags in ({"done": False}, {"done_reason": "length"}):
            self.post.return_value.json.return_value = {"message": {"content": "Incomplete answer"}, **flags}
            with self.subTest(flags=flags), self.assertRaisesRegex(ValueError, "incomplete"):
                generate_response([], self.config)


if __name__ == "__main__":
    unittest.main()
