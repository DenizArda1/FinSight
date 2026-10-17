import re


def validate_citations(answer, matches, require_citations=True):
    if not isinstance(answer, str):
        raise ValueError("Answer must be text")
    citation_ids = re.findall(r"\[Source ([0-9]+)\]", answer)
    remainder = re.sub(r"\[Source [0-9]+\]", "", answer)
    if re.search(r"\[source", remainder, re.IGNORECASE):
        raise ValueError("Malformed source citation")
    if not citation_ids and require_citations:
        raise ValueError("Answer must include source citations")
    for citation_id in citation_ids:
        source_number = int(citation_id)
        if not 1 <= source_number <= len(matches):
            raise ValueError(f"Source {source_number} is outside the available source range: 1 to {len(matches)}")
    return True
