import os

DOMAIN = os.environ.get("NEO4J_DOMAIN", "neo4j")
URI = f"neo4j://{DOMAIN}:7687"
AUTH = ("neo4j", "neo4j")
DATABASE = "neo4j"