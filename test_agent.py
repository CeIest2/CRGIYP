import logging
import uuid
from langfuse import Langfuse
from agents.request_generator import generate_cypher_query
from agents.evaluator import evaluate_cypher_result
from DataBase.IYP_connector import test_cypher_on_iyp

# Initialisation du client Langfuse (v3)
langfuse = Langfuse()

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

def run_full_agent_test(question: str):
    # CORRECT : .hex génère une chaîne de 32 caractères hexadécimaux sans tirets
    run_id = uuid.uuid4().hex 
    session_id = "test_unified_trace"

    # Utilisation du gestionnaire de contexte (v3)
    with langfuse.start_as_current_observation(
        name="IYP_Full_Pipeline",
        as_type="span",
        trace_context={
            "trace_id": run_id,
            "session_id": session_id,
            "tags": ["e2e_test"]
        },
        input={"question": question}
    ) as main_span:

        print(f"\n🚀 STARTING PIPELINE | Trace ID: {run_id}")

        # --- STEP 1: GENERATION ---
        print(f"\n[1/3] GENERATING CYPHER...")
        gen_result = generate_cypher_query(question, session_id=session_id, trace_id=run_id)
        
        if not gen_result["success"]:
            print("❌ Generation failed.")
            main_span.update(level="ERROR", status_message="Generation failed")
            return

        # --- STEP 2: EXECUTION ---
        print(f"\n[2/3] EXECUTING ON IYP DATABASE...")
        db_result = test_cypher_on_iyp(gen_result["cypher"])

        # --- STEP 3: EVALUATION ---
        eval_verdict = evaluate_cypher_result(
            question=question,
            cypher=gen_result["cypher"],
            explanation=gen_result["explanation"],
            db_output=db_result,
            session_id=session_id,
            trace_id=run_id
        )

        # 4. Mise à jour de l'output final
        main_span.update(output=eval_verdict)

        print("\n" + "="*50)
        print("FINAL PIPELINE VERDICT")
        print("="*50)
        print(f"IS VALID: {eval_verdict.get('is_valid')}")
        print(f"ANALYSIS: {eval_verdict.get('analysis')}")
        print(f"UNIFIED TRACE ID (HEX): {run_id}")
        print("="*50 + "\n")

if __name__ == "__main__":
    run_full_agent_test("What is the market share of AS 3215 in France?")