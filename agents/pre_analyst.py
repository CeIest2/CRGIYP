import json, logging
from typing import Dict, Any
from utils.llm_caller import call_llm_with_tracking
from utils.helpers import load_schema_doc

logger = logging.getLogger(__name__)

def get_query_expectations(user_question: str, session_id: str = "pre_analyst_default", trace_id: str = None) -> Dict[str, Any]:
    
    schema_doc  = load_schema_doc()
    variables   = {"schema_doc": schema_doc, "question": user_question}
    response    = call_llm_with_tracking(prompt_name="iyp-pre-analyst", variables=variables, session_id=session_id, trace_id=trace_id, trace_name="pre_analysis", tags=["pre_analyst"], response_format="json")

    if response["success"]:
        try:
            content = json.loads(response["content"])
            # C'EST ICI QUE TOUT CHANGE : ON RÉCUPÈRE LES NOUVELLES CLÉS
            return {
                "success": True, 
                "real_world_context": content.get("real_world_context"), 
                "expected_data_type": content.get("expected_data_type"), 
                "is_empty_result_plausible": content.get("is_empty_result_plausible"),
                "rejection_conditions": content.get("rejection_conditions")
            }
        except json.JSONDecodeError:
            logger.error("LLM output could not be parsed as JSON.")
            return {"success": False, "error_message": "LLM output format error: expected valid JSON."}
    
    return response

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    print("\n" + "="*50 + "\nTESTING PRE-ANALYST AGENT\n" + "="*50)
    test_q = "What is Orange's market share in France?"
    result = get_query_expectations(test_q, session_id="test_pre_analyst")
    if result["success"]:
        print(f"✅ THEORETICAL: {result['theoretical_answer']}\n✅ ENTITIES: {result['expected_entities']}\n✅ COHERENCE: {result['coherence_check']}")
    else:
        print(f"❌ FAILED: {result.get('error_message')}")
    print("="*50 + "\n")