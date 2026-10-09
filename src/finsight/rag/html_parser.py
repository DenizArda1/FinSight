import re

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

