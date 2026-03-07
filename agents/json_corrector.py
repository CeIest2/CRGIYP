import json, logging
from typing import Dict, Any
from utils.llm_caller import call_llm_with_tracking

logger = logging.getLogger(__name__)

def fix_malformed_json(malformed_string: str, session_id: str = "json_corrector_default", trace_id: str = None) -> Dict[str, Any]:
    logger.info("🛠️ Lancement de l'agent correcteur de JSON...")
    
    variables = {
        "malformed_json": malformed_string
    }
    
    response = call_llm_with_tracking(
        prompt_name="iyp-json-corrector", 
        variables=variables, 
        session_id=session_id, 
        model_name="gemini-2.5-flash-lite", 
        trace_id=trace_id, 
        trace_name="json_correction", 
        tags=["json_corrector", "auto_healing"], 
        response_format="json"
    )
    
    if response["success"]:
        return {"success": True, "fixed_json_string": response["content"]}
    
    return response