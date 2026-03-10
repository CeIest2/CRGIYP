# agents/nodes.py

import logging
import traceback
import json
from typing import Dict, Any
from langfuse import Langfuse
from langchain_core.runnables import RunnableConfig

from agents.state import AgentState
from agents.pre_analyst import get_query_expectations
from DataBase.rag_retriever import get_relevant_examples, format_rag_context
from agents.decomposer import decompose_query
from agents.request_generator import generate_cypher_query
from DataBase.IYP_connector import test_cypher_on_iyp_traced
from agents.evaluator import evaluate_cypher_result
from agents.investigator import run_investigation
from utils.helpers import truncate_deep_lists

logger = logging.getLogger(__name__)
langfuse = Langfuse()

def pre_analysis_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """Analyze question context and fetch global RAG examples."""
    logger.info("🟢 [NODE] Pre-Analysis")
    try:
        oracle_res = get_query_expectations(state["question"], session_id=state["session_id"], trace_id=state["run_id"])
        tech_intent = oracle_res.get("technical_translation", "")
        rag_text = ""
        if state["use_rag"]:
            raw = get_relevant_examples(tech_intent, top_k=3)
            rag_text = format_rag_context(raw)
        return {
            "oracle_expectations": oracle_res if oracle_res.get("success") else None,
            "implicit_filters": oracle_res.get("implicit_filters") or "None",
            "rag_context_text": rag_text
        }
    except Exception as e:
        logger.error(f"Pre-analysis fail: {e}")
        return {"oracle_expectations": None}

def decomposition_node(state: AgentState) -> Dict[str, Any]:
    """Determine if the plan needs multiple steps."""
    logger.info("🟢 [NODE] Decomposition")
    res = decompose_query(state["question"], oracle_filters=state["implicit_filters"], rag_examples=state["rag_context_text"])
    return {
        "is_complex": res.get("is_complex", False),
        "sub_questions": res.get("sub_questions", []),
        "current_step_index": 0,
        "context_data": {},
        "investigation_history": "" 
    }

def generator_node(state: AgentState) -> Dict[str, Any]:
    """Generate Cypher query based on current intent and history."""
    idx = state["current_step_index"]
    intent = state["sub_questions"][idx].get("intent") if state["is_complex"] else state["question"]
    
    logger.info(f"🟢 [NODE] Generator | Attempt {state['current_attempt'] + 1}")
    
    # Intégration du contexte des étapes précédentes
    full_intent = intent
    if state["context_data"]:
        full_intent += f"\n\nContext from previous steps:\n{json.dumps(state['context_data'])}"

    res = generate_cypher_query(
        user_question=full_intent,
        previous_history=state["investigation_history"],
        rag_examples=state["rag_context_text"]
    )
    return {
        "current_cypher": res.get("cypher"),
        "current_explanation": res.get("explanation"),
        "current_attempt": state["current_attempt"] + 1,
        "current_intent": intent
    }

def execution_node(state: AgentState) -> Dict[str, Any]:
    """Execute the Cypher query on Neo4j."""
    logger.info("🟢 [NODE] Execution")
    try:
        db_res = test_cypher_on_iyp_traced(state["current_cypher"])
        return {
            "current_data": db_res.get('data', []),
            "error_message": db_res.get("error_message") if not db_res.get("success") else None
        }
    except Exception as e:
        return {"current_data": [], "error_message": str(e)}

def evaluator_node(state: AgentState) -> Dict[str, Any]:
    """Evaluate if the data matches the question and oracle expectations."""
    logger.info("🟢 [NODE] Evaluation")
    
    # Préparation des données pour le LLM (tronquées pour la fenêtre de contexte)
    db_output = {
        "success": state["error_message"] is None,
        "data": truncate_deep_lists(state["current_data"], max_items=10),
        "row_count": len(state["current_data"]),
        "error_message": state["error_message"]
    }

    eval_res = evaluate_cypher_result(
        question=state["current_intent"] or state["question"],
        cypher=state["current_cypher"],
        explanation=state["current_explanation"],
        db_output=db_output,
        oracle_expectations=state["oracle_expectations"],
        session_id=state["session_id"],
        trace_id=state["run_id"]
    )

    is_valid = eval_res.get("is_valid", False)
    updates = {
        "is_valid": is_valid,
        "error_type": eval_res.get("error_type"),
        "error_message": eval_res.get("analysis")
    }

    # Si c'est valide et complexe, on prépare le passage à la sous-question suivante
    if is_valid and state["is_complex"]:
        idx = state["current_step_index"]
        new_context = state["context_data"].copy()
        new_context[f"Step_{idx+1}"] = {
            "intent": state["current_intent"],
            "cypher": state["current_cypher"],
            "sample": state["current_data"][:5]
        }
        updates["context_data"] = new_context
        updates["current_step_index"] = idx + 1
        updates["current_attempt"] = 0 # Reset des retries pour la prochaine étape
        updates["investigation_history"] = "" # Reset de l'historique pour la prochaine étape

    return updates

def investigator_node(state: AgentState) -> Dict[str, Any]:
    """Diagnose errors and update history for the next attempt."""
    logger.info(f"🕵️‍♂️ [NODE] Investigator | Error: {state['error_type']}")
    report = run_investigation(
        question=state["current_intent"] or state["question"],
        failed_cypher=state["current_cypher"],
        error_message=f"[{state['error_type']}] {state['error_message']}",
        previous_history=state["investigation_history"]
    ).get("report", "No diagnostic.")

    history_update = (
        f"\n--- FAILED ATTEMPT {state['current_attempt']} ---\n"
        f"Query: {state['current_cypher']}\n"
        f"Issue: {state['error_message']}\n"
        f"Diagnostic: {report}\n"
    )
    return {"investigation_history": history_update}