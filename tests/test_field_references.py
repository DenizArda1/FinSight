import unittest
from unittest.mock import patch

from src.llm.prompts import prompt_fact_catalog
from src.verification.agent_answer import (
    build_fact_catalog, compose_template, render_agent_template, request_answer_check,
    finalize_agent_answer,
    report_number_literals,
)


class FieldReferenceTests(unittest.TestCase):
    def test_source_backed_dates_and_quarter_years_survive_partial_tokenization(self):
        evidence = [{'source_id': 1, 'tool': 'search_company_updates', 'result': {'matches': [{
            'text': 'Three months ended September 30, 2026. Revenue 100.',
            'metadata': {'report_date': '2026-09-30', 'filed': '2026-10-30'}}]}}]
        catalog = build_fact_catalog(evidence)
        for text in ("30 Eylül 2026’da sona erdi; 2026 üçüncü çeyreği. [Source 1]",
                     "30 Eylül {{S1|2026}}’da sona erdi. [Source 1]",
                     "30 Eylül 2026 dönem sonu; 30 Ekim 2026 dosyalama tarihi. [Source 1]"):
            answer = render_agent_template(compose_template({'kind': 'answer', 'text': text, 'facts': []}, catalog), evidence)
            self.assertIn('2026-09-30', answer)
        for text in ('Revenue 2026 USD. [Source 1]', '2027 üçüncü çeyreği. [Source 1]',
                     '29 Eylül 2026 tarihinde. [Source 1]'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                render_agent_template(compose_template({'kind': 'answer', 'text': text, 'facts': []}, catalog), evidence)

    def test_numbered_product_names_require_exact_cited_support(self):
        evidence = [{'source_id': 1, 'tool': 'get_filing_section',
                     'result': {'text': 'Microsoft 365 and Windows 11 revenue increased. Revenue 365 USD.'}}]
        for text in ('Microsoft 365 revenue increased. [Source 1]', 'Windows 11 revenue increased. [Source 1]'):
            render_agent_template({'kind': 'answer', 'template': text}, evidence)
        for text in ('Microsoft 366 revenue increased. [Source 1]', 'Revenue 365 USD. [Source 1]',
                     'Microsoft 365 million USD. [Source 1]'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                render_agent_template({'kind': 'answer', 'template': text}, evidence)
        evidence[0]['result']['text'] = 'No product names here.'
        with self.assertRaises(ValueError):
            render_agent_template({'kind': 'answer', 'template': 'Microsoft 365. [Source 1]'}, evidence)

    def test_report_aliases_identify_exact_value_and_source(self):
        evidence = [
            {'source_id': 1, 'tool': 'get_filing_section', 'result': {'text': 'Total sales 201,944 million.'}},
            {'source_id': 2, 'tool': 'get_filing_section', 'result': {'text': 'Outlook 247.0 billion.'}},
        ]
        catalog = build_fact_catalog(evidence)
        text = 'Sales {{S1|201,944}} million; outlook {{S2|247.0}} billion.'
        rendered = render_agent_template(compose_template({'kind': 'answer', 'text': text, 'facts': []}, catalog), evidence)
        self.assertIn('Sales 201,944 million; outlook 247.0 billion.', rendered)
        for bad in ('{{S2|201,944}}', '{{S1|201.944}}', '{{S1|999}}', '{{S1|201.9}}'):
            with self.subTest(token=bad), self.assertRaises(ValueError):
                render_agent_template(compose_template({'kind': 'answer', 'text': bad, 'facts': []}, catalog), evidence)

    def test_percentage_units_are_not_duplicated(self):
        evidence = [{'source_id': 1, 'tool': 'get_filing_section',
                     'result': {'text': 'Growth 12%. Sales 50.'}}]
        catalog = build_fact_catalog(evidence)
        text = 'Büyüme yüzde {{1:report_numbers/0/value}}; pay yüzde {{1:report_numbers/1/value}}.'
        answer = render_agent_template(compose_template({'kind': 'answer', 'text': text, 'facts': []}, catalog), evidence)
        self.assertIn('Büyüme 12%', answer)
        self.assertIn('pay yüzde 50', answer)

    def test_start_date_exposed_and_calendar_year_bound_only_as_year(self):
        evidence = [{'source_id': 1, 'tool': 'get_company_facts', 'result': {'records': [{
            'metric': 'revenue', 'value': 100, 'unit': 'USD', 'fiscal_year': 2025,
            'start': '2024-02-01', 'end': '2025-01-31'}]}}]
        catalog = build_fact_catalog(evidence)
        self.assertTrue(any('start' in row['inline_fields'] for row in prompt_fact_catalog(catalog).values()))
        text = '2025 takvim yılıyla aynı değildir. [Source 1]'
        rendered = render_agent_template(compose_template({'kind': 'answer', 'text': text, 'facts': []}, catalog), evidence)
        self.assertIn('2025 takvim yılı', rendered)
        with self.assertRaises(ValueError):
            render_agent_template(compose_template({'kind': 'answer', 'text': '2025 USD. [Source 1]', 'facts': []}, catalog), evidence)

    def test_report_amounts_and_guidance_use_exact_source_tokens(self):
        evidence = [{'source_id': 1, 'tool': 'search_company_updates', 'result': {'matches': [{
            'text': 'Three months: net sales (millions) 180,169 and 201,944. '
                    'Guidance: $240.0 to $247.0 billion, growth 12% to 16%.',
            'metadata': {'form': '8-K'},
        }]}}]
        catalog = build_fact_catalog(evidence)
        prompt = prompt_fact_catalog(catalog)
        tokens = {entry['reported_number']: entry['inline_fields']['value']
                  for entry in prompt.values() if 'reported_number' in entry}
        text = (f"Sales were {tokens['201,944']} million dollars. "
                f"Outlook is {tokens['240.0']} to {tokens['247.0']} billion dollars; "
                f"expected growth {tokens['12%']} to {tokens['16%']}.")
        answer = render_agent_template(compose_template(
            {'kind': 'answer', 'text': text, 'facts': []}, catalog), evidence)
        self.assertEqual(answer, 'Sales were 201,944 million dollars. Outlook is 240.0 to 247.0 '
                                'billion dollars; expected growth 12% to 16%. [Source 1]')
        self.assertEqual(evidence[0]['result']['matches'][0]['metadata'], {'form': '8-K'})

    def test_report_numbers_do_not_allow_free_values_rounding_or_percent_conversion(self):
        evidence = [{'source_id': 1, 'tool': 'get_filing_section',
                     'result': {'text': 'Sales were 201,944 million. Growth 12%.'}}]
        catalog = build_fact_catalog(evidence)
        for text in ('Sales 201,944 million. [Source 1]', 'Sales 201.9 billion. [Source 1]',
                     '{{1:report_numbers/99/value}} [Source 1]',
                     '{{1:report_numbers/0/value|percent}} [Source 1]'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                render_agent_template(compose_template(
                    {'kind': 'answer', 'text': text, 'facts': []}, catalog), evidence)

    def test_report_number_uses_visible_context_not_hidden_or_omitted_text(self):
        source = {'source_id': 1, 'tool': 'search_filings', 'result': {'matches': [{
            'text': '999', 'context': {'text': 'Loss (703), change -2.5%, product H20. 703.'},
            'metadata': {},
        }]}}
        self.assertEqual(report_number_literals(source), ['(703)', '-2.5%', '703'])
        source['content_omitted'] = True
        self.assertEqual(report_number_literals(source), [])
        with self.assertRaises(ValueError):
            render_agent_template({'kind': 'answer', 'template': '{{1:report_numbers/0/value}} [Source 1]'}, [source])
        source.pop('content_omitted')
        source['tool'] = 'get_company_facts'
        self.assertEqual(report_number_literals(source), [])

    def test_report_number_cannot_be_taken_from_another_source(self):
        evidence = [
            {'source_id': 1, 'tool': 'get_filing_section', 'result': {'text': 'Revenue 100.'}},
            {'source_id': 2, 'tool': 'get_filing_section', 'result': {'text': 'No figures.'}},
        ]
        with self.assertRaises(ValueError):
            render_agent_template({'kind': 'answer', 'template': '{{2:report_numbers/0/value}} [Source 2]'}, evidence)

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

    def test_ratio_percentage_unit_is_not_duplicated(self):
        for text in ('Büyüme yüzde {{F1_value}}.', 'Growth {{F1_value}} percent.'):
            rendered = render_agent_template(compose_template(
                {'kind': 'answer', 'text': text, 'facts': []}, self.catalog), self.evidence)
            self.assertIn('-2.00%', rendered)
            self.assertNotIn('yüzde', rendered)
            self.assertNotIn('percent', rendered)

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
