# agents/nodes.py

import logging
import json
from typing import Dict, Any
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


def pre_analysis_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    logger.info("🟢 [NODE] Pre-Analysis")
    try:
        oracle_res = get_query_expectations(
            state["question"],
            session_id=state["session_id"],
            trace_id=state["run_id"],
        )
        tech_intent = oracle_res.get("technical_translation", "")
        rag_text = ""

        if state["use_rag"]:
            raw = get_relevant_examples(tech_intent, top_k=3)
            rag_text = format_rag_context(raw)

        return {
            "oracle_expectations": oracle_res if oracle_res.get("success") else None,
            "implicit_filters":    oracle_res.get("implicit_filters") or "None",
            "rag_context_text":    rag_text,
        }
    except Exception as e:
        logger.error(f"Pre-analysis fail: {e}")
        return {
            "oracle_expectations": None,
            "implicit_filters":    "None",
            "rag_context_text":    "",
        }


def decomposition_node(state: AgentState) -> Dict[str, Any]:
    logger.info("🟢 [NODE] Decomposition")
    res = decompose_query(
        state["question"],
        oracle_filters=state["implicit_filters"],
        rag_examples=state["rag_context_text"],
        session_id=state["session_id"],   # FIX: était ignoré
        trace_id=state["run_id"],          # FIX: était ignoré
    )
    return {
        "is_complex":            res.get("is_complex", False),
        "sub_questions":         res.get("sub_questions", []),
        "current_step_index":    0,
        "context_data":          {},
        "investigation_history": None,
    }


def generator_node(state: AgentState) -> Dict[str, Any]:
    idx = state["current_step_index"]
    intent = (
        state["sub_questions"][idx].get("intent")
        if state["is_complex"]
        else state["question"]
    )

    logger.info(f"🟢 [NODE] Generator | Attempt {state['current_attempt'] + 1}")

    full_intent = intent
    if state["context_data"]:
        full_intent += (
            f"\n\nContext from previous steps:\n{json.dumps(state['context_data'])}"
        )

    res = generate_cypher_query(
        user_question=full_intent,
        previous_history=state["investigation_history"] or "No previous attempts.",
        rag_examples=state["rag_context_text"],
        session_id=state["session_id"],   # FIX: non passé auparavant
        trace_id=state["run_id"],          # FIX: non passé auparavant
        trace_name=f"[Attempt {state['current_attempt'] + 1}] Cypher Generation",
    )
    return {
        "current_cypher":      res.get("cypher"),
        "current_explanation": res.get("explanation"),
        "current_attempt":     state["current_attempt"] + 1,
        "current_intent":      intent,
    }


def execution_node(state: AgentState) -> Dict[str, Any]:
    logger.info("🟢 [NODE] Execution")

    cypher = state.get("current_cypher")
    if not cypher:
        # FIX: si le generator a échoué silencieusement, on ne crashe pas Neo4j
        logger.error("execution_node: current_cypher is None — skipping DB call")
        return {
            "current_data":  [],
            "error_message": "Generator produced no Cypher query.",
        }

    try:
        db_res = test_cypher_on_iyp_traced(cypher)
        return {
            "current_data":  db_res.get("data", []),
            "error_message": None if db_res.get("success") else db_res.get("message"),
        }
    except Exception as e:
        return {"current_data": [], "error_message": str(e)}


def evaluator_node(state: AgentState) -> Dict[str, Any]:
    logger.info("🟢 [NODE] Evaluation")

    db_output = {
        "success":       state["error_message"] is None,
        "data":          truncate_deep_lists(state["current_data"], max_items=10),
        "row_count":     len(state["current_data"]),
        "error_message": state["error_message"],
    }

    eval_res = evaluate_cypher_result(
        question=state["current_intent"] or state["question"],
        cypher=state["current_cypher"],
        explanation=state["current_explanation"],
        db_output=db_output,
        oracle_expectations=state["oracle_expectations"],
        session_id=state["session_id"],
        trace_id=state["run_id"],
        trace_name=f"[Attempt {state['current_attempt']}] Evaluation",  # FIX: trace nommée
    )

    is_valid = eval_res.get("is_valid", False)
    updates: Dict[str, Any] = {
        "is_valid":     is_valid,
        "error_type":   eval_res.get("error_type"),
        "error_message": eval_res.get("analysis"),
    }

    if is_valid and state["is_complex"]:
        idx = state["current_step_index"]
        new_context = state["context_data"].copy()
        new_context[f"Step_{idx + 1}"] = {
            "intent": state["current_intent"],
            "cypher": state["current_cypher"],
            "sample": state["current_data"][:5],
        }
        updates["context_data"]          = new_context
        updates["current_step_index"]    = idx + 1
        updates["current_attempt"]       = 0
        updates["investigation_history"] = None

    return updates


def investigator_node(state: AgentState) -> Dict[str, Any]:
    logger.info(f"🕵️‍♂️ [NODE] Investigation | Error: {state['error_type']}")

    investigation_res = run_investigation(
        question=state["current_intent"] or state["question"],
        failed_cypher=state["current_cypher"],
        error_message=f"[{state['error_type']}] {state['error_message']}",
        previous_history=state["investigation_history"] or "No previous attempts.",
        session_id=state["session_id"],
        trace_id=state["run_id"],
        trace_prefix=f"[Attempt {state['current_attempt']}]",
    )

    report_summary = investigation_res.get("report", "")

    history_update = (
        f"\n--- FAILED ATTEMPT {state['current_attempt']} ---\n"
        f"Query: {state['current_cypher']}\n"
        f"Issue: {state['error_message']}\n"
        f"Diagnostic Report: {report_summary}\n"
    )

    return {"investigation_history": history_update}


def final_synthesis_node(state: AgentState) -> Dict[str, Any]:
    logger.info("🏁 [NODE] Final Synthesis — preparing unified query from all steps")

    steps_summary = json.dumps(state["context_data"], indent=2, ensure_ascii=False)

    synthesis_intent = (
        f"Using the intermediate results collected below, answer the original question "
        f"with a single unified Cypher query.\n\n"
        f"ORIGINAL QUESTION: {state['question']}\n\n"
        f"INTERMEDIATE RESULTS FROM PREVIOUS STEPS:\n{steps_summary}\n\n"
        f"IMPORTANT: Do NOT hardcode large lists of IDs from previous steps. "
        f"Instead, merge the previous Cypher logic into a single traversal query."
    )

    return {
        "is_complex":            False,
        "current_intent":        synthesis_intent,
        "current_attempt":       0,
        "investigation_history": None,
    }