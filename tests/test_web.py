import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from tempfile import TemporaryDirectory

from src.web import PROJECT_ROOT, ResearchHandler, ResearchJobs, present_result, research, research_error_message


class WebTests(unittest.TestCase):
    def test_delete_conversation_removes_all_messages_and_survives_restart(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'history.json'
            jobs = ResearchJobs(storage_path=path)
            try:
                with patch.object(jobs.executor, 'submit'):
                    first = jobs.submit({'question': 'First'})
                    jobs.jobs[first['id']]['status'] = 'completed'
                    followup = jobs.submit({'question': 'Follow-up', 'conversation_id': first['conversation_id']})
                    jobs.jobs[followup['id']]['status'] = 'completed'
                    other = jobs.submit({'question': 'Other conversation'})
                    jobs.jobs[other['id']]['status'] = 'completed'
                jobs.delete_conversation(first['conversation_id'])
                self.assertEqual([job['id'] for job in jobs.snapshot()], [other['id']])
                restored = ResearchJobs(storage_path=path)
                try:
                    self.assertEqual([job['id'] for job in restored.snapshot()], [other['id']])
                finally:
                    restored.executor.shutdown()
            finally:
                jobs.executor.shutdown()

    def test_delete_rejects_running_conversation_and_rolls_back_disk_failure(self):
        jobs = ResearchJobs()
        try:
            with patch.object(jobs.executor, 'submit'):
                job = jobs.submit({'question': 'Question'})
            with self.assertRaises(RuntimeError):
                jobs.delete_conversation(job['conversation_id'])
            jobs.jobs[job['id']]['status'] = 'completed'
            with patch.object(jobs, 'persist', side_effect=OSError('Disk failure')):
                with self.assertRaises(OSError):
                    jobs.delete_conversation(job['conversation_id'])
            self.assertIsNotNone(jobs.snapshot(job['id']))
            with self.assertRaises(KeyError):
                jobs.delete_conversation('0' * 32)
        finally:
            jobs.executor.shutdown()

    def test_delete_endpoint_requires_local_origin_and_request_header(self):
        from unittest.mock import Mock
        handler = object.__new__(ResearchHandler)
        handler.server = SimpleNamespace(server_port=8766, jobs=Mock())
        handler.path = '/api/conversations/' + 'a' * 32
        handler.send_json = Mock()
        handler.headers = {'Host': '127.0.0.1:8766', 'Origin': 'https://foreign.example', 'X-FinSight-Request': 'research'}
        handler.do_DELETE()
        self.assertEqual(handler.send_json.call_args.args[0], 403)
        handler.headers = {'Host': '127.0.0.1:8766'}
        handler.do_DELETE()
        self.assertEqual(handler.send_json.call_args.args[0], 403)
        handler.server.jobs.delete_conversation.assert_not_called()
        handler.headers['X-FinSight-Request'] = 'research'
        handler.do_DELETE()
        handler.server.jobs.delete_conversation.assert_called_once_with('a' * 32)
        self.assertEqual(handler.send_json.call_args.args[0], 200)

    def test_step_limit_is_not_misreported_as_connection_failure(self):
        error = ExceptionGroup('Transport wrapper', [RuntimeError('Specialist reached the maximum number of steps')])
        message = research_error_message(error)
        self.assertIn('adım sınırına', message)
        self.assertNotIn('bağlantısını kontrol', message)

    def test_conversations_survive_restart_without_replaying_requests(self):
        async def runner(question):
            return {'answer': 'Saved answer', 'verification': {'supported': True}, 'evidence': []}
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'conversations.json'
            jobs = ResearchJobs(runner, storage_path=path)
            first = jobs.submit({'question': 'Apple revenue?'})
            jobs.executor.shutdown(wait=True)
            restored = ResearchJobs(runner, storage_path=path)
            self.assertEqual(restored.snapshot(first['id'])['result']['prose'], 'Saved answer')
            self.assertEqual(restored.snapshot(first['id'])['conversation_id'], first['conversation_id'])
            restored.executor.shutdown()

    def test_followup_context_is_scoped_and_previous_answers_are_not_evidence(self):
        jobs = ResearchJobs()
        try:
            with patch.object(jobs.executor, 'submit'):
                first = jobs.submit({'question': 'Apple revenue?'})
                jobs.jobs[first['id']].update(status='completed', result={'supported': True, 'prose': 'Apple answer'})
                unrelated = jobs.submit({'question': 'Microsoft risks?'})
                jobs.jobs[unrelated['id']].update(status='failed', error='Failure')
                followup = jobs.submit({'question': 'And its costs?', 'conversation_id': first['conversation_id']})
                context = jobs.conversation_question(followup)
            self.assertIn('Apple revenue?', context)
            self.assertIn('CURRENT REQUEST:\nAnd its costs?', context)
            self.assertIn('not source evidence', context)
            self.assertNotIn('Microsoft', context)
            self.assertEqual(jobs.conversation_question(unrelated), 'Microsoft risks?')
        finally:
            jobs.executor.shutdown()

    def test_unknown_conversation_and_non_string_id_are_rejected(self):
        jobs = ResearchJobs()
        try:
            for identifier in ['a' * 32, True, '../file']:
                with self.subTest(identifier=identifier), self.assertRaises(ValueError):
                    jobs.submit({'question': 'Question', 'conversation_id': identifier})
        finally:
            jobs.executor.shutdown()

    def test_history_is_not_silently_removed_after_fifty_conversations(self):
        jobs = ResearchJobs()
        try:
            with patch.object(jobs.executor, 'submit'):
                for index in range(55):
                    job = jobs.submit({'question': f'Question {index}'})
                    jobs.jobs[job['id']]['status'] = 'completed'
            self.assertEqual(len(jobs.snapshot()), 55)
        finally:
            jobs.executor.shutdown()

    def test_interrupted_jobs_are_marked_failed_on_restart(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'history.json'
            jobs = ResearchJobs(storage_path=path)
            with patch.object(jobs.executor, 'submit'):
                job = jobs.submit({'question': 'Question'})
            jobs.executor.shutdown()
            restored = ResearchJobs(storage_path=path)
            self.assertEqual(restored.snapshot(job['id'])['status'], 'failed')
            restored.executor.shutdown()

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
                  'coverage': {'status': 'partial', 'gaps': ['Previous period missing.']},
                  'evidence': [{'source_id': 7, 'tool': 'get_filing_section', 'result': {
                      'text': 'Original evidence', 'source_url': 'https://www.sec.gov/test',
                      'company': {'ticker': 'TEST'}}}]}
        payload = present_result('Question', result)
        self.assertEqual(payload['prose'], result['answer'])
        self.assertEqual(payload['sources'][0]['id'], 7)
        self.assertNotIn('text', payload['sources'][0])
        self.assertNotIn('Original evidence', str(payload['sources']))
        self.assertIn('An explanation', payload['markdown'])
        self.assertEqual(payload['coverage'], result['coverage'])
        self.assertIn('Partial coverage', payload['markdown'])

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

    def test_executor_rejection_does_not_leave_a_running_job(self):
        with TemporaryDirectory() as root:
            path = Path(root) / 'conversations.json'
            jobs = ResearchJobs(storage_path=path)
            jobs.executor.shutdown()
            with self.assertRaises(RuntimeError):
                jobs.submit({'question': 'Question'})
            self.assertEqual(jobs.snapshot(), [])
            self.assertEqual(json.loads(path.read_text()), {})

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
