import unittest
from unittest.mock import patch

import requests

from src.finsight.llm.client import generate_response
from src.finsight.verification.grounding import verify_report_answer


class LLMClientTests(unittest.TestCase):
    def setUp(self):
        self.config = {"model": "test-model", "base_url": "http://localhost:11434/", "timeout_seconds": 180}
        patcher = patch("src.finsight.llm.client.requests.post")
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


if __name__ == "__main__":
    unittest.main()
