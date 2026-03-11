import os
import logging
import threading
from typing import Dict, Any, List, Optional, Type
from dotenv import load_dotenv
from pydantic import BaseModel
from utils.local_prompts import LOCAL_FALLBACK_PROMPTS

from langfuse import Langfuse
from langfuse.langchain import CallbackHandler
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

load_dotenv()
langfuse_client = Langfuse()
logger = logging.getLogger(__name__)

# FIX: lru_cache n'est pas thread-safe en écriture.
# Avec 12 workers en parallèle, plusieurs threads pouvaient déclencher
# un cache miss simultané sur le même prompt → N appels Langfuse concurrents
# → race condition sur l'insertion dans le cache.
# On remplace lru_cache par un dict protégé par un RLock.
_prompt_cache: Dict[str, ChatPromptTemplate] = {}
_prompt_cache_lock = threading.RLock()


def _fetch_prompt_template(prompt_name: str) -> ChatPromptTemplate:
    # Lecture sans lock (fast path — cas le plus fréquent)
    if prompt_name in _prompt_cache:
        return _prompt_cache[prompt_name]

    # Écriture protégée par lock
    with _prompt_cache_lock:
        # Double-check : un autre thread a peut-être déjà inséré pendant qu'on attendait
        if prompt_name in _prompt_cache:
            return _prompt_cache[prompt_name]

        try:
            logger.info(f"📥 Fetching prompt '{prompt_name}' from Langfuse (Cache MISS)...")
            langfuse_prompt = langfuse_client.get_prompt(prompt_name)
            prompt_messages = langfuse_prompt.get_langchain_prompt()
            template = ChatPromptTemplate.from_messages(prompt_messages)
            logger.debug(f"✅ Successfully loaded '{prompt_name}' from Langfuse.")

        except Exception as e:
            logger.warning(f"⚠️ Langfuse unreachable or prompt missing: {e}.")
            logger.warning(f"🛡️ Switching to LOCAL FALLBACK for '{prompt_name}'...")

            if prompt_name not in LOCAL_FALLBACK_PROMPTS:
                logger.error(f"❌ CRITICAL: No local fallback found for '{prompt_name}'!")
                raise

            template = ChatPromptTemplate.from_messages(LOCAL_FALLBACK_PROMPTS[prompt_name])

        _prompt_cache[prompt_name] = template
        return template


def _build_tracking_config(
    session_id: str,
    trace_name: str,
    tags: list,
    trace_id: str = None,
) -> dict:
    metadata = {
        "langfuse_session_id": session_id,
        "langfuse_trace_name": trace_name,
        "langfuse_tags": tags,
    }
    if trace_id:
        metadata["langfuse_trace_id"] = trace_id
    return {
        "callbacks": [CallbackHandler()],
        "metadata": metadata,
        "run_name": trace_name,
    }


def call_llm_with_tracking(
    prompt_name: str,
    variables: Dict[str, Any],
    session_id: str,
    trace_name: str = "llm_call",
    tags: List[str] = [],
    model_name: str = "gemini-2.5-flash-lite",
    temperature: float = 0.0,
    trace_id: str = None,
    pydantic_schema: Optional[Type[BaseModel]] = None,
    thinking_budget: Optional[int] = None,
) -> Dict[str, Any]:

    try:
        prompt_template = _fetch_prompt_template(prompt_name)

        llm_kwargs = {
            "model": model_name,
            "temperature": temperature,
            "google_api_key": os.getenv("GOOGLE_API_KEY"),
            "max_output_tokens": 4096,
        }
        if thinking_budget is not None:
            llm_kwargs["thinking_budget"] = thinking_budget

        llm = ChatGoogleGenerativeAI(**llm_kwargs)
        tracking_config = _build_tracking_config(session_id, trace_name, tags, trace_id=trace_id)

        if pydantic_schema:
            chain = prompt_template | llm.with_structured_output(pydantic_schema)
        else:
            chain = prompt_template | llm | StrOutputParser()

    except Exception as e:
        logger.error(f"Erreur d'initialisation LLM: {e}")
        return {"success": False, "content": None, "error_message": str(e)}

    try:
        logger.info(f"Appel LLM pour '{trace_name}'...")
        response_content = chain.invoke(variables, config=tracking_config)
        return {"success": True, "content": response_content, "error_message": None}

    except Exception as e:
        logger.error(f"Échec de l'exécution LLM: {e}")
        return {"success": False, "content": None, "error_message": str(e)}