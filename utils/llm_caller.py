import os
import logging
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv

from langfuse import Langfuse
from langfuse.langchain import CallbackHandler
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

load_dotenv()
langfuse_client = Langfuse()
logger = logging.getLogger(__name__)

def _fetch_prompt_template(prompt_name: str) -> ChatPromptTemplate:
    try:
        langfuse_prompt = langfuse_client.get_prompt(prompt_name)
        prompt_messages = langfuse_prompt.get_langchain_prompt()
        return ChatPromptTemplate.from_messages(prompt_messages)
    except Exception as e:
        logger.error(f"Erreur lors de la récupération du prompt '{prompt_name}': {e}")
        raise

def _initialize_llm(model_name: str, temperature: float, response_format: str = "text") -> ChatGoogleGenerativeAI:
    # Correction de l'avertissement : on passe response_mime_type au constructeur
    response_mime_type = "application/json" if response_format.lower() == "json" else "text/plain"
    return ChatGoogleGenerativeAI(
        model=model_name, 
        temperature=temperature, 
        google_api_key=os.getenv("GOOGLE_API_KEY"),
        response_mime_type=response_mime_type
    )
def _build_tracking_config(session_id: str, trace_name: str, tags: list, trace_id: str = None) -> dict:
    metadata = {
        "langfuse_session_id": session_id,
        "langfuse_trace_name": trace_name,
        "langfuse_tags": tags,
    }
    if trace_id:
        metadata["langfuse_trace_id"] = trace_id # LA CLÉ MAGIQUE
    
    return {
        "callbacks": [CallbackHandler()],
        "metadata": metadata
    }

def call_llm_with_tracking(
    prompt_name: str, 
    variables: Dict[str, Any], 
    session_id: str, 
    trace_name: str = "llm_call", 
    tags: List[str] = [], 
    model_name: str = "gemini-2.5-flash", 
    temperature: float = 0.0, 
    response_format: str = "text",
    trace_id: str = None # Paramètre ajouté
) -> Dict[str, Any]:
    try:
        prompt_template = _fetch_prompt_template(prompt_name)
        llm             = _initialize_llm(model_name, temperature, response_format) 
        tracking_config = _build_tracking_config(session_id, trace_name, tags, trace_id=trace_id)
        chain           = prompt_template | llm | StrOutputParser()

    except Exception as e:
        logger.error(f"Erreur d'initialisation LLM: {e}")
        return {"success": False, "content": None, "error_message": str(e)}
    
    try:
        logger.info(f"Appel LLM pour '{trace_name}'...")
        response_text = chain.invoke(variables, config=tracking_config)
        return {"success": True, "content": response_text.strip(), "error_message": None}
    except Exception as e:
        logger.error(f"Échec de l'exécution LLM: {e}")
        return {"success": False, "content": None, "error_message": str(e)}
if __name__ == "__main__":
    import os
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    
    schema_path = "docs/IYP_doc.md" 
    
    try:
        with open(schema_path, "r", encoding="utf-8") as f:
            real_schema_doc = f.read()
    except FileNotFoundError:
        print(f"❌ Erreur : Le fichier {schema_path} est introuvable. Avez-vous mis le bon chemin ?")
        exit(1) 
    
    test_variables = {
        "schema_doc": real_schema_doc,
        "question": "Quelle est la part de marché (population servie) de l'AS 3215 en France ?"
    }
    
    result = call_llm_with_tracking(
        prompt_name="iyp-cypher-generator",
        variables=test_variables,
        session_id="test_reel_llm_001",
        trace_name="test_direct_call_reel",
        tags=["test_reel", "llm_module"]
    )
    
    print("\n" + "="*40)
    print("RÉSULTAT DU TEST RÉEL")
    print("="*40)
    
    if result["success"]:
        print("✅ SUCCÈS ! Réponse générée :")
        print("-" * 40)
        print(result["content"])
        print("-" * 40)
    else:
        print("❌ ÉCHEC !")
        print(f"Erreur rencontrée : {result['error_message']}")