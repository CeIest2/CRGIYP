import os
import json
import logging
import re
from typing import Any

from CRGIYP.agents.json_corrector import fix_malformed_json
logger = logging.getLogger(__name__)

def get_project_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

def load_schema_doc(filename: str = "IYP_doc.md") -> str:
    path = os.path.join(get_project_root(), "docs", filename)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        logger.error(f"Fichier de documentation introuvable : {path}")
        raise
    except Exception as e:
        logger.error(f"Erreur lors du chargement de {filename} : {e}")
        raise

def format_db_output(data: Any) -> str:
    if data is None:
        return "No data returned (None)."
    
    if isinstance(data, (dict, list)):
        try:
            return json.dumps(data, indent=2, ensure_ascii=False)
        except Exception:
            return str(data)
    
    return str(data)

def save_json_debug(data: dict, filename: str):
    debug_dir = os.path.join(get_project_root(), "debug")
    os.makedirs(debug_dir, exist_ok=True)
    
    path = os.path.join(debug_dir, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    logger.info(f"Trace de débogage sauvegardée dans {path}")



def parse_llm_json(response_text: str, session_id: str = "default_session", trace_id: str = None) -> dict:
    cleaned_text = response_text.strip()
    cleaned_text = re.sub(r'^```json\s*', '', cleaned_text, flags=re.MULTILINE)
    cleaned_text = re.sub(r'```$', '', cleaned_text, flags=re.MULTILINE)
    
    try:
        start_idx = cleaned_text.find('{')
        end_idx = cleaned_text.rfind('}')
        
        if start_idx == -1 or end_idx == -1:
            raise ValueError("Aucune accolade trouvée dans la réponse.")
            
        json_str = cleaned_text[start_idx:end_idx + 1]
        json_str = re.sub(r'[\x00-\x1F\x7F]', '', json_str)
        
        return json.loads(json_str)
        
    except json.JSONDecodeError as e:
        try:
            repaired_json = json_str.replace('\n', '\\n').replace('\r', '\\r')
            return json.loads(repaired_json)
        except Exception:
            logger.warning(f"⚠️ Échec du parsing basique. Appel de l'agent correcteur LLM...")
            
            correction_result = fix_malformed_json(json_str, session_id=session_id, trace_id=trace_id)
            
            if correction_result["success"]:
                try:
                    return json.loads(correction_result["fixed_json_string"])
                except json.JSONDecodeError as final_error:
                    logger.error(f"❌ L'agent a échoué à produire un JSON valide. Sortie: {correction_result['fixed_json_string']}")
                    raise ValueError(f"JSON toujours invalide après correction par le LLM : {final_error}")
            else:
                logger.error(f"❌ Erreur critique lors de l'appel à l'agent correcteur: {correction_result.get('error_message')}")
                raise ValueError(f"JSON invalide et échec de l'agent correcteur : {e}")