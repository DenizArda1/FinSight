import re
from datetime import datetime

from bs4 import BeautifulSoup


def is_explicitly_hidden(element):
    if element.has_attr("hidden"):
        return True

    style = re.sub(r"/\*.*?\*/", "", element.get("style", ""), flags=re.DOTALL)
    display = None
    display_is_important = False
    for declaration in style.split(";"):
        property_name, separator, value = declaration.partition(":")
        if not separator or property_name.strip().lower() != "display":
            continue

        important = re.search(r"!\s*important\s*$", value, flags=re.IGNORECASE)
        if display_is_important and not important:
            continue
        if important:
            value = value[:important.start()]
        display = value.strip().lower()
        display_is_important = bool(important)

    return display == "none"


def normalize_text(text):
    text = text.replace("\xa0", " ")
    cleaned_lines = []

    for line in text.splitlines():
        line = re.sub(r" +", " ", line)
        line = line.strip(" ")

        if line.strip():
            cleaned_lines.append(line)

    return "\n".join(cleaned_lines)


def extract_text(html):
    if not isinstance(html, str) or not html.strip():
        raise ValueError("HTML must be a non-empty string")

    soup = BeautifulSoup(html, "html.parser")

    for element in soup.find_all(["script", "style", "head", "ix:header"]):
        if not element.decomposed:
            element.decompose()

    for element in soup.find_all(True):
        if not element.decomposed and is_explicitly_hidden(element):
            element.decompose()

    block_tags = [
        "p", "div", "li",
        "h1", "h2", "h3", "h4", "h5", "h6",
        "table", "tr", "br",
    ]
    for element in soup.find_all(block_tags):
        element.insert_before("\n")
        element.insert_after("\n")
    
    for element in soup.find_all(["td","th"]):
        element.insert_before("\t")

    text = soup.get_text(separator="", strip=False)
    return normalize_text(text)


def extract_fiscal_year(html):
    return extract_fiscal_year_details(html)['fiscal_year']


def extract_fiscal_year_details(html):
    #Read the report's declared fiscal year, including hidden inline XBRL
    soup = BeautifulSoup(html, "html.parser")
    values = set()
    for element in soup.find_all(attrs={"name": "dei:DocumentFiscalYearFocus"}):
        value = element.get_text(strip=True)
        if not re.fullmatch(r"\d{4}", value):
            raise ValueError("Invalid DocumentFiscalYearFocus in report")
        values.add(int(value))
    if len(values) != 1:
        raise ValueError("Expected one unambiguous DocumentFiscalYearFocus in report")
    declared = values.pop()
    result = {'fiscal_year': declared, 'fiscal_year_source': 'dei:DocumentFiscalYearFocus'}
    # A company may explicitly define its fiscal-year naming convention.
    # Match the definition to this report's end date; never infer FY from
    # the calendar year of the end date or from an unrelated future mention.
    period_values = {element.get_text(strip=True) for element in
                     soup.find_all(attrs={'name': 'dei:DocumentPeriodEndDate'})}
    period_dates = set()
    for value in period_values:
        for fmt in ('%Y-%m-%d', '%B %d, %Y'):
            try:
                period_dates.add(datetime.strptime(value, fmt).date())
                break
            except ValueError:
                continue
    if len(period_dates) != 1:
        return result
    text = re.sub(r'\s+', ' ', extract_text(html))
    definitions = re.finditer(
        r'References to fiscal(?: year)?\s+(\d{4})\b[^.;]{0,80}?refer(?:s)? to '
        r'the fiscal year end(?:ing|ed)\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})', text, re.I)
    explicit_years = set()
    for definition in definitions:
        try:
            end = datetime.strptime(definition[2], '%B %d, %Y').date()
        except ValueError:
            continue
        if end in period_dates:
            explicit_years.add(int(definition[1]))
    if len(explicit_years) > 1:
        raise ValueError('Conflicting explicit fiscal-year definitions for the report period')
    if explicit_years and declared not in explicit_years:
        result.update(fiscal_year=explicit_years.pop(), fiscal_year_source='explicit_report_definition',
                      fiscal_year_warning=f'DocumentFiscalYearFocus declares {declared}; the explicit fiscal-year definition for this report period takes precedence.')
    return result
