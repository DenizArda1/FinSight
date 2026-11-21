import unittest
from unittest.mock import patch

from src.llm.prompts import prompt_fact_catalog
from src.verification.agent_answer import (
    build_fact_catalog, compose_template, render_agent_template, request_answer_check,
    finalize_agent_answer,
)


class FieldReferenceTests(unittest.TestCase):
    def setUp(self):
        self.evidence = [{'source_id': 1, 'tool': 'compute_metrics', 'result': {
            'results': {'revenue_growth': [{'metric': 'revenue_growth', 'value': -0.02,
                                         'unit': 'ratio', 'fiscal_year': 2025, 'end': '2025-12-31'}]}}}]
        self.catalog = build_fact_catalog(self.evidence)

    def test_prompt_uses_short_tokens_and_shared_renderer_preserves_values(self):
        fields = prompt_fact_catalog(self.catalog)['1:results/revenue_growth/0']['inline_fields']
        self.assertEqual(fields['value'], '{{F1_value}}')
        composition = {'kind': 'answer', 'text': 'Growth was {{F1_value}} in FY{{F1_fiscal_year}}.', 'facts': []}
        rendered = render_agent_template(compose_template(composition, self.catalog), self.evidence)
        self.assertEqual(rendered, 'Growth was -2.00% in FY2025. [Source 1]')
        self.assertEqual(composition['text'], 'Growth was {{F1_value}} in FY{{F1_fiscal_year}}.')

    def test_unknown_alias_and_free_amount_are_still_rejected(self):
        for text in ('Growth {{F99_value}}.', 'Growth {{F1_unknown}}.', 'Revenue 500 USD.'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                render_agent_template(compose_template({'kind': 'answer', 'text': text, 'facts': []}, self.catalog), self.evidence)

    @patch('src.verification.agent_answer.generate_response')
    def test_single_agent_uses_the_same_short_field_renderer(self, generate):
        import json
        generate.side_effect = [json.dumps({'kind': 'answer', 'text': 'Growth {{F1_value}}.', 'facts': []}),
                                json.dumps({'evidence_supported': True, 'language_matches': True,
                                            'answer_complete': True, 'issues': []})]
        trace = [{'type': 'tool', 'status': 'completed', 'name': 'compute_metrics',
                  'arguments': {}, 'result': self.evidence[0]['result']}]
        result = finalize_agent_answer('Growth?', 'Draft', trace, {})
        self.assertEqual(result['answer'], 'Growth -2.00%. [Source 1]')

    @patch('src.verification.agent_answer.generate_response', return_value='{}')
    def test_single_and_multi_agent_use_same_role_configuration(self, generate):
        config = {'model': 'local', 'roles': {'writer': {'model': 'writer'}, 'critic': {'model': 'critic'}}}
        for phase, role in [('composition', 'writer'), ('composition_repair', 'writer'),
                            ('writer', 'writer'), ('verification', 'critic'), ('critic', 'critic')]:
            request_answer_check([], config, [], phase)
            self.assertEqual(generate.call_args.args[1], config['roles'][role])
