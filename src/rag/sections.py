"""Locate the narrative sections used for retrieval in a cleaned 10-K."""
import re

SECTION_TITLES = {
    "1": "Business",
    "1A": "Risk Factors",
    "7": "Management's Discussion and Analysis",
}
HEADING_TITLES = {
    **SECTION_TITLES,
    "1B": "Unresolved Staff Comments",
    "1C": "Cybersecurity",
    "2": "Properties",
    "7A": "Quantitative and Qualitative Disclosures",
    "8": "Financial Statements",
}
END_ITEMS = {"1": {"1A"}, "1A": {"1B", "1C", "2"}, "7": {"7A", "8"}}
MIN_BODY_CHARS = 200


def find_headings(text):
    #Require both an item number and its title; ignore bare page headers
    headings = []
    for item, title in HEADING_TITLES.items():
        title_pattern = re.escape(title).replace("'", "['’]").replace(r"\ ", r"\s+")
        # Titles may wrap across lines or follow a tab in a table cell.
        pattern = (
            rf"^[ \t]*item[ \t]+{item}\b[ \t]*[.:\-]?[ \t]*"
            rf"(?:\n[ \t]*)?{title_pattern}\b[^\n]*"
        )
        for match in re.finditer(pattern, text, flags=re.IGNORECASE | re.MULTILINE):
            headings.append({"item": item, "start": match.start(), "end": match.end()})
    return sorted(headings, key=lambda heading: heading["start"])


def extract_sections(text, partial=False):
    headings = find_headings(text)
    if partial:
        # An amendment can end after a replacement section or continue into any
        # other Item. Never concatenate content from different accessions.
        boundaries = list(re.finditer(r"(?im)^[ \t]*item\s+(\d+[a-z]?)\b[^\n]*", text))
        found = []
        for heading in headings:
            if heading["item"] not in SECTION_TITLES:
                continue
            end = next((match.start() for match in boundaries if match.start() > heading["end"]
                        and match[1].upper() != heading["item"]), len(text))
            body = text[heading["end"]:end].strip()
            if body and not body.isdigit():
                found.append({"section": f"Item {heading['item']}", "title": SECTION_TITLES[heading["item"]],
                              "start": heading["start"], "end": end, "text": text[heading["start"]:end]})
        if len({entry["section"] for entry in found}) != len(found):
            raise ValueError("Ambiguous replacement sections in amendment")
        return found
    candidates = {item: [] for item in SECTION_TITLES}
    for heading, following in zip(headings, headings[1:]):
        item = heading["item"]
        if item not in candidates or following["item"] not in END_ITEMS[item]:
            continue
        if len(text[heading["end"]:following["start"]].strip()) < MIN_BODY_CHARS:
            continue
        start, end = heading["start"], following["start"]
        candidates[item].append({
            "section": f"Item {item}",
            "title": SECTION_TITLES[item],
            "start": start,
            "end": end,
            "text": text[start:end],
        })

    sections = []
    for item, matches in candidates.items():
        if len(matches) != 1:
            raise ValueError(f"Expected one substantive Item {item} section; found {len(matches)}")
        sections.append(matches[0])
    for previous, current in zip(sections, sections[1:]):
        if previous["end"] > current["start"]:
            raise ValueError("Report sections overlap or appear out of order")
    return sections
