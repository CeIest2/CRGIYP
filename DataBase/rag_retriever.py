import os
import logging
from typing import List, Dict, Any
from dotenv import load_dotenv
from neo4j import GraphDatabase
from langchain_google_genai import GoogleGenerativeAIEmbeddings

# 1. Import de Langfuse v3
from langfuse import Langfuse

load_dotenv()
logger = logging.getLogger(__name__)

# 2. Initialisation du client Langfuse
langfuse = Langfuse()

RAG_URI      = os.getenv("RAG_URI", "bolt://localhost:7688")
RAG_USER     = os.getenv("RAG_USER", "neo4j")
RAG_PASSWORD = os.getenv("RAG_PASSWORD", "password")

embeddings = GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-001")

def get_relevant_examples(search_intent: str, top_k: int = 3) -> List[Dict[str, Any]]:
    """
    Interroge la base vectorielle Neo4j pour ramener les top_k exemples Cypher les plus pertinents.
    """
    logger.info(f"🔍 Recherche RAG pour l'intention : '{search_intent[:50]}...'")
    
    try:
        # Traçage de l'Embedding
        with langfuse.start_as_current_observation(
            name="Gemini_Embedding",
            as_type="generation",
            model="gemini-embedding-001", 
            input=search_intent
        ) as emb_gen:
            
            query_vector = embeddings.embed_query(search_intent)
            
            estimated_tokens = len(search_intent) // 4
            if estimated_tokens == 0: estimated_tokens = 1
            
            emb_gen.update(
                output={"vector_dimension": len(query_vector)},
                usage={
                    "input": estimated_tokens
                }
            )
            
    except Exception as e:
        logger.error(f"❌ Erreur lors de l'embedding de la requête RAG : {e}")
        return []

    cypher_query = """
    CALL db.index.vector.queryNodes('example_intent_embedding', $top_k, $query_vector) 
    YIELD node, score
    RETURN 
        node.intent AS original_question,
        node.abstract_intent AS abstract_intent,
        node.methodology AS methodology,
        node.cypher AS cypher,
        score
    """
    
    results = []
    try:
        with langfuse.start_as_current_observation(
            name="Neo4j_Vector_Search",
            as_type="span",
            input={"top_k": top_k}
        ) as db_span:
            
            with GraphDatabase.driver(RAG_URI, auth=(RAG_USER, RAG_PASSWORD)) as driver:
                records, _, _ = driver.execute_query(
                    cypher_query,
                    query_vector=query_vector,
                    top_k=top_k,
                    database_="neo4j"
                )
                
                for record in records:
                    results.append({
                        "original_question": record["original_question"],
                        "abstract_intent": record["abstract_intent"],
                        "methodology": record["methodology"],
                        "cypher": record["cypher"],
                        "score": record["score"]
                    })
            
            db_span.update(output={"retrieved_count": len(results)})
                
        logger.info(f"✅ RAG : {len(results)} exemples récupérés.")
        return results

    except Exception as e:
        logger.error(f"❌ Erreur lors de l'interrogation de la base RAG : {e}")
        return []

def format_rag_context(examples: List[Dict[str, Any]]) -> str:
    """
    Formate la liste d'exemples en un texte clair à injecter dans le prompt du LLM.
    """
    if not examples:
        return "No relevant examples found."
    
    formatted_text = "Here are some validated examples of similar graph traversals:\n\n"
    for i, ex in enumerate(examples, 1):
        formatted_text += f"--- Example {i} (Similarity: {ex['score']:.2f}) ---\n"
        formatted_text += f"User Intent: {ex['abstract_intent']}\n"
        formatted_text += f"Graph Strategy: {ex['methodology']}\n"
        formatted_text += f"Valid Cypher: {ex['cypher']}\n\n"
        
    return formatted_text

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    
    test_intent = "Find AS nodes that have a POPULATION relationship to calculate the share in Country JP."
    
    found_examples = get_relevant_examples(test_intent, top_k=2)
    formatted_context = format_rag_context(found_examples)
    
    print("\n" + "="*50)
    print("CONTEXTE RAG GÉNÉRÉ POUR LE LLM :")
    print("="*50)
    print(formatted_context)