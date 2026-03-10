# agents/state.py

from typing import TypedDict, List, Dict, Any, Optional, Annotated
import operator


def history_reducer(current: str, update: Optional[str]) -> str:
    """
    Reducer custom pour investigation_history.

    - update is None  → reset complet (nouveau step, on repart à zéro)
    - update is str   → concaténation normale (on accumule les tentatives)

    Pourquoi ne pas utiliser operator.add directement :
    operator.add("history...", "") retourne "history..." — impossible de reset.
    Ici, retourner None depuis un node déclenche le reset proprement.
    """
    if update is None:
        return ""
    return current + update


class AgentState(TypedDict):
    """
    Represents the state of our autonomous Cypher generation graph.
    This state is passed between and updated by every node in LangGraph.
    """
    # --- Initial Inputs ---
    question: str
    session_id: str
    run_id: str
    use_rag: bool
    max_retries: int

    # --- Context & Pre-Analysis ---
    oracle_expectations: Optional[Dict[str, Any]]
    implicit_filters: str
    rag_context_text: str

    # --- Decomposition ---
    is_complex: bool
    sub_questions: List[Dict[str, Any]]
    current_step_index: int

    # --- Autonomous Loop State ---
    current_intent: str
    context_data: Dict[str, Any]

    current_attempt: int
    current_cypher: Optional[str]
    current_explanation: Optional[str]
    current_data: List[Dict[str, Any]]

    # Evaluation & Correction
    is_valid: bool
    error_type: Optional[str]
    error_message: Optional[str]

    # ✅ FIX: history_reducer remplace operator.add
    # Retourner None depuis un node → reset complet
    # Retourner une str → concaténation normale
    investigation_history: Annotated[str, history_reducer]

    # --- Final Output ---
    final_status: str
    final_cypher: Optional[str]
    final_data: List[Dict[str, Any]]