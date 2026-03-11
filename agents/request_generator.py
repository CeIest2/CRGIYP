import logging
from typing import Dict, Any
from pydantic import BaseModel, Field

from utils.llm_caller import call_llm_with_tracking
from utils.helpers import load_schema_doc

logger = logging.getLogger(__name__)

class CypherGeneration(BaseModel):
    reasoning: str   = Field(description="Step-by-step explanation of the chosen nodes/relationships. Explicitly mention any strategy changes based on previous attempts.")
    cypher: str      = Field(description="The executable Cypher query.")
    explanation: str = Field(description="A detailed technical explanation of how the query works.")

def generate_cypher_query(user_question: str, session_id: str = "gen_session_default", trace_id: str = None, model: str = "gemini-2.5-flash", previous_history: str = "No previous attempts.", trace_name: str = "cypher_generation", rag_examples: str = "No relevant examples found.") -> Dict[str, Any]:

    schema_doc = load_schema_doc()
    
    variables = {
        "schema_doc": schema_doc, 
        "question": user_question, 
        "previous_history": previous_history,
        "rag_examples": rag_examples
    }
    
    response = call_llm_with_tracking(prompt_name="iyp-cypher-generator", variables=variables, model_name=model,thinking_budget=0, session_id=session_id, trace_id=trace_id, trace_name=trace_name, tags=["generator"], pydantic_schema=CypherGeneration) 
    
    if response["success"]:
        content = response["content"]
        return {"success": True,"reasoning": content.reasoning,"cypher": content.cypher,"explanation": content.explanation}
    
    return response

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    
    print("\n" + "="*50)
    print("TESTING REQUEST GENERATOR AGENT")
    print("="*50)

    test_q = "How many ASNs are registered in France?"
    
    result = generate_cypher_query(test_q, session_id="standalone_gen_test")
    
    if result["success"]:
        print(f"✅ REASONING: {result['reasoning']}")
        print(f"✅ CYPHER: {result['cypher']}")
        print(f"✅ EXPLANATION: {result['explanation']}")
    else:
        print(f"❌ GENERATION FAILED: {result.get('error_message')}")
    print("="*50 + "\n")