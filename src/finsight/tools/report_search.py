from pathlib import Path

from src.finsight.tools.company import resolve_company
from src.finsight.utils.utils import load_yaml
from src.finsight.rag.vector_store import get_vector_collection
from src.finsight.rag.retrieval import search_reports


def search_company_reports(
    ticker: str,
    query: str,
    fiscal_year: int | None = None,
    top_k: int = 5,
    section: str | None = None,
) -> dict:

    company = resolve_company(ticker)
    project_root = Path(__file__).resolve().parents[3]
    settings_path = project_root / "configs" / "settings.yaml"
    settings = load_yaml(settings_path)

    collection = get_vector_collection(settings["vector_store"])
    matches = search_reports(
        query=query,
        collection=collection,
        embedding_config=settings["embedding"],
        top_k=top_k,
        ticker=company["ticker"],
        fiscal_year=fiscal_year,
        section=section,
    )

    return {
        "company": company,
        "query": query,
        "fiscal_year": fiscal_year,
        "section": section,
        "matches": matches,
    }
