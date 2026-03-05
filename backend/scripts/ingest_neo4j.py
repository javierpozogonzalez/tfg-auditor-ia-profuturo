import os
import csv
from datetime import datetime
from dotenv import load_dotenv
from neo4j import GraphDatabase
from langchain_ollama.embeddings import OllamaEmbeddings

load_dotenv()

NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")

DATA_FILE = "data/datos_profuturo.csv"


class Neo4jETLPipeline:
    
    def __init__(self, uri, user, password):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        self.embeddings = OllamaEmbeddings(
            model=EMBEDDING_MODEL,
            base_url=OLLAMA_HOST
        )
    
    def close(self):
        self.driver.close()
    
    def clear_database(self):
        with self.driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")
            print("Base de datos limpiada")
    
    def create_constraints(self):
        with self.driver.session() as session:
            constraints = [
                "CREATE CONSTRAINT post_id IF NOT EXISTS FOR (p:Post) REQUIRE p.id IS UNIQUE",
                "CREATE CONSTRAINT author_name IF NOT EXISTS FOR (a:Author) REQUIRE a.name IS UNIQUE",
                "CREATE CONSTRAINT community_name IF NOT EXISTS FOR (c:Community) REQUIRE c.name IS UNIQUE",
                "CREATE CONSTRAINT discussion_name IF NOT EXISTS FOR (d:Discussion) REQUIRE d.topic IS UNIQUE"
            ]
            for constraint in constraints:
                session.run(constraint)
            print("Constraints creados")
    
    def create_indexes(self):
        with self.driver.session() as session:
            indexes = [
                "CREATE INDEX post_content IF NOT EXISTS FOR (p:Post) ON (p.content)",
                "CREATE INDEX post_sentiment IF NOT EXISTS FOR (p:Post) ON (p.sentiment)",
                "CREATE INDEX post_date IF NOT EXISTS FOR (p:Post) ON (p.date)"
            ]
            for index in indexes:
                session.run(index)
            print("Indices creados")
    
    def parse_date(self, date_str):
        try:
            return datetime.strptime(date_str.strip(), "%Y-%m-%d")
        except:
            return datetime.now()
    
    def create_graph_structure(self, row):
        post_id = str(row["mensaje_id"]).strip()
        author_name = row["autor"].strip()
        community_name = row["comunidad"].strip()
        discussion_topic = row["tema"].strip()
        content = row["contenido"].strip()
        post_date = self.parse_date(row["fecha"])
        sentiment = row["sentimiento"].strip()
        
        if not content:
            return 0
        
        embedding_vector = self.embeddings.embed_query(content)
        
        with self.driver.session() as session:
            session.run("""
                MERGE (p:Post {id: $post_id})
                SET p.content = $content,
                    p.date = $date,
                    p.sentiment = $sentiment,
                    p.embedding = $embedding
                
                MERGE (a:Author {name: $author})
                MERGE (a)-[:WROTE]->(p)
                
                MERGE (d:Discussion {topic: $discussion})
                MERGE (p)-[:IN_DISCUSSION]->(d)
                
                MERGE (c:Community {name: $community})
                MERGE (d)-[:PERTAINS_TO]->(c)
            """,
                post_id=post_id,
                content=content,
                date=post_date,
                sentiment=sentiment,
                embedding=embedding_vector,
                author=author_name,
                discussion=discussion_topic,
                community=community_name
            )
        
        return 1
    
    def ingest_data(self):
        posts_processed = 0
        
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            
            for row in reader:
                result = self.create_graph_structure(row)
                posts_processed += result
                
                if posts_processed % 25 == 0 and posts_processed > 0:
                    print(f"  {posts_processed} posts procesados")
        
        print(f"Ingesta completada: {posts_processed} posts")
        return posts_processed
    
    def verify_ingestion(self):
        with self.driver.session() as session:
            stats = session.run("""
                MATCH (p:Post)
                OPTIONAL MATCH (a:Author)-[:WROTE]->(p)
                OPTIONAL MATCH (p)-[:IN_DISCUSSION]->(d:Discussion)
                OPTIONAL MATCH (d)-[:PERTAINS_TO]->(c:Community)
                RETURN 
                    count(DISTINCT p) as total_posts,
                    count(DISTINCT a) as total_authors,
                    count(DISTINCT d) as total_discussions,
                    count(DISTINCT c) as total_communities
            """).single()
            
            print(f"\nEstadisticas del grafo:")
            print(f"  Posts: {stats['total_posts']}")
            print(f"  Autores: {stats['total_authors']}")
            print(f"  Discusiones: {stats['total_discussions']}")
            print(f"  Comunidades: {stats['total_communities']}")
    
    def run_pipeline(self):
        print("=" * 50)
        print("ProFuturo GraphRAG - ETL Pipeline")
        print("=" * 50)
        print()
        
        print("Paso 1: Limpiar base de datos")
        self.clear_database()
        print()
        
        print("Paso 2: Crear constraints")
        self.create_constraints()
        print()
        
        print("Paso 3: Crear indices")
        self.create_indexes()
        print()
        
        print("Paso 4: Ingestar datos y generar embeddings")
        self.ingest_data()
        print()
        
        print("Paso 5: Verificar ingestion")
        self.verify_ingestion()
        print()
        
        print("=" * 50)
        print("Pipeline completado")
        print("=" * 50)


if __name__ == "__main__":
    pipeline = Neo4jETLPipeline(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
    
    try:
        pipeline.run_pipeline()
    finally:
        pipeline.close()
