import os
from dotenv import load_dotenv

from langfuse import Langfuse
from langfuse.langchain import CallbackHandler

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

load_dotenv()

langfuse_client = Langfuse()

def load_documentation(filepath=os.path.join("docs", "IYP_doc.md")) -> str:
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()

def generate_cypher_query(user_question: str) -> str:

    print("⏳ Initialisation de l'agent...")
    
    langfuse_handler = CallbackHandler()
    
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash-lite", 
        temperature=0.0, 
        google_api_key=os.getenv("GOOGLE_API_KEY")
    )
    
    langfuse_prompt = langfuse_client.get_prompt("iyp-cypher-generator")
    
    prompt_messages = langfuse_prompt.get_langchain_prompt()
    
    prompt_template = ChatPromptTemplate.from_messages(prompt_messages)
    
    schema_doc = load_documentation()
    
    chain = prompt_template | llm | StrOutputParser()
    print(f"🧠 Réflexion en cours pour la question : '{user_question}'...")
    
    response = chain.invoke(
        {"schema_doc": schema_doc, "question": user_question},
        config={
            "callbacks": [langfuse_handler],
            "metadata": {
                "langfuse_session_id": "test_prompt_management",
                "langfuse_tags": ["poc", "prompt_from_ui"]
            }
        }
    )
    
    return response

if __name__ == "__main__":
    test_question = "Combien y a t'il d'ASN en France ?"
    
    cypher_result = generate_cypher_query(test_question)
    
    print("\n✅ RÉPONSE DE L'AGENT :")
    print(cypher_result)