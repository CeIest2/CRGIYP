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

def evaluate_semantic_equivalence(question: str, res_gen: dict, res_can: dict, session_id: str, task_id: str, max_retries: int = 3):
    """Demande au LLM de comparer les résultats, avec système de retry en cas de mauvais JSON."""
    variables = {
        "question": question,
        "generated_result": format_db_result(res_gen),
        "canonical_result": format_db_result(res_can)
    }
    
    for attempt in range(max_retries):
        response = call_llm_with_tracking(
            prompt_name="iyp-results-comparator",
            variables=variables,
            session_id=session_id,  
            model_name="gemini-2.5-flash", 
            trace_name=f"semantic_eval_task_{task_id}_attempt_{attempt+1}", 
            tags=["semantic_evaluation", f"task_{task_id}"], 
            response_format="json",
            temperature=0.1
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
                logging.warning(f"Task {task_id} - Tentative {attempt+1}/{max_retries}: Mauvais JSON généré. Nouvelle tentative... (Erreur: {e})")
        else:
            logging.error(f"Task {task_id} - Tentative {attempt+1}: Erreur de l'API LLM: {response.get('error_message')}")
            
    return {"is_equivalent": False, "reasoning": f"Échec critique du parsing JSON après {max_retries} tentatives."}

def process_single_task(task, session_id, benchmark_data, output_json_path):
    """Fonction exécutée par chaque thread."""
    task_id = task.get('task_id', 'unknown')
    question = task.get("prompt")
    gen_cypher = task.get("generated_cypher")
    can_cypher = task.get("canonical_cypher")
    difficulty = task.get("difficulty", "Unknown")

    if gen_cypher == "None" or not gen_cypher or not can_cypher:
        task["semantic_evaluation"] = {"is_equivalent": False, "reasoning": "Requête manquante."}
    else:
        try:
            logging.info(f"Task {task_id}: Exécution des requêtes sur Neo4j...")
            res_gen, res_can = execute_queries_in_parallel(gen_cypher, can_cypher)
            
            if not res_gen.get("success"):
                task["semantic_evaluation"] = {"is_equivalent": False, "reasoning": "Erreur Neo4j sur la requête générée."}
            else:
                logging.info(f"Task {task_id}: Analyse sémantique LLM en cours...")
                eval_result = evaluate_semantic_equivalence(question, res_gen, res_can, session_id, task_id)
                task["semantic_evaluation"] = eval_result
        except Exception as e:
            logging.warning(f"Task {task_id} - Mauvais JSON. Erreur: {e}")
            logging.warning(f"Texte brut reçu du LLM : {raw_content}")
            logging.error(f"Task {task_id}: Erreur interne : {str(e)}")
            task["semantic_evaluation"] = {"is_equivalent": False, "reasoning": f"Exception interne: {str(e)}"}

    # Sauvegarde incrémentale sécurisée (Verrou)
    with save_lock:
        is_success = task["semantic_evaluation"].get("is_equivalent", False)
        
        # Récupération des blocs de stats
        stats_run = benchmark_data.setdefault("stats_current_run", {})
        global_stats = stats_run.setdefault("global", {})
        diff_stats = stats_run.setdefault("by_difficulty", {}).setdefault(difficulty, {})
        
        # Mise à jour incrémentale
        if is_success:
            global_stats["success_compa"] = global_stats.get("success_compa", 0) + 1
            diff_stats["success_compa"] = diff_stats.get("success_compa", 0) + 1
        else:
            global_stats["failed_compa"] = global_stats.get("failed_compa", 0) + 1
            diff_stats["failed_compa"] = diff_stats.get("failed_compa", 0) + 1

        # Calcul du pourcentage incrémental
        total_eval = global_stats["success_compa"] + global_stats["failed_compa"]
        global_stats["success_rate_compa"] = round((global_stats["success_compa"] / total_eval) * 100, 2) if total_eval > 0 else 0

        # Écriture dans le fichier en temps réel
        with open(output_json_path, 'w', encoding='utf-8') as out_f:
            json.dump(benchmark_data, out_f, indent=4, ensure_ascii=False)
            
    status = "✅" if task["semantic_evaluation"].get("is_equivalent") else "❌"
    logging.info(f"Task {task_id}: Terminée {status}")
    
    return task

def run_parallel_post_benchmark(input_json_path: str, output_json_path: str, max_parallel_tasks: int = 10):
    """Lance l'évaluation sémantique de tout le benchmark en parallèle."""
    with open(input_json_path, 'r', encoding='utf-8') as f:
        benchmark_data = json.load(f)
        
    original_session = benchmark_data.get("session_id", f"run_{int(time.time())}")
    eval_session_id = f"{original_session}_SEMANTIC_EVAL"
    
    details = benchmark_data.get("details", [])
    
    # --- Initialisation des compteurs avant le traitement ---
    stats_run = benchmark_data.setdefault("stats_current_run", {})
    global_stats = stats_run.setdefault("global", {})
    global_stats["success_compa"] = 0
    global_stats["failed_compa"] = 0
    global_stats["success_rate_compa"] = 0
    
    for diff in stats_run.setdefault("by_difficulty", {}).keys():
        stats_run["by_difficulty"][diff]["success_compa"] = 0
        stats_run["by_difficulty"][diff]["failed_compa"] = 0
    # --------------------------------------------------------
    
    print(f"🚀 Lancement de l'évaluation ({max_parallel_tasks} tâches simultanées)...")
    print(f"📊 Session Langfuse : {eval_session_id}")
    start_time = time.time()

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_parallel_tasks) as executor:
        futures = [executor.submit(process_single_task, task, eval_session_id, benchmark_data, output_json_path) for task in details]
        concurrent.futures.wait(futures)

    end_time = time.time()
    duration = end_time - start_time
    
    final_success = benchmark_data["stats_current_run"]["global"]["success_compa"]
    final_failed = benchmark_data["stats_current_run"]["global"]["failed_compa"]
    final_rate = benchmark_data["stats_current_run"]["global"]["success_rate_compa"]
    
    print(f"\n🏁 Évaluation terminée en {duration:.2f}s ! Résultats dans {output_json_path}")
    print(f"📊 Bilan Comparatif Final : {final_success} Succès | {final_failed} Échecs ({final_rate}%)")

if __name__ == "__main__":
    INPUT_FILE = "benchmark_report_20260308_1204.json" # Nom du dernier rapport
    OUTPUT_FILE = "benchmark_report_SEMANTIC_EVAL_PARALLEL_2.json"
    
    run_parallel_post_benchmark(INPUT_FILE, OUTPUT_FILE, max_parallel_tasks=10)