# DataBase/db_client.py

import os
import logging
import threading
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)


class DatabaseManager:
    _drivers = {}
    _lock = threading.Lock()

    @classmethod
    def get_driver(cls, db_name: str):
        if db_name in cls._drivers:
            return cls._drivers[db_name]

        with cls._lock:
            if db_name not in cls._drivers:
                cls._drivers[db_name] = cls._initialize_driver(db_name)

        return cls._drivers[db_name]

    @classmethod
    def _initialize_driver(cls, db_name: str):
        uri      = os.getenv(f"{db_name}_URI")
        user     = os.getenv(f"{db_name}_USER")
        password = os.getenv(f"{db_name}_PASSWORD")

        try:
            driver = GraphDatabase.driver(uri, auth=(user, password))
            driver.verify_connectivity()
            logger.info(f"✅ Successfully initialized Neo4j connection pool for: {db_name}")
            return driver
        except Exception as e:
            logger.error(f"❌ Failed to connect to {db_name}: {e}")
            raise

    @classmethod
    def close_all(cls):
        with cls._lock:
            for name, driver in cls._drivers.items():
                driver.close()
                logger.info(f"🔌 Closed Neo4j connection pool for: {name}")
            cls._drivers.clear()