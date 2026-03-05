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

def _initialize_llm(model_name: str, temperature: float) -> ChatGoogleGenerativeAI:
    try:
        return ChatGoogleGenerativeAI(model=model_name, temperature=temperature, google_api_key=os.getenv("GOOGLE_API_KEY"))
    
    except Exception as e:
        logger.error(f"Erreur lors de l'initialisation du LLM {model_name}: {e}")
        raise

def _build_tracking_config(session_id: str, trace_name: str, tags: List[str]) -> Dict[str, Any]:
    langfuse_handler = CallbackHandler()
    
    return {"callbacks": [langfuse_handler],"metadata": {"langfuse_session_id": session_id,"langfuse_trace_name": trace_name,"langfuse_tags": tags}}



def call_llm_with_tracking(prompt_name: str, variables: Dict[str, Any], session_id: str, trace_name: str = "llm_call", tags: List[str] = [], model_name: str = "gemini-2.5-flash-lite", temperature: float = 0.0, max_retries: int = 2) -> Dict[str, Any]:

    try:
        prompt_template = _fetch_prompt_template(prompt_name)
        llm             = _initialize_llm(model_name, temperature)
        tracking_config = _build_tracking_config(session_id, trace_name, tags)
        chain           = prompt_template | llm | StrOutputParser()
        
    except Exception as e:
        return {"success": False,"content": None,"error_message": f"Erreur d'initialisation: {str(e)}"}
    
    try:
        logger.info(f"Appel LLM pour '{trace_name}'...")
        response_text = chain.invoke(variables, config=tracking_config)
        return {"success": True,"content": response_text.strip(),"error_message": None}
    
    except Exception as e:
        logger.error(f"Échec de l'exécution LLM: {e}")
        return {"success": False, "content": None, "error_message": str(e)}
    

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    
    print("\n🚀 Lancement du test unitaire de la fonction LLM...\n")
    
    test_variables = {
        "schema_doc": "(Simulation du document Markdown de référence IYP)",
        "question": "Combien y a t'il d'ASN en France ?"
    }
    
    result = call_llm_with_tracking(
        prompt_name="iyp-cypher-generator",
        variables=test_variables,
        session_id="test_unitaire_llm_001",
        trace_name="test_direct_call",
        tags=["test_unitaire", "llm_module"]
    )
    
    print("\n" + "="*40)
    print("RÉSULTAT DU TEST")
    print("="*40)
    
    if result["success"]:
        print("✅ SUCCÈS ! Réponse générée :")
        print("-" * 40)
        print(result["content"])
        print("-" * 40)
    else:
        print("❌ ÉCHEC !")
        print(f"Erreur rencontrée : {result['error_message']}")
        
    print("\n💡 Astuce : Allez vérifier sur Langfuse, vous devriez voir la trace 'test_direct_call' !")