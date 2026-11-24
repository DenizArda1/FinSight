"""Frozen source fixtures: dates, scales and scope are checked without a model."""
import unittest

from src.rag.financial_tables import extract_financial_tables
from src.rag.html_parser import extract_text
from src.tools.research_sources import rank_documents
from src.verification.agent_answer import build_agent_evidence, build_fact_catalog, compose_template, render_agent_template
from src.verification.evidence import report_text_size


HEADER = '''<xbrli:context id="quarter"><xbrli:period>
<xbrli:startDate>2025-07-01</xbrli:startDate><xbrli:endDate>2025-09-30</xbrli:endDate>
</xbrli:period></xbrli:context>
<xbrli:context id="ytd"><xbrli:period><xbrli:startDate>2025-01-01</xbrli:startDate>
<xbrli:endDate>2025-09-30</xbrli:endDate></xbrli:period></xbrli:context>
<xbrli:context id="segment"><xbrli:entity><xbrli:segment>
<xbrldi:explicitMember dimension="Company:RegionAxis">Company:NorthAmericaMember</xbrldi:explicitMember>
</xbrli:segment></xbrli:entity><xbrli:period><xbrli:startDate>2025-07-01</xbrli:startDate>
<xbrli:endDate>2025-09-30</xbrli:endDate></xbrli:period></xbrli:context>
<xbrli:unit id="usd"><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unit>'''


def tagged_value(context, value):
    return (f'<ix:nonFraction name="us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax" '
            f'contextRef="{context}" unitRef="usd" scale="6">{value}</ix:nonFraction>')


def filing(table):
    return f'<html><body><ix:header hidden>{HEADER}</ix:header><p>In millions of USD</p>{table}</body></html>'


class FinancialTableTests(unittest.TestCase):
    def test_quarter_ytd_and_segment_keep_separate_contexts(self):
        table = '<table><tr><th>Net sales</th><th colspan="2">Periods ended September 30</th></tr>'
        for context, value in [('quarter', '125'), ('ytd', '350'), ('segment', '80')]:
            table += f'<tr><td>Revenue</td><td>{tagged_value(context, value)}</td></tr>'
        html = filing(table + '</table>')
        tables = extract_financial_tables(html, extract_text(html))
        rows = tables[0]['context']['rows']
        facts = tables[0]['context']['revenue_facts']
        self.assertEqual([fact['period_type'] for fact in facts], ['quarter', 'other_duration', 'quarter'])
        self.assertEqual([fact['scope'] for fact in facts], ['entity_wide', 'entity_wide', 'dimensional'])
        self.assertEqual(facts[2]['dimensions'][0]['member'], 'Company:NorthAmericaMember')
        self.assertEqual(facts[0]['unit'], 'USD')
        self.assertEqual(facts[0]['value'], 125000000)
        self.assertEqual(facts[0]['scale_power'], '6')
        self.assertEqual(tables[0]['context']['spans'][0][2], '2')
        self.assertEqual(tables[0]['context']['preceding_text'], 'In millions of USD')

    def test_guidance_remains_untagged_source_not_actual_revenue(self):
        html = filing('<table><tr><th>Revenue outlook</th><th>Next quarter</th></tr>'
                      '<tr><td>Expected net sales</td><td>240.0–247.0 billion USD</td></tr></table>')
        tables = extract_financial_tables(html, extract_text(html))
        cells = tables[0]['context']['rows'][1]
        self.assertEqual(cells[1], '240.0–247.0 billion USD')
        self.assertEqual(tables[0]['context']['revenue_facts'], [])

    def test_invalid_context_is_not_guessed_and_hidden_cells_are_removed(self):
        html = filing('<table><tr><td>Net sales</td><td>' + tagged_value('missing', '125') +
                      '</td><td hidden>Secret 999</td></tr></table>')
        tables = extract_financial_tables(html, extract_text(html))
        self.assertNotIn('999', str(tables))
        self.assertEqual(tables[0]['context']['revenue_facts'], [])

    def test_retrieval_and_catalog_share_table_evidence_and_budget(self):
        html = filing('<table><tr><td>Revenue</td><td>' + tagged_value('quarter', '125') + '</td></tr></table>')
        text = extract_text(html)
        matches = rank_documents([{'text': text, 'tables': extract_financial_tables(html, text),
                                   'metadata': {'source_url': 'fixture', 'form': '10-Q'}}], 'revenue', 1)
        self.assertEqual(matches[0]['text'], text)
        self.assertTrue(matches[0]['financial_tables'])
        evidence = build_agent_evidence([{'type': 'tool', 'status': 'completed', 'name': 'search_company_updates',
                                         'arguments': {}, 'result': {'matches': matches}}])
        self.assertGreater(report_text_size(evidence[0]), len(text))
        values = [entry['fields'].get('value') for entry in build_fact_catalog(evidence).values()]
        self.assertIn('125', values)
        self.assertIn(125000000, values)
        records = [entry for entry in build_fact_catalog(evidence).values()
                   if entry['fields'].get('value') == 125000000]
        self.assertEqual(records[0]['fields']['period_type'], 'quarter')
        self.assertEqual(records[0]['fields']['scope'], 'entity_wide')
        catalog = build_fact_catalog(evidence)
        identifier = next(key for key, entry in catalog.items() if entry['fields'].get('value') == 125000000)
        source, path = identifier.split(':', 1)
        composition = {'kind': 'answer', 'facts': [],
                       'text': 'Revenue was {{' + source + ':' + path + '/value}} USD.'}
        rendered = render_agent_template(compose_template(composition, catalog), evidence)
        self.assertIn('125000000 USD', rendered)
        self.assertIn('[Source 1]', rendered)
        self.assertNotIn('6', values)  # the scale exponent is metadata, not a reported financial amount

    def test_unrelated_and_oversized_tables_do_not_pollute_matches(self):
        html = filing('<table><tr><td>Revenue</td><td>' + 'long ' * 21000 + '</td></tr></table>')
        self.assertEqual(extract_financial_tables(html, extract_text(html)), [])
