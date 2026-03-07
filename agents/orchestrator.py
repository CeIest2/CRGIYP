import logging, uuid, json
from langfuse import Langfuse
from agents.pre_analyst import get_query_expectations 
from agents.request_generator import generate_cypher_query
from agents.evaluator import evaluate_cypher_result
from DataBase.IYP_connector import test_cypher_on_iyp_traced
from agents.investigator import run_investigation 
from agents.decomposer import decompose_query
langfuse = Langfuse()
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def resolve_query_with_retries(target_question: str, context_data: dict, oracle_expectations: dict, session_id: str, run_id: str, max_retries: int):
    history = "No previous attempts."

    prompt_question = target_question
    if context_data:
        prompt_question += f"\n\n[INFO CRITIQUE : Voici les données exactes trouvées lors des étapes précédentes dans la base. Utilise-les pour ta requête.]\n{json.dumps(context_data, indent=2)}"

    for attempt in range(max_retries):
        current_attempt = attempt + 1
        attempt_prefix = f"[Attempt {current_attempt}]"
        print(f"\n--- 🔄 ATTEMPT {current_attempt}/{max_retries} pour : '{target_question[:50]}...' ---")

        gen_result = generate_cypher_query(prompt_question, session_id=session_id, trace_id=run_id, previous_history=history, trace_name=f"{attempt_prefix} Cypher Generation")
        
        if not gen_result.get("success"):
            print(f"❌ Critical Generation Error: {gen_result.get('error_message')}")
            break

        cypher       = gen_result["cypher"]
        explanation  = gen_result["explanation"]
        db_result    = test_cypher_on_iyp_traced(cypher)

        sample_limit = 20 
        is_truncated = len(db_result.get('data', [])) > sample_limit
        
        db_output_for_llm = {
            "success": db_result["success"],
            "data": db_result.get('data', [])[:sample_limit] if db_result["success"] else [],
            "row_count": len(db_result.get('data', [])),
            "is_truncated": is_truncated,
            "error_message": db_result.get("error_message")
        }
        
        eval_verdict = evaluate_cypher_result(question=target_question, cypher=cypher, explanation=explanation, db_output=db_output_for_llm, session_id=session_id, trace_id=run_id, oracle_expectations=oracle_expectations, trace_name=f"{attempt_prefix} Evaluation")

        if eval_verdict.get("is_valid"):
            print(f"✅ SUCCESS at attempt {current_attempt}!")
            return {"status": "SUCCESS", "iterations": current_attempt, "cypher": cypher, "data": db_result.get("data")}
        
        else:
            error_type = eval_verdict.get('error_type')
            analysis = eval_verdict.get('analysis')
            print(f"⚠️ Validation Failed [{error_type}]. Launching Investigator...")
            
            if current_attempt < max_retries:
                investigation_result = run_investigation(question=target_question, failed_cypher=cypher, error_message=f"Error Type: {error_type} | Analysis: {analysis}", session_id=session_id, trace_id=run_id, previous_history=history,trace_prefix=attempt_prefix )
                
                investigation_report = investigation_result.get("report", "No report.")
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
    return {"status": "FAILED", "iterations": max_retries, "data": None}



def run_autonomous_loop(question: str, max_retries: int = 9,session_id: str = None):
    run_id = uuid.uuid4().hex
    if not session_id:  session_id = f"session_{uuid.uuid4().hex[:8]}"
    
    with langfuse.start_as_current_observation(name="Autonomous_Cypher_Pipeline", as_type="span", trace_context={"trace_id": run_id, "session_id": session_id}, input={"question": question}) as main_span:

        oracle_res = get_query_expectations(question, session_id=session_id, trace_id=run_id)
        oracle_expectations = None
        implicit_filters = "None"
        if oracle_res.get("success"):
            oracle_expectations = {"real_world_context": oracle_res.get("real_world_context"),  "expected_data_type": oracle_res.get("expected_data_type"),  "is_empty_result_plausible": oracle_res.get("is_empty_result_plausible"),  "rejection_conditions": oracle_res.get("rejection_conditions")}
            implicit_filters = oracle_res.get("implicit_filters", "None")

        print("\n--- 🧠 Décomposition de la question ---")
        decomposer_res = decompose_query(question, oracle_filters=implicit_filters, session_id=session_id, trace_id=run_id)
        is_complex     = decomposer_res.get("is_complex", False)
        sub_questions  = decomposer_res.get("sub_questions", [])
        context_data   = {} 

        if is_complex and sub_questions:
            print(f"🧩 Question complexe détectée. Traitement en {len(sub_questions)} étapes.")
            
            for sq in sub_questions:
                step_num = sq.get("step_number")
                intent = sq.get("intent")
                print(f"\n>>> 🏃 Exécution de l'Étape {step_num}: {intent}")
                
                step_result = resolve_query_with_retries(target_question=intent, context_data=context_data, oracle_expectations=oracle_expectations, session_id=session_id, run_id=run_id, max_retries=8)

                if step_result["status"] == "SUCCESS":
                    context_data[f"Resultat_Etape_{step_num}"] = step_result["data"]
                else:
                    print(f"❌ Échec de l'étape {step_num}. Impossible de continuer l'enquête.")
                    main_span.update(level="ERROR", status_message=f"Échec à l'étape {step_num}")
                    return {"status": "FAILED", "reason": f"Failed at sub-question {step_num}"}
            
            print("\n>>> 🏁 Lancement de la génération FINALE avec tous les indices récoltés")
            final_result = resolve_query_with_retries(target_question=f"Utilise les indices fournis pour répondre à la question initiale : {question}", context_data=context_data,  oracle_expectations=oracle_expectations, session_id=session_id, run_id=run_id,max_retries=5)
            
            if final_result["status"] == "SUCCESS":
                main_span.update(output={"final_cypher": final_result["cypher"], "data": final_result["data"]})
            return final_result

        else:
            print("🎯 Question simple détectée. Résolution directe sans étapes.")
            final_result = resolve_query_with_retries(target_question=question, context_data={}, oracle_expectations=oracle_expectations, session_id=session_id, run_id=run_id, max_retries=max_retries)
            
            if final_result["status"] == "SUCCESS":
                main_span.update(output={"final_cypher": final_result["cypher"], "data": final_result["data"]})
            return final_result

















if __name__ == "__main__":
    q = " Find domain names for which at least 30 percent of the queries are made in japan. Return the domain name, domain name rank in Tranco, and the percentage of queries made in japan. " 
    # Quels sont les opérateurs télécoms africains qui dépendent le plus de l'infrastructure de Google ou d'Amazon pour accéder à Internet ?
    result = run_autonomous_loop(q)
    print("\nFinal Result:", json.dumps(result, indent=2))