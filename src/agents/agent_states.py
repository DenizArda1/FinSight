from typing import TypedDict, Literal

class PlanTask(TypedDict):
    id: str
    agent: Literal["financial_data", "filing_rag"]
    instruction: str

class AgentState(TypedDict):
    question: str
    plan: list[PlanTask]
    financial_results: list[dict]
    filing_results: list[dict]
    draft: str | None
    answer: str | None
    verification: dict | None
    revision_count: int
    trace: list[dict]
    request_type: str | None
    evidence: list[dict]
    composition: dict | None

def create_initial_state(question: str) -> AgentState:
    if not isinstance(question, str) or not question.strip():
        raise ValueError("Question must be a non-empty string")

    return {
        "question": question.strip(),
        "plan": [],
        "financial_results": [],
        "filing_results": [],
        "draft": None,
        "answer": None,
        "verification": None,
        "revision_count": 0,
        "trace": [],
        "request_type": None,
        "evidence": [],
        "composition": None
    }