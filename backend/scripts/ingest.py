import os
import csv
from datetime import datetime
from dotenv import load_dotenv
from neo4j import GraphDatabase
from src.llm_config import get_embeddings

load_dotenv()

NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

DATA_FILE = "data/datos_profuturo.csv"

embeddings = get_embeddings()
driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


def create_constraints():
    with driver.session() as session:
        session.run("CREATE CONSTRAINT post_id IF NOT EXISTS FOR (p:Post) REQUIRE p.id IS UNIQUE")
        session.run("CREATE CONSTRAINT author_name IF NOT EXISTS FOR (a:Author) REQUIRE a.name IS UNIQUE")
        session.run("CREATE CONSTRAINT community_name IF NOT EXISTS FOR (c:Community) REQUIRE c.name IS UNIQUE")
        session.run("CREATE CONSTRAINT topic_name IF NOT EXISTS FOR (t:Topic) REQUIRE t.name IS UNIQUE")
    print("Constraints creados")


def clear_database():
    with driver.session() as session:
        session.run("MATCH (n) DETACH DELETE n")
    print("Base de datos limpiada")


def ingest_data():
    posts_created = 0
    
    with driver.session() as session:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            
            for row in reader:
                mensaje_id = str(row.get("mensaje_id", "")).strip()
                author = row.get("autor", "Anónimo").strip()
                community = row.get("comunidad", "general").strip()
                topic = row.get("tema", "general").strip()
                content = row.get("contenido", "").strip()
                date_str = row.get("fecha", "").strip()
                sentiment = row.get("sentimiento", "neutral").strip()
                
                if not content:
                    continue
                
                try:
                    post_date = datetime.strptime(date_str, "%Y-%m-%d")
                except Exception:
                    post_date = datetime.now()
                
                embedding_vector = embeddings.embed_query(content)
                
                session.run("""
                    MERGE (p:Post {id: $post_id})
                    SET p.content = $content,
                        p.date = $date,
                        p.sentiment = $sentiment,
                        p.embedding = $embedding
                """,
                    post_id=mensaje_id,
                    content=content,
                    date=post_date,
                    sentiment=sentiment,
                    embedding=embedding_vector
                )
                
                session.run("""
                    MERGE (a:Author {name: $author})
                    MERGE (p:Post {id: $post_id})
                    MERGE (a)-[:WROTE]->(p)
                """,
                    author=author,
                    post_id=mensaje_id
                )
                
                session.run("""
                    MERGE (c:Community {name: $community})
                    MERGE (p:Post {id: $post_id})
                    MERGE (p)-[:BELONGS_TO]->(c)
                """,
                    community=community,
                    post_id=mensaje_id
                )
                
                session.run("""
                    MERGE (t:Topic {name: $topic})
                    MERGE (p:Post {id: $post_id})
                    MERGE (p)-[:ABOUT]->(t)
                """,
                    topic=topic,
                    post_id=mensaje_id
                )
                
                posts_created += 1
                if posts_created % 50 == 0:
                    print(f"  {posts_created} posts procesados...")
    
    print(f"Ingesta completada: {posts_created} posts")


def create_indexes():
    with driver.session() as session:
        session.run("CREATE INDEX post_content IF NOT EXISTS FOR (p:Post) ON (p.content)")
        session.run("CREATE INDEX post_sentiment IF NOT EXISTS FOR (p:Post) ON (p.sentiment)")
        session.run("CREATE INDEX author_name IF NOT EXISTS FOR (a:Author) ON (a.name)")
        session.run("CREATE INDEX community_name IF NOT EXISTS FOR (c:Community) ON (c.name)")
    print("Índices creados")


if __name__ == "__main__":
    print("=" * 40)
    print("ProFuturo - Data Ingestion")
    print("=" * 40)
    print()
    
    print("1. Limpiar base de datos...")
    clear_database()
    print()
    
    print("2. Crear constraints...")
    create_constraints()
    print()
    
    print("3. Crear índices...")
    create_indexes()
    print()
    
    print("4. Ingestar datos...")
    ingest_data()
    print()
    
    driver.close()
    print("Completado!")

