#Limit report text exposed to answer generation while preserving provenance

from copy import deepcopy
from html import escape
import hashlib
import json


REPORT_SEARCH_TOOLS = {"search_filings", "search_company_updates", "search_fed_releases"}

MAX_REPORT_SOURCE_CHARS = 6000
MAX_REPORT_TOTAL_CHARS = 12000


def report_text_size(source):
    result = source["result"]
    if source["tool"] == "get_filing_section":
        return len(result.get("text", ""))
    if source["tool"] in REPORT_SEARCH_TOOLS:
        return sum(
            len(match.get("context", {}).get("text", match.get("text", "")))
            for match in result.get("matches", [])
        )
    return 0


def limit_report_evidence(evidence, max_source_chars=MAX_REPORT_SOURCE_CHARS,
                          max_total_chars=MAX_REPORT_TOTAL_CHARS):
    """
    Keep complete excerpts, prefer search results, and mark omitted sources.
    Limits count the excerpt actually sent to the model, not tokens or metadata.
    Financial records are unchanged. Original tool results remain in the trace.
    """
    for limit in (max_source_chars, max_total_chars):
        if type(limit) is not int or limit <= 0:
            raise ValueError("Report text limits must be positive integers")

    bounded = deepcopy(evidence)
    used = 0
    # Priority affects admission only: source order and citation IDs stay intact.
    ranks = {}
    priorities = []
    for index, source in enumerate(bounded):
        query = (source["tool"], json.dumps(source.get("arguments", {}), sort_keys=True))
        rank = ranks.get(query, 0)
        ranks[query] = rank + 1
        priorities.append((source["tool"] == "get_filing_section", rank, index, source))
    # Admit the top result from each query before the next result from one query.
    candidates = [item[-1] for item in sorted(priorities, key=lambda item: item[:3])]
    for source in candidates:
        if source["tool"] not in REPORT_SEARCH_TOOLS | {"get_filing_section"}:
            continue
        size = report_text_size(source)
        reason = None
        if size > max_source_chars:
            reason = "source_text_limit"
        elif used + size > max_total_chars:
            reason = "total_report_text_limit"
        if reason is None:
            used += size
            continue

        original = json.dumps(source["result"], sort_keys=True, ensure_ascii=False, allow_nan=False)
        source["content_omitted"] = True
        source["result"] = {
            "content_limit": {
                "reason": reason,
                "original_text_characters": size,
                "max_source_characters": max_source_chars,
                "max_total_characters": max_total_chars,
                "original_result_sha256": hashlib.sha256(original.encode()).hexdigest(),
            },
        }
    return bounded


def evidence_for_prompt(evidence):
    """Send each original passage once, delimited as untrusted filing data."""
    sources = deepcopy(evidence)
    for source in sources:
        if source.get("content_omitted"):
            continue
        result = source["result"]
        if source["tool"] in REPORT_SEARCH_TOOLS:
            for match in result.get("matches", []):
                context = match.pop("context", {})
                excerpt = context.get("text", match.get("text", ""))
                match["text"] = "<filing_excerpt>\n" + escape(excerpt, quote=False) + "\n</filing_excerpt>"
        elif source["tool"] == "get_filing_section":
            result["text"] = "<filing_excerpt>\n" + escape(result.get("text", ""), quote=False) + "\n</filing_excerpt>"
    return sources
