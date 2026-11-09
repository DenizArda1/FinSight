import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from src.web import PROJECT_ROOT, ResearchHandler, ResearchJobs, present_result, research


class WebTests(unittest.TestCase):
    def test_web_research_uses_configured_mcp_orchestrator(self):
        import asyncio
        result = {'answer': 'Configured runner result'}
        with patch('src.web.load_yaml', return_value={'llm': {'model': 'configured'}}), \
                patch('src.web.run_mcp_orchestrator', new_callable=AsyncMock, return_value=result) as runner:
            self.assertIs(asyncio.run(research('Question')), result)
        runner.assert_awaited_once_with('Question', {'model': 'configured'})

    def test_static_routes_cannot_expose_credentials_or_source_files(self):
        handler = object.__new__(ResearchHandler)
        self.assertEqual(Path(handler.translate_path('/')), PROJECT_ROOT / 'src/templates/research.html')
        for path in ('/.env', '/src/web.py', '/../.env', '/static/../../.env', '/static/'):
            with self.subTest(path=path):
                self.assertEqual(Path(handler.translate_path(path)).name, '__not_found__')

    def test_api_rejects_foreign_origins_and_hostnames(self):
        handler = object.__new__(ResearchHandler)
        handler.server = SimpleNamespace(server_port=8766)
        handler.headers = {'Host': '127.0.0.1:8766', 'Origin': 'http://127.0.0.1:8766'}
        self.assertTrue(handler.local_request())
        handler.headers['Origin'] = 'https://example.com'
        self.assertFalse(handler.local_request())
        handler.headers = {'Host': 'example.com:8766'}
        self.assertFalse(handler.local_request())

    def test_verified_prose_and_source_identity_are_preserved(self):
        result = {'answer': 'An explanation [Source 7]', 'verification': {'supported': True},
                  'evidence': [{'source_id': 7, 'tool': 'get_filing_section', 'result': {
                      'text': 'Original evidence', 'source_url': 'https://www.sec.gov/test',
                      'company': {'ticker': 'TEST'}}}]}
        payload = present_result('Question', result)
        self.assertEqual(payload['prose'], result['answer'])
        self.assertEqual(payload['sources'][0]['id'], 7)
        self.assertNotIn('text', payload['sources'][0])
        self.assertNotIn('Original evidence', str(payload['sources']))
        self.assertIn('An explanation', payload['markdown'])

    def test_rejected_draft_is_not_rendered_or_exported(self):
        payload = present_result('Question', {'answer': 'Unsafe answer', 'draft': 'Unsafe draft',
            'verification': {'supported': False, 'issues': ['Unsupported claim']}, 'evidence': []})
        self.assertFalse(payload['supported'])
        self.assertEqual(payload['prose'], '')
        self.assertIsNone(payload['markdown'])
        self.assertEqual(payload['issues'], ['Unsupported claim'])

    def test_blank_or_invalid_questions_never_start_research(self):
        jobs = ResearchJobs()
        try:
            for payload in [{}, {'question': ' '}, {'question': True}, {'question': 'x', 'extra': 1},
                            {'question': 'x' * 4001}, {'question': 'x', 'company': []}]:
                with self.subTest(payload=str(payload)[:40]), self.assertRaises(ValueError):
                    jobs.submit(payload)
            self.assertEqual(jobs.snapshot(), [])
        finally:
            jobs.executor.shutdown()

    def test_submit_scopes_company_and_completes_existing_runner(self):
        seen = []
        async def runner(question):
            seen.append(question)
            return {'answer': 'Hello', 'verification': {'supported': True}, 'evidence': []}
        jobs = ResearchJobs(runner)
        job = jobs.submit({'question': 'Question', 'company': 'ORCL'})
        jobs.executor.shutdown(wait=True)
        completed = jobs.snapshot(job['id'])
        self.assertEqual(seen, ['Question\nSelected company: ORCL.'])
        self.assertEqual(completed['status'], 'completed')
        self.assertTrue(completed['result']['supported'])
        self.assertEqual(job['status'], 'running')

    def test_busy_requests_are_rejected(self):
        jobs = ResearchJobs()
        try:
            with patch.object(jobs.executor, 'submit'):
                jobs.submit({'question': 'First'})
                with self.assertRaises(RuntimeError):
                    jobs.submit({'question': 'Second'})
        finally:
            jobs.executor.shutdown()

    def test_error_message_does_not_expose_credentials(self):
        async def runner(question):
            raise RuntimeError('secret-key')
        jobs = ResearchJobs(runner)
        job = jobs.submit({'question': 'Question'})
        jobs.executor.shutdown(wait=True)
        result = jobs.snapshot(job['id'])
        self.assertEqual(result['status'], 'failed')
        self.assertNotIn('secret-key', result['error'])


if __name__ == '__main__':
    unittest.main()
