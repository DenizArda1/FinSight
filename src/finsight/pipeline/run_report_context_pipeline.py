from pathlib import Path

from src.finsight.llm.client import generate_response
from src.finsight.llm.prompts import build_report_messages
from src.finsight.rag.context import build_report_context
from src.finsight.tools.report_search import search_company_reports
from src.finsight.utils.utils import load_yaml
from src.finsight.verification.citations import validate_citations
from src.finsight.verification.grounding import verify_report_answer

def answer_report_question(ticker, question, fiscal_year=None, section=None, top_k=5):
    result = search_company_reports(
        ticker=ticker,
        query=question,
        fiscal_year=fiscal_year,
        section=section,
        top_k=top_k,
    )
    matches = result["matches"]
    if not matches:
        return {"answer": None, "matches": [], "verification": None}

    context = build_report_context(matches)
    messages = build_report_messages(question, context)

    project_root = Path(__file__).resolve().parents[3]
    settings = load_yaml(project_root / "configs" / "settings.yaml")
    answer = generate_response(messages, settings["llm"])
    validate_citations(answer, matches)
    verification = verify_report_answer(
        question, answer, context, settings["llm"]
    )
    if not verification["supported"]:
        answer = None

    return {"answer": answer, "matches": matches, "verification": verification}
