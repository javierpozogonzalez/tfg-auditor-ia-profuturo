from typing import Dict, List, Any
from neo4j import GraphDatabase


class Neo4jGraphClient:
    def __init__(self, uri: str, user: str, password: str):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        self.driver.close()

    def execute_query(self, query: str, parameters: Dict[str, Any] = None) -> List[Dict]:
        with self.driver.session() as session:
            result = session.run(query, parameters or {})
            return [record.data() for record in result]

    def get_messages_by_community(self, community: str, limit: int = 20) -> List[Dict]:
        query = """
        MATCH (m:Mensaje)-[:PERTENECE_A]->(c:Comunidad {nombre: $community})
        OPTIONAL MATCH (a:Autor)-[:ESCRIBIO]->(m)
        RETURN m.contenido as content, a.nombre as author, m.sentimiento as sentiment
        ORDER BY m.fecha DESC
        LIMIT $limit
        """
        return self.execute_query(query, {"community": community, "limit": limit})

    def search_by_topic(self, topic: str, limit: int = 10) -> List[Dict]:
        query = """
        MATCH (m:Mensaje)-[:SOBRE]->(t:Tema {nombre: $topic})
        OPTIONAL MATCH (a:Autor)-[:ESCRIBIO]->(m)
        RETURN m.contenido as content, a.nombre as author, m.fecha as date
        ORDER BY m.fecha DESC
        LIMIT $limit
        """
        return self.execute_query(query, {"topic": topic, "limit": limit})

    def get_most_active_authors(self, community: str = None, limit: int = 10) -> List[Dict]:
        if community:
            query = """
            MATCH (a:Autor)-[:ESCRIBIO]->(m:Mensaje)-[:PERTENECE_A]->(c:Comunidad {nombre: $community})
            RETURN a.nombre as author, count(m) as message_count
            ORDER BY message_count DESC
            LIMIT $limit
            """
            return self.execute_query(query, {"community": community, "limit": limit})
        else:
            query = """
            MATCH (a:Autor)-[:ESCRIBIO]->(m:Mensaje)
            RETURN a.nombre as author, count(m) as message_count
            ORDER BY message_count DESC
            LIMIT $limit
            """
            return self.execute_query(query, {"limit": limit})

    def get_community_overview(self, community: str) -> Dict:
        query = """
        MATCH (c:Comunidad {nombre: $community})<-[:PERTENECE_A]-(m:Mensaje)
        WITH c, count(m) as total_messages, 
             collect(distinct m.sentimiento) as sentiments
        OPTIONAL MATCH (a:Autor)-[:ESCRIBIO]->(m:Mensaje)-[:PERTENECE_A]->(c)
        RETURN c.nombre as community, total_messages, count(distinct a) as total_authors,
               sentiments
        """
        results = self.execute_query(query, {"community": community})
        return results[0] if results else {}

    def full_text_search(self, search_term: str, limit: int = 15) -> List[Dict]:
        query = """
        MATCH (m:Mensaje)
        WHERE m.contenido CONTAINS $term
        OPTIONAL MATCH (a:Autor)-[:ESCRIBIO]->(m)
        OPTIONAL MATCH (t:Tema)<-[:SOBRE]-(m)
        RETURN m.contenido as content, a.nombre as author, t.nombre as topic, m.fecha as date
        ORDER BY m.fecha DESC
        LIMIT $limit
        """
        return self.execute_query(query, {"term": search_term, "limit": limit})
