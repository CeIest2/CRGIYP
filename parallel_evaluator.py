import json
import time
import concurrent.futures
import logging
import threading
import os
from DataBase.IYP_connector import test_cypher_on_iyp
from utils.llm_caller import call_llm_with_tracking
from pydantic import BaseModel, Field

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger    = logging.getLogger(__name__)
save_lock = threading.Lock()

class SemanticComparison(BaseModel):
    is_equivalent: bool = Field(description="True if the generated data provides the same factual answer as the canonical data, regardless of column names or row order.")
    reasoning: str      = Field(description="A concise technical justification explaining why the results are or are not semantically identical.")

def execute_queries_in_parallel(generated_cypher: str, canonical_cypher: str):
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        future_gen = executor.submit(test_cypher_on_iyp, generated_cypher)
        future_can = executor.submit(test_cypher_on_iyp, canonical_cypher)
        res_gen = future_gen.result()
        res_can = future_can.result()
    return res_gen, res_can

def truncate_data_structure(data, max_str_len=500):
    if isinstance(data, dict):
        return {k: truncate_data_structure(v, max_str_len) for k, v in data.items()}
    elif isinstance(data, list):
        return [truncate_data_structure(i, max_str_len) for i in data]
    elif isinstance(data, str):
        return data[:max_str_len] + " [TRUNCATED...]" if len(data) > max_str_len else data
    return data

def format_db_result(db_result):
    if not db_result.get("success"):
        return f"Neo4j Error: {db_result.get('message', 'Unknown error')}"
    
    data = db_result.get("data", [])
    row_limit = 15 
    is_row_truncated = len(data) > row_limit
    safe_data = truncate_data_structure(data[:row_limit], max_str_len=500)
    output = json.dumps(safe_data, ensure_ascii=False, default=str, indent=2)
    
    if len(output) > 8000:
        output = output[:8000] + "\n... [SAFETY TRUNCATION]"
    if is_row_truncated:
        output += f"\n... (And {len(data) - row_limit} more rows)"
        
    return output

def evaluate_semantic_equivalence(question: str, res_gen: dict, res_can: dict, session_id: str, task_id: str):
    variables = {"question": question,"generated_result": format_db_result(res_gen),"canonical_result": format_db_result(res_can)}
    
    response = call_llm_with_tracking(
        prompt_name="iyp-results-comparator",
        variables=variables,
        session_id=session_id,  
        model_name="gemini-2.5-flash", 
        trace_name=f"semantic_eval_task_{task_id}", 
        tags=["semantic_evaluation", f"task_{task_id}", "functional_correctness"], 
        pydantic_schema=SemanticComparison 
    )
    
    if response.get("success"):
        content = response["content"]
        return {
            "is_equivalent": content.is_equivalent,
            "reasoning": content.reasoning
        }
    
    return {
        "is_equivalent": False, 
        "reasoning": f"LLM Error: {response.get('error_message', 'Unknown error')}"
    }

def process_single_task(task, session_id, benchmark_data, output_json_path):
    """Thread function to process a single benchmark entry."""
    task_id = task.get('task_id', 'unknown')
    question = task.get("prompt")
    gen_cypher = task.get("generated_cypher")
    can_cypher = task.get("canonical_cypher")
    difficulty = task.get("difficulty", "Unknown")

    if gen_cypher == "None" or not gen_cypher or not can_cypher:
        task["semantic_evaluation"] = {"is_equivalent": False, "reasoning": "Missing or invalid query."}
    else:
        try:
            logger.info(f"Task {task_id}: Executing queries on Neo4j...")
            res_gen, res_can = execute_queries_in_parallel(gen_cypher, can_cypher)
            
            if not res_gen.get("success"):
                task["semantic_evaluation"] = {"is_equivalent": False, "reasoning": f"Neo4j Error on generated query: {res_gen.get('message')}"}
            else:
                logger.info(f"Task {task_id}: Starting LLM Semantic Analysis...")
                eval_result = evaluate_semantic_equivalence(question, res_gen, res_can, session_id, task_id)
                task["semantic_evaluation"] = eval_result
        except Exception as e:
            logger.error(f"Task {task_id}: Internal Error: {str(e)}")
            task["semantic_evaluation"] = {"is_equivalent": False, "reasoning": f"Internal Exception during execution: {str(e)}"}

    with save_lock:
        is_success = task["semantic_evaluation"].get("is_equivalent", False)
        
        stats_run = benchmark_data.setdefault("stats_current_run", {})
        global_stats = stats_run.setdefault("global", {})
        diff_stats = stats_run.setdefault("by_difficulty", {}).setdefault(difficulty, {})
        
        key_success = "success_compa"
        key_failed  = "failed_compa"
        
        if is_success:
            global_stats[key_success] = global_stats.get(key_success, 0) + 1
            diff_stats[key_success] = diff_stats.get(key_success, 0) + 1
        else:
            global_stats[key_failed] = global_stats.get(key_failed, 0) + 1
            diff_stats[key_failed] = diff_stats.get(key_failed, 0) + 1

        total_eval = global_stats.get(key_success, 0) + global_stats.get(key_failed, 0)
        global_stats["success_rate_compa"] = round((global_stats[key_success] / total_eval) * 100, 2) if total_eval > 0 else 0

        try:
            with open(output_json_path, 'w', encoding='utf-8') as out_f:
                json.dump(benchmark_data, out_f, indent=4, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to write to {output_json_path}: {e}")
            
    status_icon = "✅" if task["semantic_evaluation"].get("is_equivalent") else "❌"
    logger.info(f"Task {task_id}: Finished {status_icon}")
    
    return task

def run_parallel_post_benchmark(input_json_path: str, output_json_path: str, max_parallel_tasks: int = 10):
    """Launches semantic evaluation of the entire benchmark in parallel."""
    if not os.path.exists(input_json_path):
        logger.error(f"Input file not found: {input_json_path}")
        return

    try:
        with open(input_json_path, 'r', encoding='utf-8') as f:
            benchmark_data = json.load(f)
    except json.JSONDecodeError as e:
        logger.error(f"JSON Decode Error: {e}")
        return
        
    original_session = benchmark_data.get("session_id", f"run_{int(time.time())}")
    eval_session_id  = f"{original_session}_SEMANTIC_EVAL"
    details          = benchmark_data.get("details", [])
    
    stats_run        = benchmark_data.setdefault("stats_current_run", {})
    global_stats     = stats_run.setdefault("global", {})

    global_stats.update({"success_compa": 0, "failed_compa": 0, "success_rate_compa": 0})
    
    by_diff = stats_run.setdefault("by_difficulty", {})
    for diff in by_diff.keys():
        by_diff[diff].update({"success_compa": 0, "failed_compa": 0})
    
    logger.info(f"🚀 Starting Parallel Evaluation ({max_parallel_tasks} tasks)...")
    logger.info(f"📊 Langfuse Session: {eval_session_id}")
    
    start_time = time.time()

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_parallel_tasks) as executor:
        futures = [executor.submit(process_single_task, task, eval_session_id, benchmark_data, output_json_path) for task in details]
        concurrent.futures.wait(futures)

    duration = time.time() - start_time
    
    final_success = benchmark_data["stats_current_run"]["global"]["success_compa"]
    final_failed  = benchmark_data["stats_current_run"]["global"]["failed_compa"]
    final_rate    = benchmark_data["stats_current_run"]["global"]["success_rate_compa"]
    
    print(f"\n🏁 Evaluation finished in {duration:.2f}s! Results saved in {output_json_path}")
    print(f"📊 Final Comparative Score: {final_success} Success | {final_failed} Failures ({final_rate}%)")

if __name__ == "__main__":
    
    INPUT_FILE  = "benchmark_report_20260309_1103.json" 
    OUTPUT_FILE = "benchmark_report_SEMANTIC_EVAL_PARALLEL_last_lundi_last_before_rag.json"

    run_parallel_post_benchmark(INPUT_FILE, OUTPUT_FILE, max_parallel_tasks=20)