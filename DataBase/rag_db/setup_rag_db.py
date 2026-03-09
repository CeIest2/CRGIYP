import os
import json
import logging
from dotenv import load_dotenv
from neo4j import GraphDatabase
from langchain_google_genai import GoogleGenerativeAIEmbeddings

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

RAG_URI      = os.getenv("RAG_URI", "bolt://localhost:7688")
RAG_USER     = os.getenv("RAG_USER", "neo4j")
RAG_PASSWORD = os.getenv("RAG_PASSWORD", "password")

embeddings = GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-001")

def setup_rag():
    logger.info(f"🔌 Connexion à la base RAG locale ({RAG_URI})...")
    driver = GraphDatabase.driver(RAG_URI, auth=(RAG_USER, RAG_PASSWORD))

    json_paths = [
        "docs/few_shot_examples.json",
        os.path.join(os.path.dirname(__file__), "..", "..", "docs", "few_shot_examples.json")
    ]
    
    examples = None
    for path in json_paths:
        try:
            with open(path, 'r', encoding='utf-8') as f:
                examples = json.load(f)
                break
        except FileNotFoundError:
            continue
            
    if examples is None:
        logger.error("❌ Fichier JSON introuvable.")
        return

    with driver.session() as session:
        # 1. Nettoyage complet
        session.run("MATCH (n:CypherExample) DETACH DELETE n")
        session.run("DROP INDEX example_intent_embedding IF EXISTS")
        
        # 2. DÉTECTION DYNAMIQUE DES DIMENSIONS
        logger.info("📏 Détection de la dimension du modèle d'embedding...")
        sample_vector = embeddings.embed_query("test dimension")
        vector_dim = len(sample_vector)
        logger.info(f"✅ Le modèle génère des vecteurs de {vector_dim} dimensions.")
        
        # 3. Création de l'index avec la dimension détectée dynamiquement
        logger.info("🏗️ Création de l'index vectoriel sur mesure...")
        session.run(f"""
            CREATE VECTOR INDEX example_intent_embedding IF NOT EXISTS
            FOR (n:CypherExample) ON (n.embedding)
            OPTIONS {{indexConfig: {{
             `vector.dimensions`: {vector_dim},
             `vector.similarity_function`: 'cosine'
            }}}}
        """)

        logger.info(f"🧠 Génération des embeddings pour {len(examples)} exemples...")
        for ex in examples:
            intent = ex.get("intent", "")
            abstract_intent = ex.get("abstract_intent", "")
            methodology = ex.get("methodology", "")
            cypher = ex.get("cypher", "")
            
            text_to_embed = f"Abstract Intent: {abstract_intent}\nGraph Strategy: {methodology}"
            vector = embeddings.embed_query(text_to_embed)
            
            session.run("""
                CREATE (n:CypherExample {
                    intent: $intent,
                    abstract_intent: $abstract_intent,
                    methodology: $methodology,
                    cypher: $cypher,
                    embedding: $embedding
                })
            """, 
            intent=intent, abstract_intent=abstract_intent, 
            methodology=methodology, cypher=cypher, embedding=vector)
            
        logger.info("✅ Base RAG locale initialisée avec succès !")

    driver.close()

if __name__ == "__main__":
    setup_rag()