import csv
from datetime import datetime
import json
import time
import uuid
import os # Nouvel import pour gérer les fichiers
from agents.orchestrator import run_autonomous_loop

def run_cyphereval_benchmark(csv_file_path: str, limit: int = None, start_at: int = 40):
    results = {
        "global": {"total": 0, "success": 0, "failed": 0},
        "by_difficulty": {}
    }
    
    detailed_logs = []
    # Nom de fichier unique pour ce run spécifique
    date_str = datetime.now().strftime("%Y%m%d_%H%M")
    report_filename = f"benchmark_report_{date_str}.json"
    
    benchmark_session_id = f"benchmark_cyphereval_{date_str}_{uuid.uuid4().hex[:4]}"
    print(f"🚀 Démarrage du benchmark sur {csv_file_path}...")
    print(f"📝 Les résultats seront sauvegardés en temps réel dans : {report_filename}")
    
    with open(csv_file_path, mode='r', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        
        for index, row in enumerate(reader):
            if index < start_at:
                continue
            if limit and index >= limit:
                break
                
            task_id          = row['Task ID']
            difficulty       = row['Difficulty Level']
            prompt           = row['Prompt']
            canonical_cypher = row['Canonical Solution']
            
            if difficulty not in results["by_difficulty"]:
                results["by_difficulty"][difficulty] = {"total": 0, "success": 0, "failed": 0}
                
            print(f"\n==================================================")
            print(f"🧪 TEST {index + 1} | Task: {task_id} | Diff: {difficulty}")
            print(f"❓ Question: {prompt}")
            print(f"==================================================")
            
            start_time = time.time()
            try:
                agent_result = run_autonomous_loop(prompt, session_id=benchmark_session_id)
                status       = agent_result.get("status", "FAILED")
                iterations   = agent_result.get("iterations", 0)
                final_cypher = agent_result.get("cypher", "None")
                
            except Exception as e:
                print(f"💥 Erreur critique du système sur cette question : {e}")
                status       = "FAILED"
                iterations   = 0
                final_cypher = str(e)
                
            elapsed_time = time.time() - start_time
            
            results["global"]["total"] += 1
            results["by_difficulty"][difficulty]["total"] += 1
            
            if status == "SUCCESS":
                results["global"]["success"] += 1
                results["by_difficulty"][difficulty]["success"] += 1
                print(f"✅ SUCCÈS en {iterations} itérations internes ({elapsed_time:.2f}s)")
            else:
                results["global"]["failed"] += 1
                results["by_difficulty"][difficulty]["failed"] += 1
                print(f"❌ ÉCHEC ({elapsed_time:.2f}s)")
            
            current_success = results["global"]["success"]
            current_total = results["global"]["total"]
            current_rate = (current_success / current_total) * 100
            print(f"📈 SCORE ACTUEL : {current_success}/{current_total} ({current_rate:.2f}%)")
            
            # --- SAUVEGARDE INCRÉMENTALE ---
            detailed_logs.append({
                "task_id": task_id,
                "difficulty": difficulty,
                "prompt": prompt,
                "status": status,
                "iterations_used": iterations,
                "time_seconds": round(elapsed_time, 2),
                "generated_cypher": final_cypher,
                "canonical_cypher": canonical_cypher
            })
            
            # On réécrit le fichier JSON à chaque étape
            with open(report_filename, "w", encoding="utf-8") as f:
                json.dump({
                    "session_id": benchmark_session_id,
                    "last_updated": datetime.now().isoformat(),
                    "stats_current_run": results,
                    "details": detailed_logs
                }, f, indent=4, ensure_ascii=False)
            


    # --- RÉSUMÉ FINAL ---
    print("\n" + "*"*50)
    print("🏆 RÉSULTATS DU BENCHMARK (FINI) 🏆")
    print("*"*50)
    
    global_rate = (results["global"]["success"] / results["global"]["total"]) * 100
    print(f"🌍 Taux de succès GLOBAL : {global_rate:.2f}% ({results['global']['success']}/{results['global']['total']})")
    
    print("\n📊 Détail par difficulté :")
    for diff, stats in results["by_difficulty"].items():
        if stats["total"] > 0:
            rate = (stats["success"] / stats["total"]) * 100
            print(f"  - {diff} : {rate:.2f}% ({stats['success']}/{stats['total']})")

    with open("benchmark_report.json", "w", encoding="utf-8") as f:
        json.dump(detailed_logs, f, indent=4)
        
    print("\n📝 Un rapport détaillé a été sauvegardé dans 'benchmark_report.json'")

if __name__ == "__main__":

    run_cyphereval_benchmark("variation-A.csv", limit=None,start_at=0)