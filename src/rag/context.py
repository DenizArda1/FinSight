from html import escape


def build_report_context(matches):
    if not matches:
        return ""
    blocks = []
    for index, match in enumerate(matches, start=1):
        metadata = match["metadata"]
        excerpt = match["context"]["text"] if "context" in match else match["text"]
        block = (
            f"[Source {index}]\n"
            f"Company: {metadata['ticker']}\n"
            f"Form: {metadata['form']}\n"
            f"Fiscal year: FY{metadata['fiscal_year']} (period end: {metadata['report_date']})\n"
            f"Accession: {metadata['accession_number']}\n"
            f"Section: {metadata['section']}\n"
            f"URL: {metadata['source_url']}\n"
            f"<filing_excerpt>\n{escape(excerpt, quote=False)}\n</filing_excerpt>"
        )
        blocks.append(block)
    return "\n\n".join(blocks)


def expand_context_window(text, start, end, section_start, section_end, padding=400):
    if not isinstance(text, str):
        raise ValueError("Text must be a string")

    for value in (start, end, section_start, section_end, padding):
        if type(value) is not int:
            raise ValueError("Offsets and padding must be integers")

    if padding < 0:
        raise ValueError("Padding must be non-negative")

    if not 0 <= section_start <= start < end <= section_end <= len(text):
        raise ValueError("Excerpt offsets must be within valid section and text bounds")

    context_start = max(section_start, start - padding)
    context_end = min(section_end, end + padding)

    return {
        "text": text[context_start:context_end],
        "start": context_start,
        "end": context_end
    }

def expand_match_context(match, text, padding=400):
    if not isinstance(match, dict):
        raise ValueError("Match must be in dictionary format")
    metadata = match.get("metadata")
    if not isinstance(metadata, dict):
        raise ValueError("Metadata must be in dictionary format")
    if not isinstance(match.get("text"), str):
        raise ValueError("Text must be in string format")

    start = metadata.get("start")
    end = metadata.get("end")
    window = expand_context_window(
        text=text,
        start=start,
        end=end,
        section_start=metadata.get("section_start"),
        section_end=metadata.get("section_end"),
        padding=padding
    )
    if text[start:end] != match["text"]:
        raise ValueError("Retrieved excerpt does not match the source text")

    return {**match, "context":window}

def validate_match_section(match, document, sections):
    if not isinstance(match, dict) or not isinstance(match.get("metadata"), dict):
        raise ValueError("Match and metadata must be dictionaries")
    if not isinstance(document, dict) or not isinstance(document.get("text"), str):
        raise ValueError("Prepared report must contain text")
    if not isinstance(sections, list):
        raise ValueError("Sections must be in list format")

    metadata = match["metadata"]
    section_name = metadata.get("section")
    if not isinstance(section_name, str) or not section_name.strip():
        raise ValueError("Retrieved section name must be non-empty text")

    matching_sections = []
    for section in sections:
        if not isinstance(section, dict):
            raise ValueError("Each prepared section must be a dictionary")
        if section.get("section") == section_name:
            matching_sections.append(section)

    if len(matching_sections) != 1:
        raise ValueError("Exactly one prepared section must match the retrieved section")

    section = matching_sections[0]
    start = section.get("start")
    end = section.get("end")
    if type(start) is not int or type(end) is not int:
        raise ValueError("Section start and end must be integers")
    if not 0 <= start < end <= len(document["text"]):
        raise ValueError("Section offsets must be within valid report bounds")
    if not isinstance(section.get("text"), str) or document["text"][start:end] != section["text"]:
        raise ValueError("Prepared section does not match the report text")

    section_start = metadata.get("section_start")
    section_end = metadata.get("section_end")
    if type(section_start) is not int or type(section_end) is not int:
        raise ValueError("Retrieved section bounds must be integers")
    if section_start != start or section_end != end:
        raise ValueError("Retrieved section bounds do not match the prepared section")

    return section
