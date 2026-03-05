import json, logging
from typing import Dict, Any
from utils.llm_caller import call_llm_with_tracking
from DataBase.IYP_connector import test_cypher_on_iyp

logger = logging.getLogger(__name__)

def run_investigation(question: str, failed_cypher: str, error_message: str, session_id: str, trace_id: str = None, previous_history: str = "No previous attempts.") -> str:
    logger.info("🕵️‍♂️ Starting Investigation Phase...")

    diag_vars = {"question": question, "failed_cypher": failed_cypher, "error_message": error_message, "previous_history": previous_history  }
    
    diag_response = call_llm_with_tracking(prompt_name="iyp-investigator-diagnostic", variables=diag_vars, session_id=session_id, trace_id=trace_id, trace_name="investigator_diagnostic", tags=["investigator"], response_format="json")

    test_queries = []
    if not diag_response["success"]:
        return {"report": f"Investigator Error (Diagnostic): {diag_response['error_message']}", "queries_tested": test_queries}

    try:
        diag_data = json.loads(diag_response["content"])
        test_queries = diag_data.get("test_queries", [])
    except json.JSONDecodeError:
        return {"report": "The investigator failed to generate a valid JSON for its tests.", "queries_tested": test_queries}

    if not test_queries:
        return {"report": "The investigator did not find any relevant tests to perform.", "queries_tested": test_queries}

    test_results_summary = []
    for i, q in enumerate(test_queries[:3]):
        logger.info(f"🕵️‍♂️ Executing test {i+1}: {q}")
        db_res = test_cypher_on_iyp(q)
        
        if db_res.get("success"):
            data_str = json.dumps(db_res.get('data'), ensure_ascii=False)[:500] 
            test_results_summary.append(f"Test Query: {q}\nResult: {data_str}")
        else:
            test_results_summary.append(f"Test Query: {q}\nResult: ERROR - {db_res.get('message')}")

    synth_vars     = {"question": question, "failed_cypher": failed_cypher, "test_results": "\n\n".join(test_results_summary)}
    synth_response = call_llm_with_tracking(prompt_name="iyp-investigator-synthesis", variables=synth_vars, session_id=session_id, trace_id=trace_id, trace_name="investigator_synthesis", tags=["investigator"], response_format="json")

    if synth_response["success"]:
        try:
            synth_data = json.loads(synth_response["content"])
            return {"report": synth_data.get("investigation_report", "No report generated."), "queries_tested": test_queries}
        except json.JSONDecodeError:
            return {"report": "The investigator failed to format its final report.", "queries_tested": test_queries}
            
    return {"report": "Investigation synthesis failed.", "queries_tested": test_queries}