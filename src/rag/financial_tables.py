import json
import re
from decimal import Decimal, localcontext
from copy import deepcopy
from datetime import date

from bs4 import BeautifulSoup

from src.rag.html_parser import extract_text, is_explicitly_hidden

REVENUE_TAGS = {
    'us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax',
    'us-gaap:RevenueFromContractWithCustomerIncludingAssessedTax',
    'us-gaap:Revenues', 'us-gaap:SalesRevenueNet',
}


def local_elements(element, name):
    return element.find_all(lambda tag: tag.name.split(':')[-1].lower() == name.lower())


def revenue_fact(element, contexts, units):
    """Only actual tagged revenue is typed. Untagged guidance remains source text."""
    if element.get('name') not in REVENUE_TAGS:
        return None
    context = contexts.get(element.get('contextref'))
    if context is None:
        return None
    starts, ends = local_elements(context, 'startDate'), local_elements(context, 'endDate')
    if len(starts) != 1 or len(ends) != 1:
        return None
    start, end = starts[0].get_text(strip=True), ends[0].get_text(strip=True)
    try:
        days = (date.fromisoformat(end) - date.fromisoformat(start)).days + 1
    except ValueError:
        return None
    if days <= 0:
        return None
    dimensions = [{'axis': member.get('dimension'), 'member': member.get_text(' ', strip=True)}
                  for member in local_elements(context, 'explicitMember') + local_elements(context, 'typedMember')]
    unit = units.get(element.get('unitref'))
    measures = local_elements(unit, 'measure') if unit else []
    fact = {
        'metric': 'revenue', 'value_text': element.get_text('', strip=True),
        'unit': measures[0].get_text(strip=True) if len(measures) == 1 else None,
        'scale_power': element.get('scale', '0'), 'sign': element.get('sign', '+'),
        'format': element.get('format'), 'start': start, 'end': end,
        'period_type': 'quarter' if 75 <= days <= 105 else 'other_duration',
        'scope': 'dimensional' if dimensions else 'entity_wide', 'dimensions': dimensions,
        'status': 'actual', 'concept': element['name'], 'context_id': element.get('contextref'),
    }
    # Normalize only the supported SEC numeric format, using exact decimal arithmetic.
    literal = fact['value_text']
    scale = fact['scale_power']
    numeric_format = (fact['format'] or '').split(':')[-1]
    if (numeric_format in {'num-dot-decimal', ''} and fact['unit'] == 'iso4217:USD'
            and re.fullmatch(r'\d+(?:,\d{3})*(?:\.\d+)?', literal)
            and re.fullmatch(r'-?\d{1,2}', scale) and -12 <= int(scale) <= 12
            and fact['sign'] in {'+', '-'}):
        with localcontext() as context:
            context.prec = len(literal) + abs(int(scale)) + 1
            value = Decimal(literal.replace(',', '')) * Decimal(10) ** int(scale)
        if fact['sign'] == '-':
            value = -value
        # Integer USD amounts are lossless JSON numbers. Leave other formats raw.
        if value == value.to_integral_value():
            fact.update(value=int(value), unit='USD')
    return fact



def extract_financial_tables(html, text):
    """Retain small revenue/outlook tables with original spans, not guessed cell alignment.

    Row/column spans stay explicit for the model. Large or unlocatable tables are
    skipped rather than truncated into misleading headers or partial facts.
    """
    soup = BeautifulSoup(html, 'html.parser')
    contexts = {tag.get('id'): tag for tag in local_elements(soup, 'context')}
    units = {tag.get('id'): tag for tag in local_elements(soup, 'unit')}
    tables, cursor = [], 0
    for table in soup.find_all('table'):
        if table.find('table') or any(is_explicitly_hidden(node) for node in [table, *table.parents] if node.attrs is not None):
            continue
        previous = table.find_previous(['h1', 'h2', 'h3', 'h4', 'p'])
        preceding = extract_text(str(previous)) if previous else ''
        if len(preceding) > 500:
            preceding = ''
        table = deepcopy(table)
        for element in table.find_all(True):
            if not element.decomposed and (element.name in {'script', 'style', 'ix:header'} or is_explicitly_hidden(element)):
                element.decompose()
        raw = extract_text(str(table))
        start = text.find(raw, cursor) if raw else -1
        if start < 0:
            continue
        cursor = start + len(raw)
        if not any(word in raw.lower() for word in ('revenue', 'net sales', 'outlook', 'guidance')):
            continue
        rows, spans, facts = [], [], []
        for row_index, row in enumerate(table.find_all('tr')):
            cells = []
            for column_index, cell in enumerate(row.find_all(['td', 'th'], recursive=False)):
                cells.append(cell.get_text(' ', strip=True))
                if cell.get('colspan', '1') != '1' or cell.get('rowspan', '1') != '1':
                    spans.append([row_index, column_index, cell.get('colspan', '1'), cell.get('rowspan', '1')])
                for element in local_elements(cell, 'nonFraction'):
                    fact = revenue_fact(element, contexts, units)
                    if fact is not None:
                        facts.append({'row': row_index, 'cell': column_index, **fact})
            rows.append(cells)
        # Context is verbatim, not a classification of the whole table as guidance/actual.
        context = {'preceding_text': preceding,
                   'rows': rows, 'spans': spans, 'span_columns': ['row', 'cell', 'colspan', 'rowspan'],
                   'revenue_facts': facts}
        if len(json.dumps(context, ensure_ascii=False)) <= 100000:
            tables.append({'start': start, 'end': cursor, 'context': context})
    return tables


def table_context_for_excerpt(tables, start, end):
    contexts, used = [], 2
    budget = max(0, 6000 - (end - start))
    for table in tables:
        if table['start'] >= end or table['end'] <= start:
            continue
        original = table['context']
        context = original
        if original['revenue_facts']:
            # Prefer the quarterly entity-wide observations, without changing
            # any record's meaning. Other rows remain available in the excerpt.
            context = {**original, 'rows': [], 'spans': [], 'revenue_facts': []}
            ordered = sorted(original['revenue_facts'], key=lambda fact: (
                fact['scope'] != 'entity_wide', fact['period_type'] != 'quarter'))
            for fact in ordered:
                candidate = {**context, 'revenue_facts': context['revenue_facts'] + [fact]}
                if used + len(json.dumps(candidate, ensure_ascii=False)) <= budget:
                    context = candidate
            if not context['revenue_facts']:
                continue
        size = len(json.dumps(context, ensure_ascii=False))
        if used + size <= budget:
            contexts.append(context)
            used += size + 2
    return contexts
