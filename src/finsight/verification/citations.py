import re


def validate_citations(answer, matches):
    citation_ids = re.findall(r"\[Source (\d+)\]", answer)
    if not citation_ids:
        raise ValueError("Answer must include source citations")
    for citation_id in citation_ids:
        source_number = int(citation_id)
        if not 1 <= source_number <= len(matches):
            raise ValueError(f"Source {source_number} is outside the available source range: 1 to {len(matches)}")
    return True
