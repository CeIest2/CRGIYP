import json
import logging
from typing import Dict, Any, Optional, Literal
from pydantic import BaseModel, Field

from utils.llm_caller import call_llm_with_tracking
from utils.helpers import load_schema_doc, format_db_output

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


class QueryEvaluation(BaseModel):
    is_valid: bool                 = Field(description="True if the generated Cypher query accurately and safely solved the user's problem based purely on the database output.")
    analysis: str                  = Field(description="A detailed analysis in English justifying your decision based on the output data.")
    correction_hint: Optional[str] = Field(default=None, description="Specific instructions to fix the query (or null if valid).")
    error_type: Literal["SYNTAX", "HALLUCINATION", "LOGIC", "EMPTY_BUT_SUSPICIOUS", "ORACLE_REJECTION", "NONE"] = Field(description="The exact category of the error. Use 'NONE' if the query is valid.")


def evaluate_cypher_result(
    question: str,
    cypher: str,
    explanation: str,
    db_output: Any,
    session_id: str = "eval_session_default",
    trace_id: str = None,
    oracle_expectations: Dict[str, Any] = None,
    trace_name: str = "cypher_evaluation",
) -> Dict[str, Any]:

    try:
        schema_doc = load_schema_doc()
    except Exception as e:
        return {"is_valid": False, "error_type": "SYSTEM", "analysis": f"Schema load failed: {e}"}

    variables = {
        "question":            question,
        "cypher":              cypher,
        "explanation":         explanation,
        "db_output":           format_db_output(db_output),
        "schema_doc":          schema_doc,
        "oracle_expectations": json.dumps(oracle_expectations, indent=2, ensure_ascii=False)
                               if oracle_expectations
                               else "No oracle expectations provided.",
    }

    logger.info(f"🔎 Evaluating query for: '{question[:50]}...'")
    response = call_llm_with_tracking(
        prompt_name="iyp-query-evaluator",
        variables=variables,
        session_id=session_id,
        model_name="gemini-2.5-flash-lite",
        trace_id=trace_id,
        trace_name=trace_name,
        tags=["evaluator"],
        pydantic_schema=QueryEvaluation,
    )

    if not response["success"]:
        return {
            "is_valid":   False,
            "error_type": "SYSTEM",
            "analysis":   f"LLM error: {response['error_message']}",
        }

    content = response["content"]
    return {
        "is_valid":        content.is_valid,
        "error_type":      content.error_type,
        "analysis":        content.analysis,
        "correction_hint": content.correction_hint,
    }