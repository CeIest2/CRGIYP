import os
import json
import logging
from typing import Any

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

def truncate_deep_lists(data, max_items=50):
    """Coupe récursivement toutes les listes à `max_items` éléments maximum."""
    if isinstance(data, list):
        if len(data) > max_items:
            truncated = [truncate_deep_lists(item, max_items) for item in data[:max_items]]
            truncated.append(f"... [TRONQUÉ : contient {len(data)} éléments au total]")
            return truncated
        else:
            return [truncate_deep_lists(item, max_items) for item in data]
    
    elif isinstance(data, dict): 
        return {key: truncate_deep_lists(value, max_items) for key, value in data.items()}
    else: 
        return data

def format_db_output(data: Any, max_items: int = 50, max_length: int = 5000) -> str:
    """
    Formate la donnée en JSON, en limitant la profondeur des listes et 
    en coupant la chaîne finale à `max_length` caractères.
    """
    if data is None:
        return "No data returned (None)."
    
    truncated_data = truncate_deep_lists(data, max_items=max_items)
    
    if isinstance(truncated_data, (dict, list)):
        try:
            output_str = json.dumps(truncated_data, indent=2, ensure_ascii=False)
        except Exception:
            output_str = str(truncated_data)
    else:
        output_str = str(truncated_data)
        
    if len(output_str) > max_length:
        return output_str[:max_length] + f"\n\n... [TRONQUÉ DE SÉCURITÉ : La réponse dépassait {max_length} caractères]"
    
    return output_str

def save_json_debug(data: dict, filename: str):
    debug_dir = os.path.join(get_project_root(), "debug")
    os.makedirs(debug_dir, exist_ok=True)
    
    path = os.path.join(debug_dir, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    logger.info(f"Trace de débogage sauvegardée dans {path}")