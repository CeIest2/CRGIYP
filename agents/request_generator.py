import json
import logging
from typing import Dict, Any

# Internal imports from your project structure
from utils.llm_caller import call_llm_with_tracking
from utils.helpers import load_schema_doc

# Set up logging in English
logger = logging.getLogger(__name__)

def generate_cypher_query(user_question: str, session_id: str = "gen_session_default", trace_id: str = None) -> Dict[str, Any]:
    """
    Translates a natural language question into a Cypher query using the IYP schema.
    Returns a dictionary containing 'reasoning', 'cypher', and 'explanation'.
    """
    
    # 1. Load IYP Graph Schema Reference from docs/IYP_doc.md
    try:
        schema_doc = load_schema_doc()
    except Exception as e:
        logger.error(f"Failed to load schema documentation: {e}")
        return {"success": False, "error_message": f"Schema loading failed: {str(e)}"}

    # 2. Prepare variables for the Langfuse prompt template
    variables = {
        "schema_doc": schema_doc,
        "question": user_question
    }

    # 3. Call the LLM (Gemini) with integrated tracking
    logger.info(f"🧠 Reasoning and generating Cypher for: '{user_question[:50]}...'")
    
    # We use 'iyp-cypher-generator' which is the prompt name in your Langfuse
    response = call_llm_with_tracking(
        prompt_name="iyp-cypher-generator",
        variables=variables,
        session_id=session_id,
        trace_id=trace_id,
        trace_name="cypher_generation",
        tags=["generator"],
        response_format="json"  # Gemini 3 Flash returns structured JSON
    )

    # 4. Process the LLM response
    if response["success"]:
        try:
            # Parse the JSON string from 'content' into a Python dictionary
            content = json.loads(response["content"])
            return {
                "success": True,
                "reasoning": content.get("reasoning"),
                "cypher": content.get("cypher"),
                "explanation": content.get("explanation")
            }
        except json.JSONDecodeError:
            logger.error("LLM output could not be parsed as JSON.")
            return {
                "success": False, 
                "error_message": "LLM output format error: expected valid JSON."
            }
    
    # Return the error from llm_caller if the call failed
    return response

if __name__ == "__main__":
    # Configure basic logging for standalone test
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