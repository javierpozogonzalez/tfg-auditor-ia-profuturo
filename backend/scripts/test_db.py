from neo4j import GraphDatabase
import os
from dotenv import load_dotenv

load_dotenv("../../.env")

NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

with driver.session() as session:
    # Count posts
    result = session.run("MATCH (p:Post) RETURN count(p) as count")
    post_count = result.single()["count"]
    print(f"Total Posts: {post_count}")
    
    # Check for communities
    result = session.run("MATCH (c:Community) RETURN c.name as name")
    communities = [r["name"] for r in result]
    print(f"Communities: {communities}")
    
    # Try to get a sample post
    result = session.run("MATCH (a:Author)-[:WROTE]->(p:Post)-[:BELONGS_TO]->(c:Community) RETURN a.name, p.content, c.name LIMIT 1")
    record = result.single()
    if record:
        print(f"\nSample Post:")
        print(f"  Author: {record['a.name']}")
        print(f"  Community: {record['c.name']}")
        print(f"  Content: {record['p.content'][:100]}...")
    else:
        print("\nNo posts found with Author->Post->Community relationship")

driver.close()
