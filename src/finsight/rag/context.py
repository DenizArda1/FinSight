from html import escape


def build_report_context(matches):
    if not matches:
        return ""
    blocks = []
    for index, match in enumerate(matches, start=1):
        metadata = match["metadata"]
        block = (
            f"[Source {index}]\n"
            f"Company: {metadata['ticker']}\n"
            f"Form: {metadata['form']}\n"
            f"Fiscal year: FY{metadata['fiscal_year']} (period end: {metadata['report_date']})\n"
            f"Accession: {metadata['accession_number']}\n"
            f"Section: {metadata['section']}\n"
            f"URL: {metadata['source_url']}\n"
            f"<filing_excerpt>\n{escape(match['text'], quote=False)}\n</filing_excerpt>"
        )
        blocks.append(block)
    return "\n\n".join(blocks)
