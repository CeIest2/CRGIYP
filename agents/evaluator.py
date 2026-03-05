import json,logging,os
from typing import Dict, Any
from utils.llm_caller import call_llm_with_tracking
from utils.helpers import load_schema_doc, format_db_output
from DataBase.IYP_connector import test_cypher_on_iyp

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def evaluate_cypher_result(question: str, cypher: str, explanation: str, db_output: Any, session_id: str = "eval_session_default",trace_id: str = None ) -> Dict[str, Any]:
    try:
        schema_doc = load_schema_doc()
    except Exception as e:
        return {"is_valid": False, "error_type": "SYSTEM", "analysis": f"Schema load failed: {e}"}

    variables = {"question": question, "cypher": cypher, "explanation": explanation, "db_output": format_db_output(db_output), "schema_doc": schema_doc}
    logger.info(f"🔎 Evaluating query for question: '{question[:50]}...'")
    response = call_llm_with_tracking(prompt_name="iyp-query-evaluator", variables=variables, session_id=session_id, trace_id=trace_id, trace_name="cypher_evaluation", tags=["evaluator"], response_format="json")

    if not response["success"]:
        return {"is_valid": False, "error_type": "SYSTEM", "analysis": f"LLM error: {response['error_message']}"}

    try:
        return json.loads(response["content"])
    except json.JSONDecodeError:
        return {"is_valid": False, "error_type": "SYSTEM", "analysis": "Invalid JSON response."}
    

if __name__ == "__main__":
    print("\n" + "="*50)
    print("RUNNING FULL PIPELINE TEST (ENGLISH)")
    print("="*50)

    test_question = "What is the market share of Orange (AS 3215) in France?"
    session_id = "full_pipeline_test_001"

    print(f"\n[1/3] GENERATING CYPHER...")
    gen_response = call_llm_with_tracking(
        prompt_name="iyp-cypher-generator",
        variables={"schema_doc": load_schema_doc(), "question": test_question},
        session_id=session_id,
        trace_name="test_generation",
        response_format="json"
    )

    if not gen_response["success"]:
        print(f"❌ Generation failed: {gen_response['error_message']}")
        exit(1)

    gen_data = json.loads(gen_response["content"])
    generated_cypher = gen_data.get("cypher")
    generated_explanation = gen_data.get("explanation")

    print(f"✅ Generated Cypher: {generated_cypher}")

    # --- STEP 2: EXECUTION ---
    print(f"\n[2/3] EXECUTING ON IYP DATABASE...")
    db_result = test_cypher_on_iyp(generated_cypher)

    if db_result["success"]:
        print(f"✅ DB Success: Found {len(db_result['data'])} records.")
    else:
        print(f"❌ DB Error: {db_result.get('message')}")

    # --- STEP 3: EVALUATION ---
    print(f"\n[3/3] EVALUATING RESULTS...")
    eval_verdict = evaluate_cypher_result(question=test_question, cypher=generated_cypher, explanation=generated_explanation, db_output=db_result, session_id=session_id)

    # --- FINAL SUMMARY ---
    print("\n" + "="*50)
    print("FINAL EVALUATION VERDICT")
    print("="*50)
    print(f"IS VALID: {eval_verdict.get('is_valid')}")
    print(f"ERROR TYPE: {eval_verdict.get('error_type')}")
    print(f"ANALYSIS: {eval_verdict.get('analysis')}")
    
    if eval_verdict.get("correction_hint"):
        print(f"HINT: {eval_verdict.get('correction_hint')}")
    print("="*50 + "\n")