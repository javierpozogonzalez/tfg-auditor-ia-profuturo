import os
import asyncio
import base64
import logging
import threading
from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor
from typing import Optional
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from src.agent import run_agent
from src.chat_history import (
    init_db,
    create_conversation,
    get_conversations_by_community,
    get_messages as get_conv_messages,
    save_message as save_conv_message,
    update_conversation_title,
    delete_conversation,
    generate_title_from_message,
)
from scripts.rpa import (
    start_scheduler, get_scheduler,
    critical_monitor_job, weekly_summary_job,
    unanswered_monitor_job, disconnection_risk_job, trending_topics_job,
)

_executor = ThreadPoolExecutor(max_workers=4)
logger = logging.getLogger(__name__)

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    threading.Thread(target=start_scheduler, daemon=True).start()
    logger.info("RPA Scheduler arrancado en background")

    if os.getenv("AUTONOMOUS_AGENT_ENABLED", "false").lower() == "true":
        from src.autonomous_agent import start_autonomous_scheduler
        start_autonomous_scheduler()
        logger.info("Agente autonomo iniciado")

    yield


app = FastAPI(title="ProFuturo AI Analytics Backend", lifespan=lifespan)

# origins = [
#     "http://localhost:3000",
#     "http://localhost:3001",
#     "http://127.0.0.1:3000",
#     "http://127.0.0.1:3001",
#     "http://0.0.0.0:3000",
#     "http://0.0.0.0:3001",
# ]
# custom_origins = os.getenv("CORS_ORIGINS", "").split(",")
# if custom_origins and custom_origins[0]:
#     origins.extend([o.strip() for o in custom_origins if o.strip()])

# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=origins,
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

# CAMBIO PARA FEEDBACK
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str
    community: str = "todas"
    history: list[dict] = []
    conversation_id: Optional[str] = None
    files: Optional[list[dict]] = None


class PDFData(BaseModel):
    base64: str
    filename: str


class ExcelData(BaseModel):
    base64: str
    filename: str


class ChatResponse(BaseModel):
    response: str
    community: str
    pdf: Optional[PDFData] = None
    excel: Optional[ExcelData] = None
    success: bool
    conversation_id: Optional[str] = None


class ConversationCreate(BaseModel):
    community: str
    title: Optional[str] = None


class ConversationUpdate(BaseModel):
    title: str


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


_neo4j_driver = None


def _get_neo4j_driver():
    global _neo4j_driver
    if _neo4j_driver is None:
        uri = os.getenv("NEO4J_URI")
        user = os.getenv("NEO4J_USER")
        password = os.getenv("NEO4J_PASSWORD")
        if not uri or not user or not password:
            raise RuntimeError("NEO4J_URI, NEO4J_USER and NEO4J_PASSWORD must be set")
        from neo4j import GraphDatabase
        _neo4j_driver = GraphDatabase.driver(uri, auth=(user, password))
    return _neo4j_driver


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "ProFuturo AI Analytics"}


# ── Conversations ──────────────────────────────────────────────────────────────

@app.get("/api/conversations/{community}")
async def list_conversations(community: str):
    convs = get_conversations_by_community(community)
    return {"conversations": convs}


@app.post("/api/conversations")
async def create_conversation_endpoint(body: ConversationCreate):
    title = body.title or "Nueva conversación"
    conv_id = create_conversation(body.community, title)
    return {"id": conv_id, "title": title}


@app.get("/api/conversations/{conversation_id}/messages")
async def conversation_messages(conversation_id: str):
    msgs = get_conv_messages(conversation_id)
    return {"messages": msgs}


@app.patch("/api/conversations/{conversation_id}")
async def rename_conversation(conversation_id: str, body: ConversationUpdate):
    update_conversation_title(conversation_id, body.title)
    return {"success": True}


@app.delete("/api/conversations/{conversation_id}")
async def remove_conversation(conversation_id: str):
    delete_conversation(conversation_id)
    return {"success": True}


@app.post("/api/chat")
async def chat(request: ChatRequest):
    try:
        if not request.message or len(request.message.strip()) == 0:
            raise HTTPException(status_code=400, detail="Message cannot be empty")

        loop = asyncio.get_event_loop()
        result = await asyncio.wait_for(
            loop.run_in_executor(
                _executor, run_agent, request.message, request.community, request.history
            ),
            timeout=600.0
        )

        pdf_data = None
        if result.get("pdf_base64"):
            pdf_data = PDFData(
                base64=result["pdf_base64"],
                filename=result.get("pdf_filename", "report.pdf"),
            )

        excel_data = None
        if result.get("excel_base64"):
            excel_data = ExcelData(
                base64=result["excel_base64"],
                filename=result.get("excel_filename", "reporte.xlsx"),
            )

        response_text = result.get("response", "")

        # Persist conversation (non-blocking, best-effort)
        conv_id = request.conversation_id
        try:
            if not conv_id:
                title = generate_title_from_message(request.message)
                conv_id = create_conversation(request.community, title)
            save_conv_message(conv_id, "user", request.message, request.files)
            save_conv_message(conv_id, "assistant", response_text)
        except Exception as _e:
            logger.warning(f"Could not persist conversation: {_e}")
            conv_id = None

        return ChatResponse(
            response=response_text,
            community=request.community,
            pdf=pdf_data,
            excel=excel_data,
            success=True,
            conversation_id=conv_id,
        )

    except asyncio.TimeoutError:
        return ChatResponse(
            response="La generacion del analisis y PDF supero el tiempo maximo permitido (600s). Reintenta.",
            community=request.community,
            pdf=None,
            excel=None,
            success=False,
        )
    except Exception as e:
        return ChatResponse(
            response=f"Error procesando la consulta: {str(e)}",
            community=request.community,
            pdf=None,
            excel=None,
            success=False,
        )


@app.post("/api/chat-with-file")
async def chat_with_file(
    message: str = Form(...),
    community: str = Form("todas"),
    history_json: str = Form("[]"),
    conversation_id: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None)
):
    try:
        if not message or len(message.strip()) == 0:
            raise HTTPException(status_code=400, detail="Message cannot be empty")

        file_content = ""
        if file:
            content_bytes = await file.read()
            if file.filename and file.filename.endswith(".csv"):
                file_content = content_bytes.decode("utf-8", errors="replace")
            elif file.filename and file.filename.endswith(".pdf"):
                try:
                    import io
                    from pypdf import PdfReader
                    reader = PdfReader(io.BytesIO(content_bytes))
                    pages = [p.extract_text() for p in reader.pages[:15] if p.extract_text()]
                    extracted = "\n\n".join(pages).strip()
                    if extracted:
                        logger.info(f"PDF '{file.filename}' extraido: {len(extracted)} chars")
                        logger.info(f"Primeros 300 chars del PDF: {extracted[:300]}")
                        file_content = extracted
                    else:
                        logger.warning(f"PDF '{file.filename}' sin texto extraible")
                        file_content = f"[PDF '{file.filename}' sin texto extraible — posiblemente escaneado sin OCR]"
                except Exception as e:
                    logger.error(f"Error extrayendo PDF '{file.filename}': {e}")
                    file_content = f"[PDF adjunto: {file.filename} — error al leer: {e}]"
            else:
                file_content = f"[Archivo adjunto: {file.filename}]"

        enhanced_message = message
        if file_content:
            enhanced_message = (
                f"════════════════════════════════════════════════════\n"
                f"DOCUMENTO ADJUNTO POR EL USUARIO — PRIORIDAD MAXIMA\n"
                f"════════════════════════════════════════════════════\n\n"
                f"El usuario ha subido el siguiente documento. DEBES basar tu respuesta "
                f"EXCLUSIVAMENTE en el contenido de este documento. NO uses tus criterios "
                f"por defecto. Sigue las instrucciones del documento al pie de la letra, "
                f"aunque te parezcan incorrectas o contradictorias.\n\n"
                f"--- INICIO DEL DOCUMENTO ---\n"
                f"{file_content[:6000]}\n"
                f"--- FIN DEL DOCUMENTO ---\n\n"
                f"════════════════════════════════════════════════════\n\n"
                f"Mensaje del usuario: {message}"
            )
            logger.info(f"enhanced_message con PDF formado: {len(enhanced_message)} chars totales")

        import json as _json
        try:
            client_history = _json.loads(history_json)
        except Exception:
            client_history = []

        loop = asyncio.get_event_loop()
        result = await asyncio.wait_for(
            loop.run_in_executor(
                _executor, run_agent, enhanced_message, community, client_history
            ),
            timeout=600.0
        )

        pdf_data = None
        if result.get("pdf_base64"):
            pdf_data = PDFData(
                base64=result["pdf_base64"],
                filename=result.get("pdf_filename", "report.pdf"),
            )

        excel_data = None
        if result.get("excel_base64"):
            excel_data = ExcelData(
                base64=result["excel_base64"],
                filename=result.get("excel_filename", "reporte.xlsx"),
            )

        response_text = result.get("response", "")

        # Persist conversation (best-effort)
        conv_id = conversation_id
        try:
            file_info = [{"name": file.filename, "type": file.content_type or "", "size": 0}] if file else None
            if not conv_id:
                title = generate_title_from_message(message)
                conv_id = create_conversation(community, title)
            save_conv_message(conv_id, "user", message, file_info)
            save_conv_message(conv_id, "assistant", response_text)
        except Exception as _e:
            logger.warning(f"Could not persist conversation: {_e}")
            conv_id = None

        return ChatResponse(
            response=response_text,
            community=community,
            pdf=pdf_data,
            excel=excel_data,
            success=True,
            conversation_id=conv_id,
        )

    except asyncio.TimeoutError:
        return ChatResponse(
            response="La generacion del analisis y PDF supero el tiempo maximo permitido (600s). Reintenta.",
            community=community,
            pdf=None,
            excel=None,
            success=False,
        )
    except Exception as e:
        return ChatResponse(
            response=f"Error procesando la consulta: {str(e)}",
            community=community,
            pdf=None,
            excel=None,
            success=False,
        )


@app.get("/api/communities")
async def get_communities():
    driver = _get_neo4j_driver()
    with driver.session() as session:
        results = session.run(
            "MATCH (c:Community) RETURN c.name AS name ORDER BY c.name"
        )
        names = [record["name"] for record in results if record["name"]]
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

    return {"success": True, "community": community, "edges": edges}


@app.get("/api/rpa/status")
async def rpa_status():
    scheduler = get_scheduler()
    if scheduler is None or not scheduler.running:
        return {"running": False, "jobs": []}

    jobs = []
    for job in scheduler.get_jobs():
        next_run = job.next_run_time
        jobs.append({
            "id": job.id,
            "name": job.name,
            "next_run": next_run.isoformat() if next_run else None,
        })
    return {"running": True, "jobs": jobs}


@app.post("/api/rpa/trigger/{job_id}")
async def rpa_trigger(job_id: str):
    _fn_map = {
        "critical_monitor":   critical_monitor_job,
        "weekly_summary":     weekly_summary_job,
        "unanswered_monitor": unanswered_monitor_job,
        "disconnection_risk": disconnection_risk_job,
        "trending_topics":    trending_topics_job,
    }
    if job_id not in _fn_map:
        raise HTTPException(status_code=400, detail=f"job_id must be one of {set(_fn_map)}")

    fn = _fn_map[job_id]
    loop = asyncio.get_event_loop()
    try:
        await asyncio.wait_for(
            loop.run_in_executor(_executor, fn),
            timeout=300.0,
        )
        return {"success": True, "job_id": job_id, "message": f"Job '{job_id}' ejecutado correctamente"}
    except asyncio.TimeoutError:
        return {"success": False, "job_id": job_id, "message": "Timeout (300s) ejecutando el job"}
    except Exception as e:
        return {"success": False, "job_id": job_id, "message": str(e)}


@app.get("/api/graph/stats")
async def get_graph_stats(community: str = "todas"):
    driver = _get_neo4j_driver()
    try:
        with driver.session() as session:
            base = """
            MATCH (a:Author)-[:WROTE]->(p:Post)-[:IN_DISCUSSION]->(d:Discussion)-[:PERTAINS_TO]->(c:Community)
            """
            where = "WHERE c.name = $community" if community != "todas" else ""
            params = {"community": community} if community != "todas" else {}

            stats_r = session.run(
                f"{base} {where} RETURN count(DISTINCT a) AS users, count(p) AS posts, count(DISTINCT d) AS discussions",
                **params,
            ).single()

            top_r = session.run(
                f"{base} {where} RETURN a.name AS name, count(p) AS posts ORDER BY posts DESC LIMIT 5",
                **params,
            ).data()

        if not stats_r:
            return {"total_users": 0, "total_posts": 0, "total_discussions": 0, "top_connectors": [], "avg_posts_per_user": 0}

        total_users = stats_r["users"] or 0
        return {
            "total_users": total_users,
            "total_posts": stats_r["posts"] or 0,
            "total_discussions": stats_r["discussions"] or 0,
            "top_connectors": [r["name"] for r in top_r],
            "avg_posts_per_user": round((stats_r["posts"] or 0) / max(total_users, 1), 1),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error consultando Neo4j: {str(e)}")


@app.get("/api/rpa/logs")
async def rpa_logs(lines: int = 50):
    log_path = os.path.join(os.path.dirname(__file__), "..", "profuturo_rpa.log")
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            all_lines = f.readlines()
        return {"lines": [l.rstrip() for l in all_lines[-lines:]]}
    except FileNotFoundError:
        return {"lines": []}


# ── Agente autonomo — endpoints de testing y estado ───────────────────────────

@app.get("/api/autonomous/status")
async def autonomous_status():
    if os.getenv("AUTONOMOUS_AGENT_ENABLED", "false").lower() != "true":
        return {"enabled": False, "running": False, "jobs": []}

    try:
        from src.autonomous_agent import get_autonomous_scheduler
        scheduler = get_autonomous_scheduler()
    except ImportError:
        return {"enabled": True, "running": False, "jobs": []}

    if scheduler is None or not scheduler.running:
        return {"enabled": True, "running": False, "jobs": []}

    jobs = [
        {
            "id":       job.id,
            "name":     job.name,
            "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
        }
        for job in scheduler.get_jobs()
    ]
    return {"enabled": True, "running": True, "jobs": jobs}


@app.post("/api/autonomous/test-reactivation")
async def test_reactivation():
    try:
        from src.autonomous_agent import reactivation_job
        loop = asyncio.get_event_loop()
        await asyncio.wait_for(
            loop.run_in_executor(_executor, reactivation_job), timeout=120.0
        )
        return {"success": True, "job": "reactivation_job"}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


@app.post("/api/autonomous/test-welcome")
async def test_welcome():
    try:
        from src.autonomous_agent import welcome_job
        loop = asyncio.get_event_loop()
        await asyncio.wait_for(
            loop.run_in_executor(_executor, welcome_job), timeout=120.0
        )
        return {"success": True, "job": "welcome_job"}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


@app.post("/api/autonomous/test-mention")
async def test_mention():
    try:
        from src.autonomous_agent import mention_response_job
        loop = asyncio.get_event_loop()
        await asyncio.wait_for(
            loop.run_in_executor(_executor, mention_response_job), timeout=120.0
        )
        return {"success": True, "job": "mention_response_job"}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", 8000))

    uvicorn.run(app, host=host, port=port)
