import json
import time
import concurrent.futures
import logging
import threading
import re
from DataBase.IYP_connector import test_cypher_on_iyp
from utils.llm_caller import call_llm_with_tracking

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

save_lock = threading.Lock()

def clean_and_parse_json(text: str) -> dict:
    """Solution ultra-robuste pour extraire et parser le JSON d'un LLM."""
    if not text:
        raise ValueError("Texte vide fourni par le LLM.")
        
    text = text.strip()
    
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    text_clean = re.sub(r'^```[a-zA-Z]*\n', '', text)
    text_clean = re.sub(r'\n```$', '', text_clean)
    text_clean = text_clean.strip()
    
    try:
        return json.loads(text_clean)
    except json.JSONDecodeError:
        pass

    match = re.search(r'(\{[\s\S]*\})', text)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError as e:
            raise ValueError(f"JSON trouvé par regex mais invalide : {str(e)}")
            
    raise ValueError("Aucun format JSON valide détecté dans la réponse.")


def execute_queries_in_parallel(generated_cypher: str, canonical_cypher: str):
    """Exécute les deux requêtes en parallèle sur Neo4j."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        future_gen = executor.submit(test_cypher_on_iyp, generated_cypher)
        future_can = executor.submit(test_cypher_on_iyp, canonical_cypher)
        res_gen = future_gen.result()
        res_can = future_can.result()
    return res_gen, res_can

def truncate_data_structure(data, max_str_len=500):
    """Tronque les chaînes de caractères trop longues pour épargner le contexte du LLM."""
    if isinstance(data, dict):
        return {k: truncate_data_structure(v, max_str_len) for k, v in data.items()}
    elif isinstance(data, list):
        return [truncate_data_structure(i, max_str_len) for i in data]
    elif isinstance(data, str):
        return data[:max_str_len] + " [TRONQUÉ...]" if len(data) > max_str_len else data
    return data

def format_db_result(db_result):
    """Prépare le résultat de la base de données pour le prompt LLM."""
    if not db_result.get("success"):
        return f"Erreur Neo4j: {db_result.get('message', 'Erreur inconnue')}"
    
    data = db_result.get("data", [])
    row_limit = 15 
    is_row_truncated = len(data) > row_limit
    safe_data = truncate_data_structure(data[:row_limit], max_str_len=500)
    output = json.dumps(safe_data, ensure_ascii=False, default=str, indent=2)
    
    if len(output) > 8000:
        output = output[:8000] + "\n... [TRONCATURE DE SÉCURITÉ]"
    if is_row_truncated:
        output += f"\n... (Et {len(data) - row_limit} autres lignes)"
        
    return output

def evaluate_semantic_equivalence(question: str, res_gen: dict, res_can: dict, session_id: str, task_id: str):
    """Demande au LLM de comparer les résultats, avec Tracking Langfuse."""
    variables = {
        "question": question,
        "generated_result": format_db_result(res_gen),
        "canonical_result": format_db_result(res_can)
    }
    
    response = call_llm_with_tracking(
        prompt_name="iyp-results-comparator",
        variables=variables,
        session_id=session_id,  
        model_name="gemini-2.5-flash", 
        trace_name=f"semantic_eval_task_{task_id}", 
        tags=["semantic_evaluation", f"task_{task_id}"], 
        response_format="json"
    )
    
    if response.get("success"):
        raw_content = response.get("content", "")
        try:
            parsed_json = clean_and_parse_json(raw_content)
            
            is_equiv = parsed_json.get("is_equivalent", False)
            if isinstance(is_equiv, str):
                is_equiv = is_equiv.lower() == "true"
                
            return {
                "is_equivalent": is_equiv,
                "reasoning": parsed_json.get("reasoning", "Aucune explication fournie.")
            }
            
        except Exception as e:
            logging.error(f"Erreur parsing JSON LLM. Trace: semantic_eval_task_{task_id} | Erreur: {e}")
            return {"is_equivalent": False, "reasoning": f"Échec critique du parsing JSON LLM: {str(e)}"}
            
    return {"is_equivalent": False, "reasoning": f"Erreur de l'API LLM: {response.get('error_message')}"}

def process_single_task(task, session_id, benchmark_data, output_json_path):
    """Fonction exécutée par chaque thread."""
    task_id = task.get('task_id', 'unknown')
    question = task.get("prompt")
    gen_cypher = task.get("generated_cypher")
    can_cypher = task.get("canonical_cypher")

    if gen_cypher == "None" or not gen_cypher or not can_cypher:
        task["semantic_evaluation"] = {"is_equivalent": False, "reasoning": "Requête manquante."}
        return task

    try:
        logging.info(f"Task {task_id}: Exécution des requêtes sur Neo4j...")
        res_gen, res_can = execute_queries_in_parallel(gen_cypher, can_cypher)
        
        if not res_gen.get("success"):
            task["semantic_evaluation"] = {"is_equivalent": False, "reasoning": "Erreur Neo4j sur la requête générée."}
        else:
            logging.info(f"Task {task_id}: Analyse sémantique LLM en cours...")
            eval_result = evaluate_semantic_equivalence(question, res_gen, res_can, session_id, task_id)
            task["semantic_evaluation"] = eval_result

        # Sauvegarde incrémentale sécurisée (Verrou)
        with save_lock:
            with open(output_json_path, 'w', encoding='utf-8') as out_f:
                json.dump(benchmark_data, out_f, indent=4, ensure_ascii=False)
        
        status = "✅" if task["semantic_evaluation"].get("is_equivalent") else "❌"
        logging.info(f"Task {task_id}: Terminée {status}")

    except Exception as e:
        logging.error(f"Task {task_id}: Erreur interne : {str(e)}")
        task["semantic_evaluation"] = {"is_equivalent": False, "reasoning": f"Exception interne: {str(e)}"}
    
    return task

def run_parallel_post_benchmark(input_json_path: str, output_json_path: str, max_parallel_tasks: int = 10):
    """Lance l'évaluation sémantique de tout le benchmark en parallèle."""
    with open(input_json_path, 'r', encoding='utf-8') as f:
        benchmark_data = json.load(f)
        
    original_session = benchmark_data.get("session_id", f"run_{int(time.time())}")
    eval_session_id = f"{original_session}_SEMANTIC_EVAL"
    
    details = benchmark_data.get("details", [])
    
    print(f"🚀 Lancement de l'évaluation ({max_parallel_tasks} tâches simultanées)...")
    print(f"📊 Session Langfuse : {eval_session_id}")
    start_time = time.time()

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_parallel_tasks) as executor:
        futures = [executor.submit(process_single_task, task, eval_session_id, benchmark_data, output_json_path) for task in details]
        concurrent.futures.wait(futures)

    end_time = time.time()
    duration = end_time - start_time
    print(f"\n🏁 Évaluation terminée en {duration:.2f}s ! Résultats dans {output_json_path}")

if __name__ == "__main__":
    INPUT_FILE = "benchmark_report_20260307_2314.json" # Nom de votre dernier rapport
    OUTPUT_FILE = "benchmark_report_SEMANTIC_EVAL_PARALLEL.json"
    
    run_parallel_post_benchmark(INPUT_FILE, OUTPUT_FILE, max_parallel_tasks=10)