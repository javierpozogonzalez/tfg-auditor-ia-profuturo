import os
import asyncio
import base64
from concurrent.futures import ThreadPoolExecutor
from typing import Optional
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from src.agent import run_agent

_executor = ThreadPoolExecutor(max_workers=4)

load_dotenv()

app = FastAPI(title="ProFuturo AI Analytics Backend")

origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str
    community: str = "todas"


class PDFData(BaseModel):
    base64: str
    filename: str


class ChatResponse(BaseModel):
    response: str
    community: str
    pdf: Optional[PDFData] = None
    success: bool


def _neo4j_date_to_str(date_value) -> str:
    if date_value is None:
        return ""
    try:
        from neo4j.time import DateTime as Neo4jDateTime, Date as Neo4jDate
        if isinstance(date_value, (Neo4jDateTime, Neo4jDate)):
            return f"{date_value.year:04d}-{date_value.month:02d}-{date_value.day:02d}"
    except (ImportError, AttributeError):
        pass
    raw = str(date_value)
    return raw[:10] if len(raw) >= 10 else raw


def _get_neo4j_driver():
    uri = os.getenv("NEO4J_URI")
    user = os.getenv("NEO4J_USER")
    password = os.getenv("NEO4J_PASSWORD")
    if not uri or not user or not password:
        raise RuntimeError("NEO4J_URI, NEO4J_USER and NEO4J_PASSWORD must be set")
    from neo4j import GraphDatabase
    return GraphDatabase.driver(uri, auth=(user, password))


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "ProFuturo AI Analytics"}


@app.post("/api/chat")
async def chat(request: ChatRequest):
    try:
        if not request.message or len(request.message.strip()) == 0:
            raise HTTPException(status_code=400, detail="Message cannot be empty")

        loop = asyncio.get_event_loop()
        result = await asyncio.wait_for(
            loop.run_in_executor(
                _executor, run_agent, request.message, request.community
            ),
            timeout=600.0
        )

        pdf_data = None
        if result.get("pdf_base64"):
            pdf_data = PDFData(
                base64=result["pdf_base64"],
                filename=result.get("pdf_filename", "report.pdf"),
            )

        return ChatResponse(
            response=result.get("response", ""),
            community=request.community,
            pdf=pdf_data,
            success=True,
        )

    except asyncio.TimeoutError:
        return ChatResponse(
            response="La generacion del analisis y PDF supero el tiempo maximo permitido (600s). Reintenta.",
            community=request.community,
            pdf=None,
            success=False,
        )
    except Exception as e:
        return ChatResponse(
            response=f"Error procesando la consulta: {str(e)}",
            community=request.community,
            pdf=None,
            success=False,
        )


@app.post("/api/chat-with-file")
async def chat_with_file(
    message: str = Form(...),
    community: str = Form("todas"),
    file: Optional[UploadFile] = File(None)
):
    try:
        if not message or len(message.strip()) == 0:
            raise HTTPException(status_code=400, detail="Message cannot be empty")

        file_content = ""
        if file:
            content_bytes = await file.read()
            if file.filename and file.filename.endswith(".csv"):
                file_content = content_bytes.decode("utf-8")
            elif file.filename and file.filename.endswith(".pdf"):
                file_content = f"[Archivo PDF adjunto: {file.filename}, {len(content_bytes)} bytes]"
            else:
                file_content = f"[Archivo adjunto: {file.filename}]"

        enhanced_message = message
        if file_content:
            enhanced_message = f"{message}\n\nArchivo adjunto:\n{file_content[:2000]}"

        loop = asyncio.get_event_loop()
        result = await asyncio.wait_for(
            loop.run_in_executor(
                _executor, run_agent, enhanced_message, community
            ),
            timeout=600.0
        )

        pdf_data = None
        if result.get("pdf_base64"):
            pdf_data = PDFData(
                base64=result["pdf_base64"],
                filename=result.get("pdf_filename", "report.pdf"),
            )

        return ChatResponse(
            response=result.get("response", ""),
            community=community,
            pdf=pdf_data,
            success=True,
        )

    except asyncio.TimeoutError:
        return ChatResponse(
            response="La generacion del analisis y PDF supero el tiempo maximo permitido (600s). Reintenta.",
            community=community,
            pdf=None,
            success=False,
        )
    except Exception as e:
        return ChatResponse(
            response=f"Error procesando la consulta: {str(e)}",
            community=community,
            pdf=None,
            success=False,
        )


@app.get("/api/communities")
async def get_communities():
    driver = _get_neo4j_driver()
    try:
        with driver.session() as session:
            results = session.run(
                "MATCH (c:Community) RETURN c.name AS name ORDER BY c.name"
            )
            names = [record["name"] for record in results if record["name"]]
    finally:
        driver.close()

    return {"communities": names}


@app.get("/api/feed")
async def get_feed(community: str = "todas"):
    driver = _get_neo4j_driver()
    messages = []

    try:
        with driver.session() as session:
            if community == "todas":
                query = """
                MATCH (a:Author)-[:WROTE]->(p:Post)-[:IN_DISCUSSION]->(d:Discussion)-[:PERTAINS_TO]->(c:Community)
                RETURN
                    p.id          AS id,
                    a.name        AS author,
                    p.content     AS excerpt,
                    d.topic       AS topic,
                    c.name        AS community,
                    p.date        AS date,
                    p.sentiment   AS sentiment
                ORDER BY p.date DESC
                LIMIT 20
                """
                results = session.run(query)
            else:
                query = """
                MATCH (a:Author)-[:WROTE]->(p:Post)-[:IN_DISCUSSION]->(d:Discussion)-[:PERTAINS_TO]->(c:Community)
                WHERE c.name = $community
                RETURN
                    p.id          AS id,
                    a.name        AS author,
                    p.content     AS excerpt,
                    d.topic       AS topic,
                    c.name        AS community,
                    p.date        AS date,
                    p.sentiment   AS sentiment
                ORDER BY p.date DESC
                LIMIT 20
                """
                results = session.run(query, community=community)

            for record in results:
                msg = record.data()
                date_str = _neo4j_date_to_str(msg.get("date"))
                community_name = str(msg.get("community") or "general")

                messages.append({
                    "id": str(msg.get("id") or ""),
                    "author": str(msg.get("author") or "Anonimo"),
                    "topic": str(msg.get("topic") or "Discusion en foro")[:120],
                    "community": community_name,
                    "excerpt": str(msg.get("excerpt") or "")[:300],
                    "time": date_str,
                    "replies": 0,
                    "communityColor": "bg-blue-200",
                    "sentiment": str(msg.get("sentiment") or "neutral"),
                })

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error consultando Neo4j: {str(e)}",
        )
    finally:
        driver.close()

    return {
        "success": True,
        "community": community,
        "count": len(messages),
        "messages": messages,
    }


@app.get("/api/graph")
async def get_graph(community: str = "todas"):
    driver = _get_neo4j_driver()
    try:
        with driver.session() as session:
            if community == "todas":
                query = """
                MATCH (a:Author)-[:WROTE]->(p:Post)-[:IN_DISCUSSION]->(d:Discussion)-[:PERTAINS_TO]->(c:Community)
                RETURN
                    a.name        AS author,
                    d.topic       AS discussion,
                    c.name        AS community,
                    count(p)      AS post_count
                ORDER BY post_count DESC
                LIMIT 60
                """
                results = session.run(query)
            else:
                query = """
                MATCH (a:Author)-[:WROTE]->(p:Post)-[:IN_DISCUSSION]->(d:Discussion)-[:PERTAINS_TO]->(c:Community)
                WHERE c.name = $community
                RETURN
                    a.name        AS author,
                    d.topic       AS discussion,
                    c.name        AS community,
                    count(p)      AS post_count
                ORDER BY post_count DESC
                LIMIT 60
                """
                results = session.run(query, community=community)

            edges = [
                {
                    "author": str(r["author"] or ""),
                    "discussion": str(r["discussion"] or "Sin titulo"),
                    "community": str(r["community"] or ""),
                    "post_count": int(r["post_count"] or 0),
                }
                for r in results
            ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error consultando Neo4j: {str(e)}")
    finally:
        driver.close()

    return {"success": True, "community": community, "edges": edges}


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", 8000))

    uvicorn.run(app, host=host, port=port)
