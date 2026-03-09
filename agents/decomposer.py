import logging
from typing import Dict, Any, List
from pydantic import BaseModel, Field
from utils.llm_caller import call_llm_with_tracking
from utils.helpers import load_schema_doc

logger = logging.getLogger(__name__)

class SubQuestion(BaseModel):
    step_number: int            = Field(description="The sequential step number (e.g., 1, 2, 3).")
    intent: str                 = Field(description="A simple, highly specific natural language question for this step (e.g., 'What is the ASN of the AS with the highest population percent in country JP?').")
    expected_entity_output: str = Field(description="The specific data type expected to be passed to the next step (e.g., 'An Integer ASN', 'A list of Strings', 'None - Final Answer').")

class QueryDecomposition(BaseModel):
    is_complex: bool                 = Field(description="True if the question requires multiple logical steps. False if it's a simple lookup or a continuous path.")
    reasoning: str                   = Field(description="Step-by-step logic explaining why this requires 1 or multiple steps based on the graph topology. If it's a continuous path, state clearly that it should be 1 step.")
    sub_questions: List[SubQuestion] = Field(default_factory=list, description="List of sub-questions if is_complex is true. Empty list if false.")

# 🔥 Ajout du paramètre rag_examples avec une valeur par défaut sécurisée
def decompose_query(user_question: str, oracle_filters: str = "None", session_id: str = "decomposer_default", trace_id: str = None, trace_name: str = "query_decomposition", rag_examples: str = "No relevant examples found.") -> Dict[str, Any]:
    
    schema_doc = load_schema_doc()
    
    # 🔥 Injection dans les variables pour le template Langfuse
    variables  = {
        "schema_doc": schema_doc, 
        "implicit_filters": oracle_filters, 
        "question": user_question,
        "rag_examples": rag_examples
    }
    
    response   = call_llm_with_tracking(prompt_name="iyp-decomposer", variables=variables, session_id=session_id, model_name="gemini-2.5-flash", trace_id=trace_id, trace_name=trace_name, tags=["decomposer"], pydantic_schema=QueryDecomposition )
    
    if response["success"]:
        content            = response["content"]
        sub_questions_list = [sq.model_dump() for sq in content.sub_questions]
        
        return {"success": True, "is_complex": content.is_complex,"reasoning": content.reasoning,"sub_questions": sub_questions_list}
    
    return response