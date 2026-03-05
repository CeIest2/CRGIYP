import json,logging
from typing import Dict, Any
from utils.llm_caller import call_llm_with_tracking
from utils.helpers import load_schema_doc

logger = logging.getLogger(__name__)

def generate_cypher_query(user_question: str, session_id: str = "gen_session_default", trace_id: str = None, previous_history: str = "No previous attempts.") -> Dict[str, Any]:

    schema_doc  = load_schema_doc()
    variables   = {"schema_doc": schema_doc, "question": user_question, "previous_history": previous_history}
    response    = call_llm_with_tracking(prompt_name="iyp-cypher-generator", variables=variables, session_id=session_id, trace_id=trace_id, trace_name="cypher_generation", tags=["generator"], response_format="json" )

    if response["success"]:
        try:
            content = json.loads(response["content"])
            return {"success": True,"reasoning": content.get("reasoning"),"cypher": content.get("cypher"),"explanation": content.get("explanation")}
        except json.JSONDecodeError:
            logger.error("LLM output could not be parsed as JSON.")
            return {"success": False, "error_message": "LLM output format error: expected valid JSON."}
    
    return response









if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    
    print("\n" + "="*50)
    print("TESTING REQUEST GENERATOR AGENT")
    print("="*50)

    test_q = "How many ASNs are registered in France?"
    
    # Perform generation
    result = generate_cypher_query(test_q, session_id="standalone_gen_test")
    
    if result["success"]:
        print(f"✅ REASONING: {result['reasoning']}")
        print(f"✅ CYPHER: {result['cypher']}")
        print(f"✅ EXPLANATION: {result['explanation']}")
    else:
        print(f"❌ GENERATION FAILED: {result.get('error_message')}")
    print("="*50 + "\n")