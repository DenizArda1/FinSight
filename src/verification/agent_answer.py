import json
import math
import re
from decimal import Decimal
from time import perf_counter

from src.llm.client import config_for_role, generate_response
from src.llm.prompts import build_agent_answer_messages, build_agent_verification_messages
from src.verification.citations import SOURCE_REFERENCE, validate_citations
from src.verification.grounding import parse_verification_response
from src.verification.evidence import limit_report_evidence


FIELD_REFERENCE = re.compile(r"\{\{([1-9][0-9]*):([A-Za-z0-9_/-]+)(\|percent)?\}\}")
TURKISH_SOURCE_REFERENCE = re.compile(r"\[Kaynak ([1-9][0-9]*)\]")
DISPLAY_FIELDS = {
    "value", "unit", "start", "end", "fiscal_year", "period_label", "form",
    "filed", "accn", "ticker", "name", "cik", "accession_number", "report_date",
    "section", "section_title", "source_url", "periods", "metric", "concept",
    "requested_period_ends", "missing_period_ends", "available_period_ends", "tag", "filed", "amendment_note",
}
ANSWER_KINDS = {"answer", "insufficient_data", "clarification", "refusal"}
VERIFICATION_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "issues": {"type": "array", "items": {"type": "string", "minLength": 1}},
        "evidence_supported": {"type": "boolean"},
        "language_matches": {"type": "boolean"},
        "answer_complete": {"type": "boolean"},
    },
    "required": ["evidence_supported", "language_matches", "answer_complete", "issues"],
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
    fields.extend(tokens[key] for key in ("report_date", "form", "accn", "accession_number", "section", "tag") if key in tokens)
    return " | ".join(fields) + f" [Source {source_id}]"


def build_fact_catalog(evidence):
    catalog = {}
    for source in evidence:
        if source.get("content_omitted"):
            continue
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


def composition_schema(catalog, request_type=None, evidence=None):
    items = {"type": "string", "enum": list(catalog)} if catalog else {"type": "string"}
    schema = {
        "type": "object", "additionalProperties": False,
        "properties": {
            "kind": {"type": "string", "enum": sorted(ANSWER_KINDS)},
            "text": {
                "type": "string",
                "description": "The substantive narrative answer, including any requested summary or explanation, "
                               "in the user's language with [Source N] citations. Filing metadata cards do not "
                               "include excerpt text. Use exact catalog field placeholders for inline numerical values and metadata.",
            },
            "facts": {"type": "array", "items": items, "uniqueItems": True, "maxItems": len(catalog)},
        },
        "required": ["kind", "text", "facts"],
    }
    if request_type == "clarification":
        schema["properties"]["kind"]["enum"] = ["clarification"]
        schema["properties"]["facts"]["maxItems"] = 0
    return schema


def normalize_prose_citations(prose, catalog):
    # Some structured responses encode visible line breaks a second time.
    prose = prose.replace("\\n", "\n")
    prose = TURKISH_SOURCE_REFERENCE.sub(r"[Source \1]", prose)
    for identifier, entry in catalog.items():
        prose = prose.replace(f"[{identifier}]", f"[Source {entry['source_id']}]")
    return prose


def bind_cited_metadata(prose, catalog):
    """Bind exact filing labels to cited fields; never infer or round financial values."""
    paragraphs = []
    for paragraph in prose.split("\n\n"):
        cited = {int(number) for number in SOURCE_REFERENCE.findall(paragraph)}
        replacements = {}
        for entry in catalog.values():
            if entry["source_id"] not in cited:
                continue
            for match in FIELD_REFERENCE.finditer(entry["template"]):
                field = match[2].rsplit("/", 1)[-1]
                if field not in {"fiscal_year", "start", "end", "report_date", "form", "section"}:
                    continue
                value = entry["fields"].get(field)
                if not isinstance(value, (str, int)) or isinstance(value, bool) or value == "":
                    continue
                # Chunk start/end are offsets; only ISO date strings are filing dates.
                if field in {"start", "end", "report_date"} and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(value)):
                    continue
                prefix = "FY" if field == "fiscal_year" else ""
                replacements.setdefault(prefix + str(value), prefix + match.group())
        if replacements:
            pattern = r"(?<![\w/-])(?:" + "|".join(
                re.escape(label) for label in sorted(replacements, key=len, reverse=True)
            ) + r")(?![\w/-])"
            paragraph = re.sub(pattern, lambda match: replacements[match.group()], paragraph)
        paragraphs.append(paragraph)
    return "\n\n".join(paragraphs)


def compose_template(payload, catalog, request_type=None):
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
    allowed_fields = {match.group() for entry in catalog.values()
                      for match in FIELD_REFERENCE.finditer(entry["template"])}
    for match in FIELD_REFERENCE.finditer(payload["text"]):
        if match.group() not in allowed_fields:
            raise ValueError(f"Unknown catalog field placeholder: {match.group()}")

    paragraphs = []
    for paragraph in normalize_prose_citations(payload["text"].strip(), catalog).split("\n\n"):
        cited = {int(number) for number in SOURCE_REFERENCE.findall(paragraph)}
        # The field path already identifies an exact tool source. Attach its
        # provenance ourselves; narrative claims still need their own citations.
        field_sources = {int(match[1]) for match in FIELD_REFERENCE.finditer(paragraph)}
        missing = sorted(field_sources - cited)
        if missing:
            paragraph += " " + " ".join(f"[Source {source_id}]" for source_id in missing)
        paragraphs.append(paragraph)
    prose = bind_cited_metadata("\n\n".join(paragraphs), catalog)

    if request_type == "comparison" and not any(
        character.isalpha() for character in SOURCE_REFERENCE.sub("", prose)
    ):
        raise ValueError("A comparison requires an explanation, not only fact cards or citations.")
    if (request_type == "comparison" and payload.get("kind") == "answer" and catalog
            and not SOURCE_REFERENCE.search(prose)):
        raise ValueError("Cite the comparison explanation itself using [Source N], not only its fact cards.")
    if re.search(r"\[Fact\b[^\]]*\]", prose, re.IGNORECASE):
        raise ValueError(
            "Unknown citation label 'Fact'. Cite tool_evidence source_id using [Source N], "
            "not a fact's position. Put selected fact_catalog IDs only in the facts list."
        )
    has_report_sources = any(entry["fields"].get("section") for entry in catalog.values())
    if request_type == "mixed" and payload.get("kind") == "answer" and has_report_sources:
        report_ids = {entry["source_id"] for entry in catalog.values() if entry["fields"].get("section")}
        cited_ids = {int(number) for number in SOURCE_REFERENCE.findall(prose)}
        if not report_ids.intersection(cited_ids):
            raise ValueError(
                "Cite the report explanation in prose using its actual report source IDs: "
                + ", ".join(f"[Source {source_id}]" for source_id in sorted(report_ids))
                + ". Financial-record citations cannot support macro events or business-risk claims. "
                "Citations on metadata cards alone do not cite the explanation."
            )
    if (payload.get("kind") == "answer" and prose and has_report_sources
            and not SOURCE_REFERENCE.search(prose)):
        raise ValueError(
            "Cite the report evidence in the explanatory text using [Source N]. "
            "Citations attached only to metadata cards do not cite the explanation."
        )
    # Normalize the observed localized label; source range validation still applies.
    for line in prose.splitlines():
        if SOURCE_REFERENCE.search(line) and not any(
            character.isalnum() for character in SOURCE_REFERENCE.sub("", line)
        ):
            raise ValueError(
                "A citation-only line is not an explanation. Write the substantive claim "
                "supported by that source on the same line, then cite it. "
                "Filing metadata cards do not display risk descriptions. "
                "For a purely numerical request fully answered by facts, use empty text instead."
            )
    # Fact cards carry their own citations; do not attach their sources to unrelated prose.
    parts = [prose] if prose else []
    parts.extend(catalog[key]["template"] for key in facts)
    return {"kind": payload.get("kind"), "template": "\n\n".join(parts)}


def collect_filing_references(value, ticker=""):
    references = set()
    if isinstance(value, dict):
        ticker = value.get("ticker", ticker)
        accession = value.get("accn") or value.get("accession_number")
        if accession and value.get("form"):
            amendment = value.get("amendment_note", "")
            if value.get("form") == "10-K/A" or value.get("is_amendment"):
                amendment = amendment or "Amended value: latest filed record selected, including 10-K/A."
            references.add(tuple(str(item) for item in (
                ticker, value.get("form", ""), accession,
                "FY" + str(value["fiscal_year"]) if "fiscal_year" in value else "",
                value.get("report_date", value.get("end", "")), value.get("section", ""),
                value.get("tag", ""), value.get("filed", ""), amendment, value.get("source_url", ""),
            )))
        for child in value.values():
            references.update(collect_filing_references(child, ticker))
    elif isinstance(value, list):
        for child in value:
            references.update(collect_filing_references(child, ticker))
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
    return limit_report_evidence(evidence)


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


def cited_report_texts(evidence):
    """Read the same report excerpts for generation constraints and source validation."""
    reports = {}
    for source in evidence:
        if source.get("content_omitted"):
            continue
        result = source["result"]
        if source["tool"] == "search_filings":
            reports[source["source_id"]] = [match.get("context", {}).get("text", match["text"])
                                           for match in result.get("matches", [])]
        elif source["tool"] == "get_filing_section":
            reports[source["source_id"]] = [result.get("text", "")]
    return reports


def mask_cited_identifiers(prose, evidence):
    """Exempt literal alphanumeric names in cited report text, never numeric values."""
    reports = cited_report_texts(evidence)
    lines = []
    for line in prose.splitlines():
        excerpts = [text for number in SOURCE_REFERENCE.findall(line) for text in reports.get(int(number), [])]
        for token in set(re.findall(r"\b[A-Za-z][A-Za-z-]*\d[A-Za-z0-9-]*\b", line)):
            if re.match(r"^(?:FY|Q|CIK|USD|EUR|GBP|JPY|CNY|CAD|AUD)\d", token, re.IGNORECASE):
                continue
            pattern = r"(?<!\w)" + re.escape(token) + r"(?!\w)"
            if any(re.search(pattern, text) for text in excerpts):
                line = re.sub(pattern, " " * len(token), line)
        lines.append(line)
    return "\n".join(lines)


def render_agent_template(payload, evidence):
    #Insert values from exact source paths; never evaluate model-generated code
    if not isinstance(payload, dict) or payload.get("kind") not in ANSWER_KINDS:
        raise ValueError("Answer must contain a supported kind")
    template = payload.get("template")
    if not isinstance(template, str) or not template.strip():
        raise ValueError("Answer template must be non-empty text")
    usable_evidence = any(not source.get("content_omitted") for source in evidence)
    if not usable_evidence and payload["kind"] == "answer":
        raise ValueError("A factual answer requires tool evidence")

    remainder = FIELD_REFERENCE.sub("", template)
    if "{{" in remainder or "}}" in remainder:
        raise ValueError("Malformed source field reference")
    prose = SOURCE_REFERENCE.sub("", mask_cited_identifiers(remainder, evidence))
    if any(character.isdigit() for character in prose) or "%" in prose:
        offending_spans = list(dict.fromkeys(
            word[:80] for word in prose.split()
            if any(character.isdigit() for character in word) or "%" in word
        ))[:8]
        raise ValueError(
            "Use exact catalog placeholders for numbers, dates, forms and percentages. "
            "Unbound prose values (untrusted text): "
            + json.dumps(offending_spans, ensure_ascii=False)
            + ". Replace these with the matching {{source_id:path}} token from the catalog, "
            "or remove the unsupported claim. Do not calculate or spell out values."
        )
    if re.search(r"(?:https?://|www\.|\]\(|<a\b)", prose, re.IGNORECASE):
        raise ValueError("Source URLs must use source field references")

    # A citation number only establishes a reference. Semantic support is checked later.
    needs_citations = usable_evidence and payload["kind"] in {"answer", "insufficient_data"}
    validate_citations(template, evidence, require_citations=needs_citations)
    cited_sources = {int(number) for number in SOURCE_REFERENCE.findall(template)}
    omitted_sources = {source["source_id"] for source in evidence if source.get("content_omitted")}
    if cited_sources & omitted_sources:
        raise ValueError("Cannot cite a source whose report text was omitted by the context limit")
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
    for field in ("evidence_supported", "language_matches", "answer_complete"):
        if type(verdict.get(field)) is not bool:
            raise ValueError(f"{field} must be a boolean")
    issues = verdict.get("issues")
    if not isinstance(issues, list) or any(not isinstance(issue, str) or not issue.strip() for issue in issues):
        raise ValueError("Verification issues must be a list of non-empty strings")
    issues = list(issues)
    # A negative check still means revision when the judge forgets its explanation.
    # Conflicting positive flags and reported issues must never release an answer.
    if not issues:
        failed_checks = {
            "evidence_supported": "Revise claims that are not supported by their cited sources.",
            "language_matches": "Rewrite the prose in the same language as the original question.",
            "answer_complete": "Answer each requested part or explain its specific evidence limitation.",
        }
        issues = [message for field, message in failed_checks.items() if not verdict[field]]
    supported = all(verdict[field] for field in ("evidence_supported", "language_matches", "answer_complete")) and not issues
    validated = parse_verification_response(json.dumps({
        "supported": supported, "issues": issues,
    }))
    return {**validated, "evidence_supported": verdict["evidence_supported"],
            "language_matches": verdict["language_matches"], "answer_complete": verdict["answer_complete"]}


def request_answer_check(messages, llm_config, trace, phase, response_format="json"):
    llm_config = config_for_role(llm_config, phase)
    started = perf_counter()
    event = {"type": "model", "phase": phase, "provider": llm_config.get("provider", "ollama"), "model": llm_config.get("model")}
    try:
        text = generate_response(messages, llm_config, response_format=response_format, telemetry=event)
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
                        "Return corrected JSON. Use exact catalog placeholders inline for financial "
                        "values, fiscal years, dates, form labels, percentages and URLs. "
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
