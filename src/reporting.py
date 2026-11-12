#Format verified research notes and source records for display and download

from src.verification.agent_answer import (
    build_agent_evidence, build_fact_catalog, compose_template, format_source_references, render_agent_template,
)
from src.verification.citations import SOURCE_REFERENCE

DISCLAIMER = (
    "Bu not SEC filing'lerine dayalı otomatik bir taslaktır; yatırım tavsiyesi değildir; "
    "analist onayı olmadan kullanılmaz."
)


def split_research_note(result):
    """Separate generated supporting records without rewriting verified prose."""
    answer = result.get("answer") or ""
    composition = result.get("composition")
    if not isinstance(composition, dict) or not composition.get("facts"):
        return answer, ""
    evidence = result.get("evidence", [])
    try:
        catalog = build_fact_catalog(evidence)
        expected = render_agent_template(compose_template(composition, catalog), evidence)
        if expected != answer:
            return answer, ""
        details = "\n\n".join(render_agent_template(
            {"kind": composition["kind"], "template": catalog[key]["template"]}, evidence,
        ) for key in composition["facts"])
    except (KeyError, TypeError, ValueError):
        return answer, ""
    suffix = "\n\n" + details
    if answer.endswith(suffix):
        return answer[:-len(suffix)], details
    # A facts-only lookup must remain visible, not disappear into an expander.
    return answer, ""


def source_financial_rows(result):
    """Expose retrieved figures independently of a rejected model narrative."""
    evidence = build_agent_evidence(result["trace"]) if "trace" in result else result.get("evidence", [])
    sources = {source["source_id"]: source for source in evidence}
    rows = []
    for entry in build_fact_catalog(evidence).values():
        fields = entry["fields"]
        if "value" not in fields:
            continue
        source = sources[entry["source_id"]]
        rows.append({
            "Şirket": source["result"].get("company", {}).get("ticker", source["result"].get("publisher", str(fields.get("cik", "")))),
            "Metrik": fields.get("metric", source["result"].get("concept", "")),
            "Değer": fields["value"], "Birim": fields.get("unit", ""),
            "Mali yıl": fields.get("fiscal_year"), "Dönem sonu": fields.get("end", ""),
            "Form": fields.get("form", ""), "Etiket": fields.get("tag", ""),
            "Kaynak": entry["source_id"],
        })
    return rows, evidence


def build_report(question, result):
    answer = result.get("answer")
    verification = result.get("verification") or {}
    if not isinstance(answer, str) or not answer.strip() or verification.get("supported") is not True:
        raise ValueError("Only an answer that passed verification can be exported.")
    prose, details = split_research_note(result)
    sections = ["# FinSight", f"**Soru / Question:** {question}", SOURCE_REFERENCE.sub(r"[^\1]", prose)]
    if details:
        sections.append("<details>\n<summary>Veri ayrıntıları / Supporting data</summary>\n\n"
                        + SOURCE_REFERENCE.sub(r"[^\1]", details) + "\n\n</details>")
    # Standard Markdown footnotes preserve citations in downloaded notes.
    cited = {int(number) for number in SOURCE_REFERENCE.findall(answer)}
    sources = []
    for source in result.get("evidence", []):
        source_id = source["source_id"]
        if source_id in cited:
            reference = format_source_references(answer, [source])
            reference = reference.replace(f"[Source {source_id}] ", "").replace("\n", "; ")
            sources.append(f"[^{source_id}]: {reference}")
    if sources:
        sections.extend(["## Kaynaklar / Sources", "\n\n".join(sources)])
    sections.append(DISCLAIMER)
    return "\n\n".join(sections) + "\n"
