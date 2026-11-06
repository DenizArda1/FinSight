import unittest
from copy import deepcopy
from unittest.mock import patch

from src.llm.client import config_for_role, generate_response, IncompleteResponseError


class OpenAIClientTests(unittest.TestCase):
    def setUp(self):
        self.config = {"provider": "openai", "model": "gpt-6-luna", "timeout_seconds": 180}
        self.data = {
            "status": "completed", "output": [{"type": "message", "content": [
                {"type": "output_text", "text": '{"ok":true}'},
            ]}],
            "usage": {"input_tokens": 100, "output_tokens": 30,
                      "input_tokens_details": {"cached_tokens": 20},
                      "output_tokens_details": {"reasoning_tokens": 10}},
        }
        for target, kwargs in (
            ("src.llm.openai_client.requests.post", {}),
            ("src.llm.openai_client.load_dotenv", {}),
        ):
            patcher = patch(target, **kwargs)
            mocked = patcher.start()
            self.addCleanup(patcher.stop)
            if target.endswith("post"):
                self.post = mocked
        patcher = patch.dict("os.environ", {"OPENAI_API_KEY": "test-secret"})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.post.return_value.ok = True
        self.post.return_value.json.return_value = self.data

    def test_structured_contract_and_usage(self):
        schema = {"type": "object", "properties": {"facts": {"type": "array", "uniqueItems": True}}}
        original = deepcopy(schema)
        usage = {}
        self.assertEqual(generate_response([], self.config, schema, usage), '{"ok":true}')
        payload = self.post.call_args.kwargs["json"]
        self.assertFalse(payload["store"])
        self.assertTrue(payload["text"]["format"]["strict"])
        self.assertNotIn("uniqueItems", payload["text"]["format"]["schema"]["properties"]["facts"])
        self.assertEqual(schema, original)
        self.assertEqual(usage["output_tokens"], 30)
        self.assertEqual(usage["reasoning_tokens"], 10)
        self.assertNotIn("test-secret", str(usage))

    def test_incomplete_response_keeps_billable_usage(self):
        self.data["status"] = "incomplete"
        usage = {}
        with self.assertRaises(IncompleteResponseError):
            generate_response([], self.config, telemetry=usage)
        self.assertEqual(usage["input_tokens"], 100)

    def test_http_failure_does_not_leak_response_body(self):
        self.post.return_value.ok = False
        self.post.return_value.status_code = 401
        with self.assertRaisesRegex(RuntimeError, "HTTP 401"):
            generate_response([], self.config)
        self.post.return_value.json.assert_not_called()

    def test_refusal_and_empty_response_are_not_answers(self):
        for content in ([{"type": "refusal"}], []):
            self.data["output"][0]["content"] = content
            with self.assertRaises(ValueError):
                generate_response([], self.config)

    def test_only_selected_roles_use_cloud(self):
        base = {"model": "qwen3:8b", "options": {"num_ctx": 16384},
                "roles": {"writer": self.config, "critic": self.config}}
        for role in ("writer", "critic"):
            self.assertEqual(config_for_role(base, role), self.config)
            self.assertNotIn("options", config_for_role(base, role))
        for role in ("planner", "financial_data", "filing_rag"):
            self.assertIs(config_for_role(base, role), base)
