# agents/state.py

from typing import TypedDict, List, Dict, Any, Optional
import operator
from typing import Annotated

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
    current_step_index: int  # To track which sub-question we are solving
    
    # --- Autonomous Loop State ---
    current_intent: str
    context_data: Dict[str, Any]  # Stores results of previous steps
    
    current_attempt: int
    current_cypher: Optional[str]
    current_explanation: Optional[str]
    current_data: List[Dict[str, Any]]
    
    # Evaluation & Correction
    is_valid: bool
    error_type: Optional[str]
    error_message: Optional[str]
    
    # Annotated with operator.add means LangGraph will APPEND to this string instead of overwriting it
    investigation_history: Annotated[str, operator.add] 
    
    # --- Final Output ---
    final_status: str  # "SUCCESS" or "FAILED"
    final_cypher: Optional[str]
    final_data: List[Dict[str, Any]]