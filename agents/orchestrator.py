import logging, uuid, json
from langfuse import Langfuse
from agents.pre_analyst import get_query_expectations 
from agents.request_generator import generate_cypher_query
from agents.evaluator import evaluate_cypher_result
from DataBase.IYP_connector import test_cypher_on_iyp
from agents.investigator import run_investigation 
langfuse = Langfuse()
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

def run_autonomous_loop(question: str, max_retries: int = 5):
    run_id = uuid.uuid4().hex
    session_id = f"session_{uuid.uuid4().hex[:8]}"
    history = "No previous attempts."
    
    with langfuse.start_as_current_observation(name="Autonomous_Cypher_Pipeline", as_type="span", trace_context={"trace_id": run_id, "session_id": session_id}, input={"question": question}) as main_span:

        oracle_res          = get_query_expectations(question, session_id=session_id, trace_id=run_id)
        oracle_expectations = None
        if oracle_res.get("success"):
            oracle_expectations = {"real_world_context": oracle_res.get("real_world_context"), "expected_data_type": oracle_res.get("expected_data_type"), "is_empty_result_plausible": oracle_res.get("is_empty_result_plausible"), "rejection_conditions": oracle_res.get("rejection_conditions")}

        for attempt in range(max_retries):
            current_attempt = attempt + 1
            print(f"\n--- 🔄 ATTEMPT {current_attempt}/{max_retries} ---")

            gen_result = generate_cypher_query(question, session_id=session_id, trace_id=run_id, previous_history=history)
            
            if not gen_result["success"]:
                print(f"❌ Critical Generation Error: {gen_result.get('error_message')}")
                break

            cypher       = gen_result["cypher"]
            explanation  = gen_result["explanation"]
            db_result    = test_cypher_on_iyp(cypher)
            eval_verdict = evaluate_cypher_result(question=question, cypher=cypher, explanation=explanation, db_output=db_result, session_id=session_id, trace_id=run_id, oracle_expectations=oracle_expectations)

            if eval_verdict.get("is_valid"):
                print(f"✅ SUCCESS at attempt {current_attempt}!")
                main_span.update(output={"final_cypher": cypher, "data": db_result.get("data")})
                return {"status": "SUCCESS","iterations": current_attempt,"cypher": cypher,"data": db_result.get("data")}
            
            else:
                error_type = eval_verdict.get('error_type')
                analysis = eval_verdict.get('analysis')
                print(f"⚠️ Validation Failed [{error_type}]. Launching Investigator...")
                
                investigation_result = run_investigation(question=question, failed_cypher=cypher, error_message=f"Error Type: {error_type} | Analysis: {analysis}", session_id=session_id, trace_id=run_id, previous_history=history )
                
                investigation_report = investigation_result.get("report", "No report.")
                queries_tested       = investigation_result.get("queries_tested", [])
                
                print(f"🕵️‍♂️ Investigator Report: {investigation_report}")

                queries_tested_str = ""
                if queries_tested:
                    for i, qt in enumerate(queries_tested):
                        queries_tested_str += f"  {i+1}. {qt}\n"
                else:
                    queries_tested_str = "  Aucun test effectué.\n"

                attempt_summary = (
                    f"\n[TENTATIVE {current_attempt}]\n"
                    f"- REQUÊTE TENTÉE : {cypher}\n"
                    f"- REJET DE L'ÉVALUATEUR : [{error_type}] {analysis}\n"
                    f"- TESTS DÉJÀ EFFECTUÉS PAR L'ENQUÊTEUR :\n{queries_tested_str}"
                    f"- CONCLUSION DE L'ENQUÊTE {current_attempt} : {investigation_report}\n"
                )
                
                if history == "No previous attempts.":
                    history = attempt_summary
                else:
                    history += attempt_summary

        print(f"❌ Failed to generate a valid query after {max_retries} attempts.")
        main_span.update(level="ERROR", status_message="Max retries reached")
        return {"status": "FAILED", "iterations": max_retries}














if __name__ == "__main__":
    q = "Quels sont les noms des 5 entreprises au Royaume-Uni qui ont la plus grosse part de marché, mais qui gèrent aussi plus de 1 préfixes IP ?"
    result = run_autonomous_loop(q)
    print("\nFinal Result:", json.dumps(result, indent=2))