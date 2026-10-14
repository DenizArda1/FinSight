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


def extract_sections(text):
    headings = find_headings(text)
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
