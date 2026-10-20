from src.agents.agent_states import AgentState, create_initial_state
from src.agents.planner import generate_plan


def run_orchestrator(question, llm_config) -> AgentState:
    state = create_initial_state(question)
    plan = generate_plan(state["question"],llm_config)

    state["request_type"] = plan["request_type"]
    state["plan"] = plan["tasks"]

    state["trace"].append({
        "type": "agent",
        "agent": "planner",
        "status": "completed",
    })
    return state