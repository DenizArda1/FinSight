import json
import unittest

from src.finsight.verification.grounding import parse_verification_response


class VerificationResponseTests(unittest.TestCase):
    def test_supported_and_unsupported_results_preserve_their_values(self):
        cases = [
            {"supported": True, "issues": []},
            {"supported": False, "issues": ["Tax policies are not mentioned in Source 3."]},
        ]
        for result in cases:
            with self.subTest(result=result):
                self.assertEqual(parse_verification_response(json.dumps(result)), result)

    def test_invalid_json_is_not_accepted(self):
        for text in ("", "not JSON", '{"supported": true,', '```json\n{"supported": true, "issues": []}\n```'):
            with self.subTest(text=text), self.assertRaises(json.JSONDecodeError):
                parse_verification_response(text)

    def test_top_level_value_must_be_an_object(self):
        for value in (None, [], "text", 1, True):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "must be a JSON object"):
                parse_verification_response(json.dumps(value))

    def test_supported_must_be_a_boolean(self):
        for value in (None, "true", "false", 0, 1, [], {}):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "must be a boolean"):
                parse_verification_response(json.dumps({"supported": value, "issues": []}))

        with self.assertRaisesRegex(ValueError, "must be a boolean"):
            parse_verification_response('{"issues": []}')

    def test_issues_must_be_a_list(self):
        for value in (None, "Issue", {}, True, 1):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "list format"):
                parse_verification_response(json.dumps({"supported": False, "issues": value}))
                
        with self.assertRaisesRegex(ValueError, "list format"):
            parse_verification_response('{"supported": true}')

    def test_each_issue_must_be_non_empty_text(self):
        for issue in (None, 1, True, [], {}, "", " \n "):
            with self.subTest(issue=issue), self.assertRaisesRegex(ValueError, "non-empty string"):
                parse_verification_response(json.dumps({"supported": False, "issues": [issue]}))

    def test_verdict_must_agree_with_issues(self):
        with self.assertRaisesRegex(ValueError, "must not contain issues"):
            parse_verification_response('{"supported": true, "issues": ["Unsupported claim."]}')
        with self.assertRaisesRegex(ValueError, "must contain at least one issue"):
            parse_verification_response('{"supported": false, "issues": []}')


if __name__ == "__main__":
    unittest.main()
