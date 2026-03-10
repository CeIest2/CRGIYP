import os
import json
import langfuse
from neo4j import GraphDatabase
from neo4j.exceptions import Neo4jError
from dotenv import load_dotenv

load_dotenv()

IYP_URI      = os.getenv("IYP_URI")
IYP_USER     = os.getenv("IYP_USER")
IYP_PASSWORD = os.getenv("IYP_PASSWORD")


@langfuse.observe(as_type="span", name="Neo4j_Execution")
def test_cypher_on_iyp_traced(cypher):
    return test_cypher_on_iyp(cypher)

def test_cypher_on_iyp(query: str, parameters: dict = None) -> dict:

    auth = (IYP_USER, IYP_PASSWORD) if IYP_USER and IYP_PASSWORD else None
    
    try:
        with GraphDatabase.driver(IYP_URI, auth=auth) as driver:
            driver.verify_connectivity()
            
            records, summary, keys = driver.execute_query(query,parameters_=parameters,routing_="r", database_="neo4j", transaction_config={"timeout": 120.0} )
            
            return {"success": True, "keys": keys, "data": [record.data() for record in records], "metadata": { "query_type": summary.query_type, "time_ms": summary.result_available_after}}
            
    except Neo4jError as e:
        return {"success": False, "error_type": "Neo4jError","message": e.message, "code": e.code}
    except Exception as e:
        print(f"\n⚠️ ERREUR PYTHON DANS NEO4J CONNECTOR : {e}\n")
        return {"success": False, "error_type": "SystemError", "message": str(e)}






if __name__ == "__main__":

    test_query = "RETURN 'Connexion à IYP réussie !' AS message"
    print(f"--- Exécution de la requête sur {IYP_URI} ---")    
    result = test_cypher_on_iyp(test_query)
    
    if result["success"]:
        print("✅ Succès ! Résultats :")
        print(json.dumps(result["data"], indent=2, ensure_ascii=False))
        print(f"\n⏱️ Temps d'exécution : {result['metadata']['time_ms']} ms")
    else:
        print(f"❌ Échec de la requête :")
        print(f"[{result['error_type']}] {result['message']}")