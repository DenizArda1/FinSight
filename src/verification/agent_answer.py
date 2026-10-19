import json
import math
import re
from decimal import Decimal
from time import perf_counter

from src.llm.client import generate_response
from src.llm.prompts import build_agent_answer_messages, build_agent_verification_messages
from src.verification.citations import validate_citations
from src.verification.grounding import parse_verification_response


FIELD_REFERENCE = re.compile(r"\{\{([1-9][0-9]*):([A-Za-z0-9_/-]+)(\|percent)?\}\}")
SOURCE_REFERENCE = re.compile(r"\[Source ([1-9][0-9]*)\]")
DISPLAY_FIELDS = {
    "value", "unit", "start", "end", "fiscal_year", "period_label", "form",
    "filed", "accn", "ticker", "name", "cik", "accession_number", "report_date",
    "section", "section_title", "source_url", "periods", "metric", "concept",
    "requested_period_ends", "missing_period_ends", "available_period_ends",
}
ANSWER_KINDS = {"answer", "insufficient_data", "clarification", "refusal"}
VERIFICATION_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "evidence_supported": {"type": "boolean"},
        "language_matches": {"type": "boolean"},
        "issues": {"type": "array", "items": {"type": "string", "minLength": 1}},
    },
    "required": ["evidence_supported", "language_matches", "issues"],
}


def record_template(source_id, path, record):
    prefix = f"{path}/" if path else ""
    tokens = {key: f"{{{{{source_id}:{prefix}{key}}}}}" for key in record if key in DISPLAY_FIELDS}
    fields = [tokens[key] for key in ("ticker", "name") if key in tokens]
    if not path and "cik" in tokens:
        fields.append("CIK: " + tokens["cik"])
    if "value" in tokens:
        value = tokens["value"]
        if record.get("unit") == "ratio":
            value = f"{{{{{source_id}:{prefix}value|percent}}}}"
        elif "unit" in tokens:
            value += " " + tokens["unit"]
        if "metric" in tokens:
            value = tokens["metric"] + ": " + value
        fields.append(value)
    if "fiscal_year" in tokens:
        fields.append("FY" + tokens["fiscal_year"])
    # Filing chunk start/end fields are character offsets, not reporting dates.
    if "report_date" not in tokens and "start" in tokens and "end" in tokens:
        fields.append(tokens["start"] + " → " + tokens["end"])
    elif "report_date" not in tokens and "end" in tokens:
        fields.append(tokens["end"])
    fields.extend(tokens[key] for key in ("report_date", "form", "accn", "accession_number", "section") if key in tokens)
    return " | ".join(fields) + f" [Source {source_id}]"


def build_fact_catalog(evidence):
    catalog = {}
    for source in evidence:
        source_id, result = source["source_id"], source["result"]
        if not isinstance(result, dict):
            continue

        records = []
        if source["tool"] == "resolve_ticker_to_cik":
            records.append(("", result))
        if source["tool"] == "get_filing_section" and isinstance(result.get("metadata"), dict):
            records.append(("metadata", result["metadata"]))

        for index, record in enumerate(result.get("records", [])):
            records.append((f"records/{index}", record))

        for metric, rows in result.get("results", {}).items():
            for index, record in enumerate(rows):
                records.append((f"results/{metric}/{index}", record))

        for index, match in enumerate(result.get("matches", [])):
            records.append((f"matches/{index}/metadata", match["metadata"]))

        for path, record in records:
            identifier = f"{source_id}:{path}" if path else f"{source_id}:company"
            template = record_template(source_id, path, record)
            if path and "ticker" not in record and isinstance(result.get("company"), dict) and "ticker" in result["company"]:
                template = f"{{{{{source_id}:company/ticker}}}} | " + template
            catalog[identifier] = {"template": template, "source_id": source_id,
                                   "fields": {key: value for key, value in record.items() if key in DISPLAY_FIELDS}}
        if "concept" in result:
            add_availability_facts(catalog, source_id, "", result)
        for concept, availability in result.get("availability", {}).items():
            add_availability_facts(catalog, source_id, f"availability/{concept}/", availability)
    return catalog


def add_availability_facts(catalog, source_id, prefix, data):
    for field, status in (("missing_period_ends", "missing"), ("available_period_ends", "available")):
        for index, end in enumerate(data.get(field, [])):
            path = f"{prefix}{field}/{index}"
            identifier = f"{source_id}:{path}"
            catalog[identifier] = {
                "source_id": source_id, "availability": status,
                "fields": {"concept": data["concept"], "period_end": end, "availability": status},
                "template": (
                    f"{{{{{source_id}:company/ticker}}}} | "
                    f"{{{{{source_id}:{prefix}concept}}}}: {status} | "
                    f"{{{{{source_id}:{path}}}}} [Source {source_id}]"
                ),
            }


def composition_schema(catalog):
    items = {"type": "string", "enum": list(catalog)} if catalog else {"type": "string"}
    return {
        "type": "object", "additionalProperties": False,
        "properties": {
            "kind": {"type": "string", "enum": sorted(ANSWER_KINDS)},
            "text": {"type": "string"},
            "facts": {"type": "array", "items": items, "uniqueItems": True, "maxItems": len(catalog)},
        },
        "required": ["kind", "text", "facts"],
    }


def compose_template(payload, catalog):
    if not isinstance(payload, dict) or not isinstance(payload.get("text"), str):
        raise ValueError("Composition must include text")

    facts = payload.get("facts")
    if not isinstance(facts, list) or any(not isinstance(key, str) or key not in catalog for key in facts):
        raise ValueError("Composition must select existing fact IDs")
    if len(set(facts)) != len(facts):
        raise ValueError("Selected fact IDs must be unique")

    missing = {key for key, entry in catalog.items() if entry.get("availability") == "missing"}
    if payload.get("kind") == "insufficient_data" and missing and not missing.intersection(facts):
        raise ValueError("An insufficient-data answer must select a missing-data fact ID")
    if "{{" in payload["text"] or "}}" in payload["text"]:
        raise ValueError("Prose cannot insert arbitrary source fields; select fact IDs instead")

    prose = payload["text"].strip()
    # Accept an exact catalog ID as a citation alias, never an invented ID.
    for identifier, entry in catalog.items():
        prose = prose.replace(f"[{identifier}]", f"[Source {entry['source_id']}]")
    if prose:
        cited = {int(number) for number in SOURCE_REFERENCE.findall(prose)}
        selected_sources = {catalog[key]["source_id"] for key in facts}
        prose += "".join(f" [Source {number}]" for number in sorted(selected_sources - cited))
    parts = [prose] if prose else []
    parts.extend(catalog[key]["template"] for key in facts)
    return {"kind": payload.get("kind"), "template": "\n\n".join(parts)}


def collect_filing_references(value):
    references = set()
    if isinstance(value, dict):
        accession = value.get("accn") or value.get("accession_number")
        if accession:
            references.add((value.get("form", ""), accession, value.get("source_url", "")))
        for child in value.values():
            references.update(collect_filing_references(child))
    elif isinstance(value, list):
        for child in value:
            references.update(collect_filing_references(child))
    return references


def format_source_references(answer, evidence):
    cited = {int(number) for number in SOURCE_REFERENCE.findall(answer)}
    lines = []
    for source in evidence:
        if source["source_id"] not in cited:
            continue
        result = source["result"]
        company = result.get("company", result) if isinstance(result, dict) else {}
        label = f"[Source {source['source_id']}] {company.get('ticker', '')}"
        references = collect_filing_references(result)
        if references:
            for reference in sorted(references):
                lines.append(f"{label} | " + " | ".join(part for part in reference if part))
        else:
            lines.append(f"{label} | {source['tool']}")
    return "\n".join(lines)


def build_agent_evidence(trace):
    #Keep tool provenance and give each retrieved filing chunk its own source ID.
    evidence = []
    for event in trace:
        if event.get("type") == "tool" and event.get("status") == "completed":
            result = event["result"]
            results = [result]
            if event["name"] == "search_filings" and isinstance(result, dict) and result.get("matches"):
                results = [{**result, "matches": [match]} for match in result["matches"]]
            for source_result in results:
                evidence.append({
                    "source_id": len(evidence) + 1,
                    "tool": event["name"],
                    "arguments": event["arguments"],
                    "result": source_result,
                })
    return evidence


def resolve_source_field(evidence, source_id, path, percent=False):
    if not 1 <= source_id <= len(evidence):
        raise ValueError(f"Unknown source: {source_id}")

    value = evidence[source_id - 1]["result"]
    parts = path.split("/")
    parent = None
    for part in parts:
        parent = value
        if isinstance(value, dict) and part in value:
            value = value[part]
        elif isinstance(value, list) and part.isascii() and part.isdigit() and int(part) < len(value):
            value = value[int(part)]
        else:
            raise ValueError(f"Unknown source field: {source_id}:{path}")

    field = parts[-2] if parts[-1].isdigit() and len(parts) > 1 else parts[-1]
    if field not in DISPLAY_FIELDS:
        raise ValueError(f"Field cannot be inserted into an answer: {field}")
    if type(value) not in (str, int, float) or (type(value) is float and not math.isfinite(value)):
        raise ValueError("Source fields must be finite scalar values")
    if percent:
        if field != "value" or not isinstance(parent, dict) or parent.get("unit") != "ratio":
            raise ValueError("Percent formatting requires a ratio value")
        if type(value) not in (int, float):
            raise ValueError("Percent formatting requires a numeric value")
        return f"{Decimal(str(value)) * 100:.2f}%"
    return str(value)


def render_agent_template(payload, evidence):
    #Insert values from exact source paths; never evaluate model-generated code
    if not isinstance(payload, dict) or payload.get("kind") not in ANSWER_KINDS:
        raise ValueError("Answer must contain a supported kind")
    template = payload.get("template")
    if not isinstance(template, str) or not template.strip():
        raise ValueError("Answer template must be non-empty text")
    if not evidence and payload["kind"] == "answer":
        raise ValueError("A factual answer requires tool evidence")

    remainder = FIELD_REFERENCE.sub("", template)
    if "{{" in remainder or "}}" in remainder:
        raise ValueError("Malformed source field reference")
    prose = SOURCE_REFERENCE.sub("", remainder)
    if any(character.isdigit() for character in prose) or "%" in prose:
        raise ValueError("Numbers, dates, form labels, and percentages must use source field references")
    if re.search(r"(?:https?://|www\.|\]\(|<a\b)", prose, re.IGNORECASE):
        raise ValueError("Source URLs must use source field references")

    # A citation number only establishes a reference. Semantic support is checked later.
    needs_citations = bool(evidence) and payload["kind"] in {"answer", "insufficient_data"}
    validate_citations(template, evidence, require_citations=needs_citations)
    cited_sources = {int(number) for number in SOURCE_REFERENCE.findall(template)}
    rendered = []
    position = 0
    for match in FIELD_REFERENCE.finditer(template):
        source_id = int(match[1])
        if source_id not in cited_sources:
            raise ValueError(f"Inserted field is missing its citation: Source {source_id}")
        rendered.append(template[position:match.start()])
        rendered.append(resolve_source_field(evidence, source_id, match[2], percent=bool(match[3])))
        position = match.end()
    rendered.append(template[position:])
    return "".join(rendered)


def parse_agent_verdict(text):
    verdict = json.loads(text)
    if not isinstance(verdict, dict):
        raise ValueError("Agent verification must be a JSON object")
    for field in ("evidence_supported", "language_matches"):
        if type(verdict.get(field)) is not bool:
            raise ValueError(f"{field} must be a boolean")
    supported = verdict["evidence_supported"] and verdict["language_matches"]
    validated = parse_verification_response(json.dumps({
        "supported": supported, "issues": verdict.get("issues"),
    }))
    return {**validated, "evidence_supported": verdict["evidence_supported"],
            "language_matches": verdict["language_matches"]}


def request_answer_check(messages, llm_config, trace, phase, response_format="json"):
    started = perf_counter()
    event = {"type": "model", "phase": phase}
    try:
        text = generate_response(messages, llm_config, response_format=response_format)
        event.update({"status": "completed", "content": text})
        return text
    except Exception as error:
        event.update({"status": "error", "error": {
            "type": type(error).__name__, "message": str(error),
        }})
        raise
    finally:
        event["elapsed_seconds"] = perf_counter() - started
        trace.append(event)


def finalize_agent_answer(question, draft, trace, llm_config):
    evidence = build_agent_evidence(trace)
    result = {
        "answer": None, "draft": draft, "candidate": None, "template": None,
        "evidence": evidence,
        "verification": {"status": "not_run", "supported": None, "issues": []},
    }
    stage = "composition"
    try:
        catalog = build_fact_catalog(evidence)
        messages = build_agent_answer_messages(question, evidence, catalog)
        for attempt in range(2):
            phase = "composition" if attempt == 0 else "composition_repair"
            stage = phase
            text = request_answer_check(messages, llm_config, trace, phase, composition_schema(catalog))
            stage = "deterministic"
            try:
                payload = json.loads(text)
                result["composition"] = payload
                template = compose_template(payload, catalog)
                result["template"] = template
                candidate = render_agent_template(template, evidence)
                break
            except ValueError as error:
                if attempt == 1:
                    raise
                messages.extend([
                    {"role": "assistant", "content": text},
                    {"role": "user", "content": (
                        f"The application rejected the format: {error}. "
                        "Return corrected JSON. Remove ALL numbers, fiscal years, dates, form labels, "
                        "percentages and URLs from text (except [Source N] citations). "
                        "Select fact IDs to display values instead. Do not spell numbers out in words. "
                        "For missing data say 'the requested period' in the question's language. "
                        "Do not change the evidence or invent fact IDs."
                    )},
                ])
        result["candidate"] = candidate
        stage = "grounding_and_language"
        messages = build_agent_verification_messages(question, candidate, evidence, payload["kind"], payload["text"])
        verdict = parse_agent_verdict(request_answer_check(
            messages, llm_config, trace, "verification", VERIFICATION_SCHEMA,
        ))

        result["verification"] = {
            **verdict, "status": "passed" if verdict["supported"] else "failed",
            "deterministic_fields": "passed", "method": "source_fields_and_llm_judge",
        }
        
        if verdict["supported"]:
            result["answer"] = candidate
    except Exception as error:
        result["verification"] = {
            "status": "error", "supported": False,
            "issues": [f"{type(error).__name__}: {error}"], "stage": stage,
            "deterministic_fields": "passed" if stage == "grounding_and_language" else (
                "failed" if stage == "deterministic" else "not_run"
            ),
            "method": "source_fields_and_llm_judge",
        }
    return result
