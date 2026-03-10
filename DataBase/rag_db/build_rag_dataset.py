import csv
import json
import os
import time
import logging
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from utils.helpers import load_schema_doc

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

load_dotenv()

# Chemins de fichiers
CSV_PATH = "variation-B.csv" 
JSON_OUTPUT_PATH = "docs/few_shot_examples-variation-B.json"

class RAGEntry(BaseModel):
    methodology: str = Field(description="Step-by-step graph traversal logic (max 3 sentences) mentioning exact Node labels (e.g., :AS) and Relationship types (e.g., :ORIGINATE).")
    abstract_intent: str = Field(description="Generalized version of the question. Replace specific values like 'Japan' or '2497' with placeholders like 'Country' or 'ASN'.")

def build_rag_dataset():
    schema_doc = load_schema_doc()
    
    llm = ChatGoogleGenerativeAI(model="gemini-2.5-pro", temperature=0.0)
    structured_llm = llm.with_structured_output(RAGEntry)

    rag_examples = []
    processed_intents = set()
    if os.path.exists(JSON_OUTPUT_PATH):
        try:
            with open(JSON_OUTPUT_PATH, 'r', encoding='utf-8') as f:
                rag_examples = json.load(f)
                processed_intents = {ex["intent"] for ex in rag_examples}
            logger.info(f"📂 Reprise : {len(rag_examples)} exemples déjà traités.")
        except Exception:
            logger.warning("⚠️ Impossible de lire le JSON existant, on repart à zéro.")

    if not os.path.exists(CSV_PATH):
        logger.error(f"❌ Erreur : Le fichier {CSV_PATH} est introuvable.")
        return

    logger.info(f"🚀 Début du traitement du fichier {CSV_PATH}...")
    
    with open(CSV_PATH, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        
        for row in reader:
            prompt = str(row.get("Prompt", "")).strip()
            cypher = str(row.get("Canonical Solution", "")).strip()

            if not prompt or not cypher or prompt in processed_intents:
                continue

            logger.info(f"⚙️ Analyse de : {prompt[:60]}...")
            
            # Prompt de Reasoning "Chain-of-Thought"
            system_msg = f"""You are an Expert Graph Database Architect.
Your goal is to explain how a Cypher query solves a specific user question.
You MUST follow the schema provided below.

IYP GRAPH SCHEMA:
{schema_doc}
"""
            user_msg = f"""
USER QUESTION: {prompt}
CANONICAL CYPHER: {cypher}

Explain the graph traversal strategy and provide an abstract version of the intent.
"""

            try:
                # Appel LLM
                result: RAGEntry = structured_llm.invoke([
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": user_msg}
                ])
                
                # Ajout à la liste
                rag_examples.append({
                    "intent": prompt,
                    "abstract_intent": result.abstract_intent,
                    "methodology": result.methodology,
                    "cypher": cypher
                })

                os.makedirs(os.path.dirname(JSON_OUTPUT_PATH), exist_ok=True)
                with open(JSON_OUTPUT_PATH, 'w', encoding='utf-8') as out_f:
                    json.dump(rag_examples, out_f, indent=2, ensure_ascii=False)
                
                time.sleep(0.8)

            except Exception as e:
                logger.error(f"❌ Échec pour '{prompt[:30]}': {e}")
                continue

    logger.info(f"✨ Terminé ! Dataset RAG disponible dans {JSON_OUTPUT_PATH}")

if __name__ == "__main__":
    build_rag_dataset()