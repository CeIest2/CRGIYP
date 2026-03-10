import logging
import uuid
import json
import traceback
from langfuse import Langfuse

from utils.helpers import truncate_deep_lists
from agents.pre_analyst import get_query_expectations 
from agents.request_generator import generate_cypher_query
from agents.evaluator import evaluate_cypher_result
from agents.investigator import run_investigation 
from agents.decomposer import decompose_query
from DataBase.IYP_connector import test_cypher_on_iyp_traced
from DataBase.rag_retriever import get_relevant_examples, format_rag_context

langfuse = Langfuse()
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def resolve_query_with_retries(target_question: str, context_data: dict, oracle_expectations: dict, session_id: str, run_id: str, max_retries: int, rag_examples: str = ""):
    history              = "No previous attempts."
    last_cypher          = None
    last_data            = [] 
    MAX_ROWS_FOR_CONTEXT = 50 
    
    prompt_question = target_question
    if context_data:
        prompt_question += (
            f"\n\n[INFO CRITIQUE : Voici le résumé des étapes précédentes de notre réflexion.\n"
            f"INTERDICTION FORMELLE : Ne crée JAMAIS de listes géantes avec IN [...] contenant des dizaines d'IDs.\n"
            f"À la place, réutilise la logique de la requête 'cypher_precedent' pour construire une seule requête Cypher unifiée.]\n"
            f"{json.dumps(context_data, indent=2)}"
        )
            
    for attempt in range(max_retries):
        current_attempt = attempt + 1
        attempt_prefix = f"[Attempt {current_attempt}]"
        print(f"\n--- 🔄 ATTEMPT {current_attempt}/{max_retries} pour : '{target_question[:50]}...' ---")

        try:
            gen_result = generate_cypher_query(
                user_question=prompt_question, 
                session_id=session_id, 
                trace_id=run_id, 
                previous_history=history, 
                trace_name=f"{attempt_prefix} Cypher Generation",
                rag_examples=rag_examples 
            )
        except Exception as e:
            logger.error(f"💥 CRASH PYTHON dans generate_cypher_query: {e}")
            logger.error(traceback.format_exc())
            break
    
        if not gen_result.get("success"):
            print(f"❌ Critical Generation Error (LLM Parsing/Timeout): {gen_result.get('error_message')}")
            break

        cypher      = gen_result["cypher"]
        explanation = gen_result["explanation"]
        last_cypher = cypher
        
        try:
            db_result   = test_cypher_on_iyp_traced(cypher)
            last_data   = db_result.get('data', [])
        except Exception as e:
            logger.error(f"💥 CRASH PYTHON dans test_cypher_on_iyp_traced: {e}")
            logger.error(traceback.format_exc())
            db_result = {"success": False, "error_message": f"Python crash: {str(e)}", "data": []}

        safe_data    = truncate_deep_lists(last_data, max_items=10)
        sample_limit = 20 
        is_truncated = len(safe_data) > sample_limit
        
        db_output_for_llm = {"success": db_result["success"],"data": safe_data if db_result["success"] else [],"row_count": len(last_data),"is_truncated": is_truncated,"error_message": db_result.get("error_message")}
        
        try:
            eval_verdict = evaluate_cypher_result(
                question=target_question, 
                cypher=cypher, 
                explanation=explanation, 
                db_output=db_output_for_llm, 
                session_id=session_id, 
                trace_id=run_id, 
                oracle_expectations=oracle_expectations, 
                trace_name=f"{attempt_prefix} Evaluation"
            )
        except Exception as e:
            logger.error(f"💥 CRASH PYTHON dans evaluate_cypher_result: {e}")
            logger.error(traceback.format_exc())
            eval_verdict = {"is_valid": False, "error_type": "PYTHON_CRASH", "analysis": str(e)}

        if eval_verdict.get("is_valid"):
            print(f"✅ SUCCESS at attempt {current_attempt}!")
            final_data = last_data[:MAX_ROWS_FOR_CONTEXT]
            if len(last_data) > MAX_ROWS_FOR_CONTEXT:
                print(f"✂️ Données tronquées de {len(last_data)} à {MAX_ROWS_FOR_CONTEXT} lignes pour le LLM.")
                
            return {"status": "SUCCESS", "iterations": current_attempt, "cypher": cypher, "data": final_data }
        
        else:
            error_type = eval_verdict.get('error_type')
            analysis = eval_verdict.get('analysis')
            print(f"⚠️ Validation Failed [{error_type}]. Launching Investigator...")
            
            if current_attempt < max_retries:
                try:
                    investigation_result = run_investigation(question=target_question, failed_cypher=cypher, error_message=f"Error Type: {error_type} | Analysis: {analysis}", session_id=session_id, trace_id=run_id, previous_history=history,trace_prefix=attempt_prefix )
                    investigation_report = investigation_result.get("report", "No report.")
                except Exception as e:
                    logger.error(f"💥 CRASH PYTHON dans run_investigation: {e}")
                    logger.error(traceback.format_exc())
                    investigation_report = f"Investigator crashed: {str(e)}"

                print(f"🕵️‍♂️ Investigator Report: {investigation_report}")

                attempt_summary = (
                    f"\n--- ATTEMPT {current_attempt} ---\n"
                    f"FAILED QUERY: {cypher}\n"
                    f"EVALUATOR REJECTION: [{error_type}] {analysis}\n"
                    f"INVESTIGATOR FACTUAL REPORT: {investigation_report}\n"
                )
                
                if history == "No previous attempts.":
                    history = attempt_summary
                else:
                    history += attempt_summary

    print(f"❌ Failed to generate a valid query after {max_retries} attempts.")
    
    return {"status": "FAILED", "iterations": max_retries,"cypher": last_cypher, "data": last_data[:MAX_ROWS_FOR_CONTEXT] if last_data else [] }


def run_autonomous_loop(question: str, max_retries: int = 4, session_id: str = None, use_rag: bool = False):
    run_id = uuid.uuid4().hex
    if not session_id:  
        session_id = f"session_{uuid.uuid4().hex[:8]}"
    
    with langfuse.start_as_current_observation(name="Autonomous_Cypher_Pipeline", as_type="span", trace_context={"trace_id": run_id, "session_id": session_id}, input={"question": question}) as main_span:

        try:
            oracle_res = get_query_expectations(question, session_id=session_id, trace_id=run_id)
            technical_intent = oracle_res.get("technical_translation", "")

            if use_rag:logger.info("Récupération des exemples RAG en cours...")
            
            rag_context_text = ""
            if use_rag:
                logger.info("Récupération des exemples RAG en cours...")
                with langfuse.start_as_current_observation(
                    name="Global_RAG_Retrieval",
                    as_type="span",
                    input={"search_intent": technical_intent}
                ) as rag_span:
                    raw_examples = get_relevant_examples(technical_intent, top_k=3) if use_rag else []
                    rag_context_text = format_rag_context(raw_examples)
                    rag_span.update(output={"retrieved_examples": raw_examples})
            
        except Exception as e:
            logger.error(f"💥 CRASH PYTHON dans get_query_expectations ou RAG: {e}")
            logger.error(traceback.format_exc())
            oracle_res = {"success": False}
            rag_context_text = "No relevant examples found." 
            
        oracle_expectations = None
        implicit_filters    = "None"
        if oracle_res.get("success"):
            oracle_expectations = {
                "real_world_context": oracle_res.get("real_world_context"),
                "expected_data_type": oracle_res.get("expected_data_type"),
                "is_empty_result_plausible": oracle_res.get("is_empty_result_plausible"),
                "rejection_conditions": oracle_res.get("rejection_conditions")
            }
            implicit_filters = oracle_res.get("implicit_filters") or "None"

        print("\n--- 🧠 Décomposition de la question ---")
        try:
            decomposer_res = decompose_query(
                question, 
                oracle_filters=implicit_filters, 
                session_id=session_id, 
                trace_id=run_id,
                rag_examples=rag_context_text 
            )
        except Exception as e:
            logger.error(f"💥 CRASH PYTHON dans decompose_query: {e}")
            decomposer_res = {"is_complex": False, "sub_questions": []}
            
        is_complex     = decomposer_res.get("is_complex", False)
        sub_questions  = decomposer_res.get("sub_questions", [])
        context_data   = {} 
        print(f"Décomposition terminée. Complexité: {'Complexe' if is_complex else 'Simple'}. Nombre de sous-questions: {len(sub_questions)}.")
        if is_complex and sub_questions:
            print(f"🧩 Question complexe détectée. Traitement en {len(sub_questions)} étapes.")
            
            for sq in sub_questions:
                step_num = sq.get("step_number")
                intent = sq.get("intent")
                print(f"\n>>> 🏃 Exécution de l'Étape {step_num}: {intent}")
                
                if use_rag :logger.info(f"🔍 Recherche RAG spécifique pour l'étape {step_num}...")
                
                with langfuse.start_as_current_observation(
                    name=f"Step_{step_num}_RAG_Retrieval",
                    as_type="span",
                    input={"search_intent": intent}
                ) as step_rag_span:
                    step_raw_examples = get_relevant_examples(intent, top_k=2) if use_rag else []
                    step_rag_context = format_rag_context(step_raw_examples)
                    step_rag_span.update(output={"retrieved_examples": step_raw_examples})
                
                step_result = resolve_query_with_retries(
                    target_question=intent, 
                    context_data=context_data, 
                    oracle_expectations=None, 
                    session_id=session_id, 
                    run_id=run_id, 
                    max_retries=max_retries,
                    rag_examples=step_rag_context 
                )

                if step_result["status"] == "SUCCESS":
                    context_data[f"Etape_{step_num}"] = {
                        "intention": intent,
                        "cypher_precedent": step_result["cypher"],
                        "echantillon_donnees": step_result["data"][:8] if step_result["data"] else [], 
                        "nombre_total_resultats": len(step_result["data"]) if step_result["data"] else 0
                    }
                else:
                    print(f"❌ Échec critique de l'étape {step_num}. L'agent n'a pas pu trouver la donnée nécessaire pour continuer.")
                    main_span.update(level="ERROR", status_message=f"Échec à l'étape {step_num}")
                    return {"status": "FAILED", "reason": f"Failed at sub-question {step_num}","iterations": step_result.get("iterations", max_retries),"cypher": step_result.get("cypher", "None generated"),"data": []}
            
            print("\n>>> 🏁 Lancement de la génération FINALE avec tous les indices récoltés")
            final_result = resolve_query_with_retries(
                target_question=f"Utilise les indices fournis pour répondre à la question initiale : {question}", 
                context_data=context_data, 
                oracle_expectations=oracle_expectations, 
                session_id=session_id, 
                run_id=run_id, 
                max_retries=max_retries,
                rag_examples=rag_context_text 
            )
            
            if final_result["status"] == "SUCCESS":
                main_span.update(output={"final_cypher": final_result["cypher"], "data": final_result["data"]})
            return final_result

        else:
            print("🎯 Question simple détectée. Résolution directe sans étapes.")
            final_result = resolve_query_with_retries(
                target_question=question, 
                context_data={}, 
                oracle_expectations=oracle_expectations, 
                session_id=session_id, 
                run_id=run_id, 
                max_retries=max_retries,
                rag_examples=rag_context_text
            )
            
            if final_result["status"] == "SUCCESS":
                main_span.update(output={"final_cypher": final_result["cypher"], "data": final_result["data"]})
            return final_result


if __name__ == "__main__":
    q = "Find the distinct Prefix's prefixes that depend on the AS with asn 109."
    result = run_autonomous_loop(q,use_rag=False)
    print("\nFinal Result:", json.dumps(result, indent=2))