# agents/graph_orchestrator.py

import json
import operator
import uuid
import logging
from typing import TypedDict, Annotated

from langgraph.graph import StateGraph, END
from langfuse.langchain import CallbackHandler

# Imports de tes briques
from agents.state import AgentState
from agents.nodes import (
    pre_analysis_node, 
    decomposition_node, 
    generator_node, 
    execution_node, 
    evaluator_node, 
    investigator_node
)
from DataBase.db_client import DatabaseManager

logger = logging.getLogger(__name__)

# --- 1. Logique de Routage (Arêtes conditionnelles) ---

def route_after_decomposition(state: AgentState):
    """Détermine si on va vers la génération ou si on a un cas particulier."""
    return "generator"

def route_after_evaluation(state: AgentState):
    """La décision la plus importante du graphe."""
    if state["is_valid"]:
        # Si c'est une question complexe et qu'il reste des étapes
        if state["is_complex"] and state["current_step_index"] < len(state["sub_questions"]):
            return "generator" # On passe à la sous-question suivante
        return END # Tout est validé, on s'arrête
    
    # Si c'est invalide mais qu'il reste des tentatives
    if state["current_attempt"] < state["max_retries"]:
        return "investigator"
    
    return END # Échec final après retries

# --- 2. Construction du Graphe ---

workflow = StateGraph(AgentState)

# Ajout des Nœuds
workflow.add_node("pre_analysis", pre_analysis_node)
workflow.add_node("decomposition", decomposition_node)
workflow.add_node("generator", generator_node)
workflow.add_node("execution", execution_node)
workflow.add_node("evaluator", evaluator_node)
workflow.add_node("investigator", investigator_node)

# Définition des Arêtes (Edges)
workflow.set_entry_point("pre_analysis")

workflow.add_edge("pre_analysis", "decomposition")

workflow.add_conditional_edges(
    "decomposition",
    route_after_decomposition,
    {
        "generator": "generator"
    }
)

workflow.add_edge("generator", "execution")
workflow.add_edge("execution", "evaluator")

workflow.add_conditional_edges(
    "evaluator",
    route_after_evaluation,
    {
        "generator": "generator",    # Prochaine étape ou retry
        "investigator": "investigator", # Diagnostic si erreur
        END: END                      # Succès final ou abandon
    }
)

workflow.add_edge("investigator", "generator") # Après enquête, on regénère

# Compilation du graphe
app = workflow.compile()

# --- 3. Fonction d'exécution (Interface identique à l'ancienne) ---

def run_graph_agent(question: str, max_retries: int = 4, session_id: str = None, use_rag: bool = False):
    """
    Exécute l'agent via LangGraph. 
    L'interface est identique à run_autonomous_loop pour faciliter la comparaison.
    """
    if not session_id:
        session_id = f"graph_session_{uuid.uuid4().hex[:8]}"
    
    run_id = uuid.uuid4().hex
    langfuse_handler = CallbackHandler()

    # État initial
    initial_state = {
        "question": question,
        "session_id": session_id,
        "run_id": run_id,
        "use_rag": use_rag,
        "max_retries": max_retries,
        "current_attempt": 0,
        "investigation_history": "",
        "context_data": {},
        "current_step_index": 0,
        "is_complex": False
    }

    # Lancement du graphe avec tracking Langfuse
    final_state = app.invoke(
        initial_state, 
        config={"callbacks": [langfuse_handler], "run_name": "LangGraph_Autonomous_Agent"}
    )

    # On formate la sortie pour qu'elle ressemble exactement à l'ancienne
    return {
        "status": "SUCCESS" if final_state["is_valid"] else "FAILED",
        "iterations": final_state["current_attempt"],
        "cypher": final_state["current_cypher"],
        "data": final_state["current_data"]
    }

# --- 4. Test de comparaison ---

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    q = "Find the distinct Prefix's prefixes that depend on the AS with asn 109."
    
    try:
        print(f"\n🚀 Launching LangGraph Agent for: {q}")
        result = run_graph_agent(q, use_rag=True)
        print("\n📊 Final Graph Result:\n", json.dumps(result, indent=2))
    finally:
        DatabaseManager.close_all()