"""One catalog-backed field contract for all answer-generation paths."""
import re

FIELD_REFERENCE = re.compile(r"\{\{([1-9][0-9]*):([A-Za-z0-9_/-]+)(\|percent)?\}\}")


def catalog_aliases(catalog):
    """Expose short display tokens; source paths stay inside the application."""
    aliases = {}
    for index, entry in enumerate(catalog.values(), 1):
        for match in FIELD_REFERENCE.finditer(entry["template"]):
            field = match[2].rsplit("/", 1)[-1]
            if field.isdigit():
                field = match[2].rsplit("/", 2)[-2] + "_" + field
            aliases["{{F" + str(index) + "_" + field + "}}"] = match.group()
    return aliases


def normalize_catalog_references(text, catalog):
    """Resolve short tokens and accept legacy syntax only for known fields."""
    for alias, reference in catalog_aliases(catalog).items():
        text = text.replace(alias, reference)
    allowed = {match.group() for entry in catalog.values()
               for match in FIELD_REFERENCE.finditer(entry['template'])}
    for match in re.finditer(r'\{\{([1-9][0-9]*):([A-Za-z0-9_/:-]+(?:\|percent)?)\}\}', text):
        source, path = match.group(1), match.group(2)
        candidate = '{{' + source + ':' + path.replace(':', '/') + '}}'
        percent_candidate = candidate[:-2] + '|percent}}'
        if candidate not in allowed and percent_candidate in allowed:
            candidate = percent_candidate
        if candidate in allowed:
            text = text.replace(match.group(), candidate)
    return text


