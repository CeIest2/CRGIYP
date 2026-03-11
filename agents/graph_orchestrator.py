import json
import uuid
import logging

from langgraph.graph import StateGraph, END
from langfuse.langchain import CallbackHandler
from langfuse import Langfuse

from agents.state import AgentState
from agents.nodes import (
    pre_analysis_node,
    decomposition_node,
    generator_node,
    execution_node,
    evaluator_node,
    investigator_node,
    final_synthesis_node,
)
from DataBase.db_client import DatabaseManager

logger = logging.getLogger(__name__)

# Instance partagée — utilisée pour le flush en fin d'exécution.
# Le flush est indispensable car Langfuse envoie les traces en batch
# via un thread background : sans flush explicite, les traces sont
# perdues quand le process se termine.
_langfuse = Langfuse()


def route_after_decomposition(state: AgentState) -> str:
    return "generator"


def route_after_evaluation(state: AgentState) -> str:
    if state["is_valid"]:
        if state["is_complex"]:
            if state["current_step_index"] < len(state["sub_questions"]):
                return "generator"
            return "final_synthesis"
        return END

    if state["current_attempt"] < state["max_retries"]:
        return "investigator"

    return END


workflow = StateGraph(AgentState)

workflow.add_node("pre_analysis",    pre_analysis_node)
workflow.add_node("decomposition",   decomposition_node)
workflow.add_node("generator",       generator_node)
workflow.add_node("execution",       execution_node)
workflow.add_node("evaluator",       evaluator_node)
workflow.add_node("investigator",    investigator_node)
workflow.add_node("final_synthesis", final_synthesis_node)

workflow.set_entry_point("pre_analysis")
workflow.add_edge("pre_analysis",  "decomposition")

workflow.add_conditional_edges(
    "decomposition",
    route_after_decomposition,
    {"generator": "generator"}
)

workflow.add_edge("generator",  "execution")
workflow.add_edge("execution",  "evaluator")

workflow.add_conditional_edges(
    "evaluator",
    route_after_evaluation,
    {
        "generator":       "generator",
        "investigator":    "investigator",
        "final_synthesis": "final_synthesis",
        END:               END
    }
)

workflow.add_edge("investigator",    "generator")
workflow.add_edge("final_synthesis", "generator")

app = workflow.compile()


def run_graph_agent(
    question: str,
    max_retries: int = 4,
    session_id: str = None,
    use_rag: bool = False,
) -> dict:
    if not session_id:
        session_id = f"graph_session_{uuid.uuid4().hex[:8]}"

    run_id = uuid.uuid4().hex
    langfuse_handler = CallbackHandler()

    initial_state = {
        "question":              question,
        "session_id":            session_id,
        "run_id":                run_id,
        "use_rag":               use_rag,
        "max_retries":           max_retries,
        "current_attempt":       0,
        "investigation_history": None,
        "context_data":          {},
        "current_step_index":    0,
        "is_complex":            False,
        "sub_questions":         [],
    }

    try:
        final_state = app.invoke(
            initial_state,
            config={
                "callbacks": [langfuse_handler],
                "run_name":  "LangGraph_Autonomous_Agent",
                "metadata":  {"langfuse_session_id": session_id},
            },
        )
    finally:
        # Flush garanti : vide la queue du thread background Langfuse
        # avant que run_graph_agent() rende la main.
        # Sans ce flush, les traces sont perdues si le process se termine
        # juste après l'appel (standalone ou benchmark avec peu de workers).
        _langfuse.flush()

    return {
        "status":     "SUCCESS" if final_state["is_valid"] else "FAILED",
        "iterations": final_state["current_attempt"],
        "cypher":     final_state["current_cypher"],
        "data":       final_state["current_data"],
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    q = "Select the top 20 AS nodes from Ranking with name 'IHR country ranking: Total AS (RU)' that are in a peer-to-peer relationship and return their asn."

    try:
        print(f"\n🚀 Launching LangGraph Agent for: {q}")
        result = run_graph_agent(q, use_rag=True)
        _langfuse.flush()
        print("\n📊 Final Graph Result:\n", json.dumps(result, indent=2))
    finally:
        DatabaseManager.close_all()