import os
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

def get_project_root() -> str:
    """ Retourne le chemin absolu vers la racine du projet. """
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

def load_schema_doc(filename: str = "IYP_doc.md") -> str:
    """
    Charge le contenu du fichier de documentation du schéma IYP.
    Utilise le chemin relatif à la racine du projet.
    """
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
    """
    Formate la sortie de la base de données pour qu'elle soit lisible par le LLM.
    Gère les dictionnaires, les listes et les erreurs.
    """
    if data is None:
        return "No data returned (None)."
    
    if isinstance(data, (dict, list)):
        try:
            # On utilise indent=2 pour la lisibilité du LLM
            return json.dumps(data, indent=2, ensure_ascii=False)
        except Exception:
            return str(data)
    
    return str(data)

def save_json_debug(data: dict, filename: str):
    """ Utilitaire pour sauvegarder des traces JSON localement si besoin de débogage. """
    debug_dir = os.path.join(get_project_root(), "debug")
    os.makedirs(debug_dir, exist_ok=True)
    
    path = os.path.join(debug_dir, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    logger.info(f"Trace de débogage sauvegardée dans {path}")