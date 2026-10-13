def build_report_context(matches):
    if not matches:
        return ""
    blocks = []
    for index, match in enumerate(matches, start=1):
        metadata = match["metadata"]
        block = (
            f"[Source {index}]\n"
            f"Company: {metadata['ticker']}\n"
            f"Fiscal year: {metadata['fiscal_year']}\n"
            f"Section: {metadata['section']}\n"
            f"URL: {metadata['source_url']}\n"
            f"Text: {match['text']}"
        )
        blocks.append(block)
    return "\n\n".join(blocks)
