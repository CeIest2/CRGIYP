import csv
import json
import time
import uuid
import os
import threading
import concurrent.futures
import logging
from datetime import datetime
from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field

from agents.orchestrator import run_autonomous_loop

# Configuration du logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

file_lock = threading.Lock()

# --- Modèles de données ---

class TestDetail(BaseModel):
    """Détails complets d'un test individuel."""
    test_index: int
    task_id: str
    difficulty: str
    prompt: str
    status: str
    failure_reason: Optional[str] = None
    iterations_used: int
    time_seconds: float
    generated_cypher: str
    canonical_cypher: str

class DifficultyStats(BaseModel):
    """Statistiques par niveau de difficulté."""
    total: int = 0
    success: int = 0
    failed: int = 0

class GlobalStats(BaseModel):
    """Statistiques globales du benchmark."""
    total: int = 0
    success: int = 0
    failed: int = 0

class BenchmarkReport(BaseModel):
    """Structure complète du rapport de benchmark."""
    session_id: str
    last_updated: str
    stats_current_run: Dict[str, Any] = {"global": GlobalStats(), "by_difficulty": {}}
    details: List[TestDetail] = []


def process_single_test(index: int, row: Dict[str, str], report: BenchmarkReport, report_filename: str,use_rag: bool = False):
    """Exécute un test unique et met à jour le rapport partagé."""
    task_id          = row.get('Task ID', 'N/A')
    difficulty       = row.get('Difficulty Level', 'Unknown')
    prompt           = row.get('Prompt', '')
    canonical_cypher = row.get('Canonical Solution', 'None')
    
    logger.info(f"⏳ Starting TEST {index + 1} | Task: {task_id} | Diff: {difficulty}")
    
    start_time = time.time()
    failure_reason = None
    
    try:
        agent_result = run_autonomous_loop(prompt, session_id=report.session_id, use_rag=use_rag)
        status       = agent_result.get("status", "FAILED")
        iterations   = agent_result.get("iterations", 0)
        final_cypher = agent_result.get("cypher", "None")
        
        if status == "FAILED":
            failure_reason = agent_result.get("reason") or f"Max retries reached ({iterations} attempts)"
            
    except Exception as e:
        status       = "FAILED"
        iterations   = 0
        final_cypher = "None"
        failure_reason = f"System Crash: {str(e)}"
        
    elapsed_time = round(time.time() - start_time, 2)
    
    detail = TestDetail(
        test_index=index + 1,
        task_id=task_id,
        difficulty=difficulty,
        prompt=prompt,
        status=status,
        failure_reason=failure_reason,
        iterations_used=iterations,
        time_seconds=elapsed_time,
        generated_cypher=final_cypher,
        canonical_cypher=canonical_cypher
    )

    with file_lock:
        if difficulty not in report.stats_current_run["by_difficulty"]:
            report.stats_current_run["by_difficulty"][difficulty] = DifficultyStats()

        report.stats_current_run["global"].total += 1
        report.stats_current_run["by_difficulty"][difficulty].total += 1
        
        if status == "SUCCESS":
            report.stats_current_run["global"].success += 1
            report.stats_current_run["by_difficulty"][difficulty].success += 1
            logger.info(f"✅ [Test {index + 1}] SUCCESS in {iterations} iterations ({elapsed_time}s)")
        else:
            report.stats_current_run["global"].failed += 1
            report.stats_current_run["by_difficulty"][difficulty].failed += 1
            logger.warning(f"❌ [Test {index + 1}] FAILED ({elapsed_time}s) -> Reason: {failure_reason}")
        
        report.details.append(detail)
        report.last_updated = datetime.now().isoformat()
        
        with open(report_filename, "w", encoding="utf-8") as f:
            f.write(report.model_dump_json(indent=4))
        
        # Affichage du score en temps réel
        g = report.stats_current_run["global"]
        rate = (g.success / g.total) * 100
        logger.info(f"📈 CURRENT SCORE: {g.success}/{g.total} ({rate:.2f}%)")


def run_cyphereval_benchmark(csv_file_path: str, limit: int = None, start_at: int = 0, max_workers: int = 5, use_rag: bool = False):
    """Point d'entrée principal pour lancer le benchmark en parallèle."""
    
    date_str = datetime.now().strftime("%Y%m%d_%H%M")
    report_filename = f"benchmark_report_{date_str}.json"
    
    # Initialisation du rapport via Pydantic
    report = BenchmarkReport(
        session_id=f"benchmark_{date_str}_{uuid.uuid4().hex[:4]}",
        last_updated=datetime.now().isoformat()
    )
    
    logger.info(f"🚀 Starting PARALLEL benchmark (x{max_workers} threads) on {csv_file_path}")
    
    tasks_to_run = []
    try:
        with open(csv_file_path, mode='r', encoding='utf-8') as file:
            reader = list(csv.DictReader(file))
            for index, row in enumerate(reader):
                if index < start_at:
                    continue
                if limit and len(tasks_to_run) >= limit:
                    break
                tasks_to_run.append((index, row))
    except FileNotFoundError:
        logger.error(f"CSV file not found: {csv_file_path}")
        return

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(process_single_test, index, row, report, report_filename, use_rag=use_rag)
            for index, row in tasks_to_run
        ]
        concurrent.futures.wait(futures)

    # Résumé final
    print("\n" + "*"*50)
    print("🏆 FINAL BENCHMARK RESULTS 🏆")
    print("*"*50)
    
    g = report.stats_current_run["global"]
    if g.total > 0:
        global_rate = (g.success / g.total) * 100
        print(f"🌍 Global Success Rate: {global_rate:.2f}% ({g.success}/{g.total})")
        
        print("\n📊 Detail by difficulty:")
        for diff, stats in report.stats_current_run["by_difficulty"].items():
            rate = (stats.success / stats.total) * 100
            print(f"  - {diff} : {rate:.2f}% ({stats.success}/{stats.total})")
    else:
        print("No tests were executed.")

    final_output = "benchmark_report_final.json"
    with open(final_output, "w", encoding="utf-8") as f:
        f.write(report.model_dump_json(indent=4))
        
    logger.info(f"📝 Final report saved in '{final_output}'")

if __name__ == "__main__":
    run_cyphereval_benchmark("variation-B.csv", limit=None, start_at=0, max_workers=12, use_rag=True)