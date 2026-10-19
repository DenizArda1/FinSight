from pathlib import Path

from src.tools.company import resolve_company
from src.utils.utils import load_yaml
from src.rag.vector_store import get_vector_collection
from src.rag.retrieval import search_reports


def search_company_reports(ticker: str,query: str,fiscal_year: int | None = None, top_k: int = 5, section: str | None = None) -> dict:

    company = resolve_company(ticker)
    project_root = Path(__file__).resolve().parents[2]
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
