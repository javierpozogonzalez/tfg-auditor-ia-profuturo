"""
Agente autonomo de ProFuturo — publica mensajes en Moodle de forma proactiva.

Activar con: AUTONOMOUS_AGENT_ENABLED=true
Modo simulacion (por defecto): MOODLE_SIMULATION_MODE=true
"""
import logging
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from dotenv import load_dotenv
from neo4j import GraphDatabase

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.llm_config import get_profuturo_llm
from src.moodle_writer import post_to_forum, create_forum_discussion
from src.autonomous_rules import (
    can_reactivate_thread,
    should_welcome_user,
    can_respond_to_mention,
    needs_moderation_alert,
)

load_dotenv()

# ── Logging separado ─────────────────────────────────────────────────────────
_log_file    = Path(__file__).resolve().parent.parent / "autonomous_agent.log"
_log_handler = logging.FileHandler(str(_log_file), encoding="utf-8")
_log_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
logger = logging.getLogger("autonomous_agent")
logger.addHandler(_log_handler)
logger.setLevel(logging.INFO)

# ── Configuracion ─────────────────────────────────────────────────────────────
NEO4J_URI      = os.getenv("NEO4J_URI")
NEO4J_USER     = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
ADMIN_EMAIL    = os.getenv("ADMIN_EMAIL")
GMAIL_ADDRESS  = os.getenv("GMAIL_ADDRESS")
GMAIL_APP_PASS = os.getenv("GMAIL_APP_PASS")

MAX_REACTIVATIONS = int(os.getenv("MAX_REACTIVATIONS_PER_RUN", "5"))
MAX_WELCOMES      = int(os.getenv("MAX_WELCOMES_PER_RUN", "10"))
MAX_MENTIONS      = int(os.getenv("MAX_MENTIONS_PER_RUN", "10"))

# Forum ID por defecto hasta que ProFuturo proporcione los IDs reales.
# Sobreescribir con MOODLE_DEFAULT_FORUM_ID o mapear por comunidad.
MOODLE_DEFAULT_FORUM_ID = int(os.getenv("MOODLE_DEFAULT_FORUM_ID", "1"))

AI_SIGNATURE = "\n\n---\nAuditor IA ProFuturo\nMensaje generado automaticamente"

# ── Prompts ───────────────────────────────────────────────────────────────────
REACTIVATION_PROMPT = """Eres el Auditor IA de ProFuturo. El siguiente hilo lleva dias sin actividad.
Escribe un mensaje de reactivacion de maximo 150 palabras que:
- Reconozca brevemente el tema del hilo
- Ofrezca una orientacion inicial util
- Invite a otros miembros a participar
Tono profesional y educativo. Sin emojis. Sin mencionar que eres una IA.

Comunidad: {community}
Hilo: {topic}
"""

WELCOME_PROMPT = """Eres el Auditor IA de ProFuturo. Un nuevo miembro acaba de hacer su primer post.
Escribe un mensaje de bienvenida de maximo 100 palabras que:
- Salude al nuevo miembro por su nombre
- Mencione brevemente el tema de su primer post
- Sugiera uno o dos usuarios o hilos relevantes de la comunidad
Tono cercano y profesional. Sin emojis. Sin mencionar que eres una IA.

Comunidad: {community}
Nuevo miembro: {author}
Primer post (tema): {topic}
Contexto de la comunidad: {context}
"""

MENTION_RESPONSE_PROMPT = """Eres el Auditor IA de ProFuturo. Un miembro te ha mencionado directamente.
Responde en maximo 200 palabras de forma clara y util.
Basa tu respuesta en el contexto proporcionado. No inventes datos ni metricas.
Tono institucional. Sin emojis.

Comunidad: {community}
Autor que pregunta: {author}
Pregunta: {question}
Contexto de la comunidad: {context}
"""

WEEKLY_DIGEST_PROMPT = """Eres el Auditor IA de ProFuturo. Genera el resumen semanal para la comunidad '{community}'.

Datos de la semana:
{data}

El resumen debe incluir:
1. Cifras clave: total de posts, participantes activos, hilos nuevos
2. Temas mas debatidos esta semana
3. Posts que han generado mas interaccion
4. Hilos que necesitan participacion (sin respuesta)
5. Un mensaje de cierre motivador para la comunidad

Formato estructurado con secciones. Tono institucional. Sin emojis.
Maximo 400 palabras.
"""

RECOGNITION_PROMPT = """Eres el Auditor IA de ProFuturo. Genera un mensaje de reconocimiento semanal.
Maximo 100 palabras. Menciona contribuciones concretas del usuario reconocido.
Tono positivo, profesional. Sin emojis. Sin mencionar que eres una IA.

Comunidad: {community}
Usuario reconocido: {author}
Posts esta semana: {post_count}
Temas en los que participo: {topics}
"""


# ── Driver Neo4j ──────────────────────────────────────────────────────────────
def _get_driver():
    return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


def _get_communities() -> list[str]:
    driver = _get_driver()
    try:
        with driver.session() as session:
            rows = session.run("MATCH (c:Community) RETURN c.name AS name ORDER BY c.name").data()
            return [r["name"] for r in rows] or []
    finally:
        driver.close()


def _send_alert(subject: str, body: str) -> None:
    """Envia email de alerta al coordinador (reutiliza la funcion de rpa.py)."""
    try:
        from scripts.rpa import send_admin_email
        send_admin_email(subject=subject, body=body)
    except Exception as exc:
        logger.error("Error enviando alerta por email: %s", exc)


# ── Job 1: Reactivacion de hilos sin respuesta (7-14 dias) ───────────────────
def reactivation_job() -> dict:
    """
    Cada 6 horas. Busca hilos con 0 respuestas y 7-14 dias de antiguedad.
    Genera un mensaje de reactivacion y lo publica en Moodle.
    Limite: MAX_REACTIVATIONS_PER_RUN por ejecucion.
    """
    logger.info("Inicio reactivation_job")
    llm        = get_profuturo_llm()
    driver     = _get_driver()
    communities = _get_communities()
    published  = 0
    _sim = os.getenv("MOODLE_SIMULATION_MODE", "true").lower() == "true"
    results: dict = {"candidates_found": 0, "messages_generated": 0, "simulation": _sim, "sample_message": ""}

    for community in communities:
        if published >= MAX_REACTIVATIONS:
            break
        try:
            # --- SOLO PARA PRUEBA (restaurar tras demo) ---
            # ORIGINAL: cutoff_min = (datetime.now() - timedelta(days=14)).date()
            # ORIGINAL: cutoff_max = (datetime.now() - timedelta(days=7)).date()
            cutoff_min = (datetime.now() - timedelta(days=500)).date()
            cutoff_max = (datetime.now() - timedelta(days=1)).date()
            # --- FIN SOLO PARA PRUEBA ---

            with driver.session() as session:
                candidates = session.run("""
                    MATCH (d:Discussion)-[:PERTAINS_TO]->(c:Community)
                    WHERE c.name = $community
                    OPTIONAL MATCH (p:Post)-[:IN_DISCUSSION]->(d)
                    WITH d, count(p) AS total_posts, max(p.date) AS last_activity
                    WHERE total_posts = 1
                      AND date(last_activity) >= $cutoff_min
                      AND date(last_activity) <= $cutoff_max
                      AND NOT EXISTS { MATCH (d) WHERE d.ai_reactivated = true }
                    RETURN d.id AS discussion_id, d.topic AS topic,
                           toString(last_activity) AS last_activity
                    LIMIT 10
                """, community=community, cutoff_min=cutoff_min, cutoff_max=cutoff_max).data()

            results["candidates_found"] += len(candidates)
            logger.info(
                "reactivation_job — comunidad='%s' candidatos=%d", community, len(candidates)
            )

            for thread in candidates:
                if published >= MAX_REACTIVATIONS:
                    break

                if not _sim:
                    thread_data = {
                        "reply_count":    0,
                        "last_activity":  thread.get("last_activity"),
                        "ai_reactivated": False,
                    }
                    if not can_reactivate_thread(thread_data):
                        continue

                topic       = str(thread.get("topic") or "sin tema")
                disc_id_neo = thread.get("discussion_id") or 0

                prompt  = REACTIVATION_PROMPT.format(community=community, topic=topic)
                message = str(llm.invoke(prompt)).strip() + AI_SIGNATURE
                results["messages_generated"] += 1
                if not results["sample_message"]:
                    results["sample_message"] = message[:300]
                logger.info("[SIMULACION] Mensaje para '%s': %s", topic[:60], message[:200])
                published += 1

                if not _sim:
                    subject = f"Re: {topic[:80]}"
                    result  = post_to_forum(
                        discussion_id=int(disc_id_neo) if disc_id_neo else MOODLE_DEFAULT_FORUM_ID,
                        subject=subject,
                        message=message,
                    )
                    if result["success"]:
                        with driver.session() as session:
                            session.run("""
                                MATCH (d:Discussion {id: $disc_id})
                                SET d.ai_reactivated = true, d.ai_reactivated_date = date()
                            """, disc_id=str(disc_id_neo))
                        logger.info(
                            "Hilo reactivado — comunidad='%s' topic='%s'",
                            community, topic[:60],
                        )

        except Exception as exc:
            logger.error("Error en reactivation_job para '%s': %s", community, exc)

    driver.close()
    logger.info("reactivation_job completado — publicaciones=%d", published)
    return results


# ── Job 2: Bienvenida a nuevos usuarios ──────────────────────────────────────
def welcome_job() -> dict:
    """
    Cada 2 horas. Busca usuarios con 1 solo post y menos de 2 dias.
    Genera un mensaje de bienvenida personalizado y lo publica como respuesta.
    Limite: MAX_WELCOMES_PER_RUN por ejecucion.
    """
    logger.info("Inicio welcome_job")
    llm        = get_profuturo_llm()
    driver     = _get_driver()
    communities = _get_communities()
    published  = 0
    _sim = os.getenv("MOODLE_SIMULATION_MODE", "true").lower() == "true"
    results: dict = {"candidates_found": 0, "messages_generated": 0, "simulation": _sim, "sample_message": ""}
    # --- SOLO PARA PRUEBA (restaurar tras demo) ---
    # ORIGINAL: cutoff = (datetime.now() - timedelta(days=2)).date()
    cutoff     = (datetime.now() - timedelta(days=500)).date()
    # --- FIN SOLO PARA PRUEBA ---

    for community in communities:
        if published >= MAX_WELCOMES:
            break
        try:
            with driver.session() as session:
                new_users = session.run("""
                    MATCH (a:Author)-[:WROTE]->(p:Post)-[:IN_DISCUSSION]->(d:Discussion)
                          -[:PERTAINS_TO]->(c:Community)
                    WHERE c.name = $community
                    WITH a, count(p) AS total_posts, min(p.date) AS first_post_date,
                         collect(d.topic)[0] AS first_topic,
                         collect(p.id)[0] AS first_post_id,
                         collect(d.id)[0] AS disc_id
                    WHERE total_posts = 1
                      AND date(first_post_date) >= $cutoff
                      AND NOT EXISTS { MATCH (a) WHERE a.ai_welcomed = true }
                    RETURN a.name AS author, toString(first_post_date) AS first_post_date,
                           first_topic AS topic, first_post_id AS post_id, disc_id
                    LIMIT 20
                """, community=community, cutoff=cutoff).data()

                top_users = session.run("""
                    MATCH (a:Author)-[:WROTE]->(p:Post)-[:IN_DISCUSSION]->(:Discussion)
                          -[:PERTAINS_TO]->(c:Community)
                    WHERE c.name = $community
                    RETURN a.name AS name, count(p) AS posts
                    ORDER BY posts DESC LIMIT 3
                """, community=community).data()

            context = "Usuarios mas activos: " + ", ".join(
                f"{r['name']} ({r['posts']} posts)" for r in top_users
            ) if top_users else ""

            results["candidates_found"] += len(new_users)
            logger.info(
                "welcome_job — comunidad='%s' nuevos=%d", community, len(new_users)
            )

            for user in new_users:
                if published >= MAX_WELCOMES:
                    break

                if not _sim:
                    user_data = {
                        "total_posts":     1,
                        "ai_welcomed":     False,
                        "first_post_date": user.get("first_post_date"),
                    }
                    if not should_welcome_user(user_data):
                        continue

                author  = str(user.get("author") or "nuevo miembro")
                topic   = str(user.get("topic")  or "sin tema")
                disc_id = user.get("disc_id") or MOODLE_DEFAULT_FORUM_ID

                prompt  = WELCOME_PROMPT.format(
                    community=community, author=author, topic=topic, context=context
                )
                message = str(llm.invoke(prompt)).strip() + AI_SIGNATURE
                results["messages_generated"] += 1
                if not results["sample_message"]:
                    results["sample_message"] = message[:300]
                logger.info("[SIMULACION] Bienvenida a '%s': %s", author, message[:200])
                published += 1

                if not _sim:
                    subject = f"Bienvenida a {author}"
                    result  = post_to_forum(
                        discussion_id=int(disc_id) if disc_id else MOODLE_DEFAULT_FORUM_ID,
                        subject=subject,
                        message=message,
                    )
                    if result["success"]:
                        with driver.session() as session:
                            session.run("""
                                MATCH (a:Author {name: $author})
                                SET a.ai_welcomed = true
                            """, author=author)
                        logger.info(
                            "Bienvenida enviada — comunidad='%s' autor='%s'",
                            community, author,
                        )

        except Exception as exc:
            logger.error("Error en welcome_job para '%s': %s", community, exc)

    driver.close()
    logger.info("welcome_job completado — publicaciones=%d", published)
    return results


# ── Job 3: Respuesta a menciones directas ────────────────────────────────────
def mention_response_job() -> dict:
    """
    Cada 30 minutos. Busca posts con '@Auditor' en las ultimas 24 horas sin respuesta.
    Genera una respuesta contextual y la publica en el mismo hilo.
    Limite: MAX_MENTIONS_PER_RUN por ejecucion.
    """
    logger.info("Inicio mention_response_job")
    llm      = get_profuturo_llm()
    driver   = _get_driver()
    _sim = os.getenv("MOODLE_SIMULATION_MODE", "true").lower() == "true"
    results: dict = {"candidates_found": 0, "messages_generated": 0, "simulation": _sim, "sample_message": ""}
    # --- SOLO PARA PRUEBA (restaurar tras demo) ---
    # ORIGINAL: cutoff = (datetime.now() - timedelta(hours=24)).date()
    cutoff   = (datetime.now() - timedelta(days=500)).date()
    # --- FIN SOLO PARA PRUEBA ---
    published = 0

    try:
        with driver.session() as session:
            mentions = session.run("""
                MATCH (a:Author)-[:WROTE]->(p:Post)-[:IN_DISCUSSION]->(d:Discussion)
                      -[:PERTAINS_TO]->(c:Community)
                WHERE (p.content CONTAINS '@Auditor' OR p.content CONTAINS '@auditor')
                  AND date(p.date) >= $cutoff
                  AND NOT EXISTS { MATCH (p) WHERE p.ai_answered = true }
                RETURN p.id AS post_id, p.content AS content,
                       d.topic AS topic, d.id AS disc_id,
                       c.name AS community, a.name AS author
                ORDER BY p.date DESC
                LIMIT 30
            """, cutoff=cutoff).data()

        results["candidates_found"] = len(mentions)
        logger.info("mention_response_job — menciones encontradas=%d", len(mentions))

        for mention in mentions:
            if published >= MAX_MENTIONS:
                break

            if not _sim:
                post_data = {
                    "content":     mention.get("content", ""),
                    "ai_answered": False,
                }
                if not can_respond_to_mention(post_data):
                    continue

            # Escalado de moderacion: aplica siempre
            if needs_moderation_alert({"content": mention.get("content", ""), "topic": mention.get("topic", "")}):
                _send_alert(
                    subject=f"Alerta de moderacion — {mention.get('community')}",
                    body=(
                        f"Un post que menciona al Auditor IA requiere revision humana.\n\n"
                        f"Comunidad: {mention.get('community')}\n"
                        f"Autor: {mention.get('author')}\n"
                        f"Hilo: {mention.get('topic')}\n"
                        f"Contenido: {mention.get('content', '')[:300]}"
                    ),
                )
                logger.info(
                    "Mencion escalada a coordinador — autor='%s' comunidad='%s'",
                    mention.get("author"), mention.get("community"),
                )
                if not _sim:
                    with driver.session() as session:
                        session.run(
                            "MATCH (p:Post {id: $pid}) SET p.ai_answered = true",
                            pid=str(mention.get("post_id", "")),
                        )
                continue

            question = re.sub(r"@[Aa]uditor(\s*(IA|_IA)?)?", "", mention["content"]).strip()
            if not question:
                question = mention.get("topic", "la pregunta planteada")

            community = str(mention.get("community", ""))
            author    = str(mention.get("author", ""))
            topic     = str(mention.get("topic", "sin tema"))
            disc_id   = mention.get("disc_id") or MOODLE_DEFAULT_FORUM_ID

            with driver.session() as session:
                context_rows = session.run("""
                    MATCH (:Author)-[:WROTE]->(p:Post)-[:IN_DISCUSSION]->(d:Discussion)
                          -[:PERTAINS_TO]->(c:Community)
                    WHERE c.name = $community
                    RETURN p.content AS content
                    ORDER BY p.date DESC LIMIT 10
                """, community=community).data()
            context = " ".join(str(r.get("content", ""))[:100] for r in context_rows)[:800]

            prompt  = MENTION_RESPONSE_PROMPT.format(
                community=community, author=author, question=question, context=context
            )
            message = str(llm.invoke(prompt)).strip() + AI_SIGNATURE
            results["messages_generated"] += 1
            if not results["sample_message"]:
                results["sample_message"] = message[:300]
            logger.info("[SIMULACION] Respuesta a '%s': %s", author, message[:200])
            published += 1

            if not _sim:
                subject = f"Re: {topic[:80]}"
                result  = post_to_forum(
                    discussion_id=int(disc_id) if disc_id else MOODLE_DEFAULT_FORUM_ID,
                    subject=subject,
                    message=message,
                )
                if result["success"]:
                    with driver.session() as session:
                        session.run(
                            "MATCH (p:Post {id: $pid}) SET p.ai_answered = true",
                            pid=str(mention.get("post_id", "")),
                        )
                    logger.info(
                        "Mencion respondida — comunidad='%s' autor='%s'",
                        community, author,
                    )

    except Exception as exc:
        logger.error("Error en mention_response_job: %s", exc)
    finally:
        driver.close()

    logger.info("mention_response_job completado — respuestas=%d", published)
    return results


# ── Job 4: Resumen semanal publicado en el foro (viernes 17:00) ──────────────
def weekly_digest_post_job() -> None:
    """
    Viernes 17:00. Genera y publica el resumen semanal en el foro de cada comunidad activa.
    Una nueva discusion por comunidad.
    """
    logger.info("Inicio weekly_digest_post_job")
    llm        = get_profuturo_llm()
    driver     = _get_driver()
    communities = _get_communities()
    published  = 0
    cutoff     = (datetime.now() - timedelta(days=7)).date()

    for community in communities:
        try:
            with driver.session() as session:
                posts = session.run("""
                    MATCH (a:Author)-[:WROTE]->(p:Post)-[:IN_DISCUSSION]->(d:Discussion)
                          -[:PERTAINS_TO]->(c:Community)
                    WHERE c.name = $community AND date(p.date) >= $cutoff
                    RETURN a.name AS author, d.topic AS topic, count(p) AS posts
                    ORDER BY posts DESC
                """, community=community, cutoff=cutoff).data()

                unanswered = session.run("""
                    MATCH (p:Post)-[:IN_DISCUSSION]->(d:Discussion)-[:PERTAINS_TO]->(c:Community)
                    WHERE c.name = $community
                    WITH d, count(p) AS total
                    WHERE total = 1
                    RETURN d.topic AS topic LIMIT 5
                """, community=community).data()

            if not posts:
                continue

            total_posts   = sum(r["posts"] for r in posts)
            participants  = len(posts)
            top_topics    = "\n".join(f"- {r['topic']}: {r['posts']} posts" for r in posts[:5])
            pending_topics = "\n".join(f"- {r['topic']}" for r in unanswered[:3]) or "Ninguno"

            data = (
                f"Total posts: {total_posts}\n"
                f"Participantes: {participants}\n"
                f"Temas mas activos:\n{top_topics}\n"
                f"Hilos sin respuesta:\n{pending_topics}"
            )

            prompt  = WEEKLY_DIGEST_PROMPT.format(community=community, data=data)
            message = str(llm.invoke(prompt)).strip() + AI_SIGNATURE
            subject = f"Resumen semanal — {community} — {datetime.now().strftime('%d/%m/%Y')}"

            result = create_forum_discussion(
                forum_id=MOODLE_DEFAULT_FORUM_ID,
                subject=subject,
                message=message,
            )

            if result["success"]:
                published += 1
                logger.info(
                    "Resumen semanal publicado — comunidad='%s' simulado=%s",
                    community, result.get("simulated"),
                )

        except Exception as exc:
            logger.error("Error en weekly_digest_post_job para '%s': %s", community, exc)

    driver.close()
    logger.info("weekly_digest_post_job completado — comunidades=%d", published)


# ── Job 5: Reconocimiento semanal (lunes 09:00) ───────────────────────────────
def recognition_job() -> None:
    """
    Lunes 09:00. Detecta el usuario mas activo de la semana por comunidad
    y publica un mensaje de reconocimiento en el foro.
    1 reconocimiento por comunidad.
    """
    logger.info("Inicio recognition_job")
    llm        = get_profuturo_llm()
    driver     = _get_driver()
    communities = _get_communities()
    published  = 0
    cutoff     = (datetime.now() - timedelta(days=7)).date()

    for community in communities:
        try:
            with driver.session() as session:
                top = session.run("""
                    MATCH (a:Author)-[:WROTE]->(p:Post)-[:IN_DISCUSSION]->(d:Discussion)
                          -[:PERTAINS_TO]->(c:Community)
                    WHERE c.name = $community AND date(p.date) >= $cutoff
                    RETURN a.name AS author, count(p) AS post_count,
                           collect(DISTINCT d.topic)[..4] AS topics
                    ORDER BY post_count DESC LIMIT 1
                """, community=community, cutoff=cutoff).single()

            if not top or top["post_count"] < 2:
                continue

            author     = str(top["author"])
            post_count = int(top["post_count"])
            topics     = ", ".join(str(t) for t in (top["topics"] or [])[:4])

            prompt  = RECOGNITION_PROMPT.format(
                community=community, author=author, post_count=post_count, topics=topics
            )
            message = str(llm.invoke(prompt)).strip() + AI_SIGNATURE
            subject = f"Reconocimiento semanal — {community}"

            result = create_forum_discussion(
                forum_id=MOODLE_DEFAULT_FORUM_ID,
                subject=subject,
                message=message,
            )

            if result["success"]:
                published += 1
                logger.info(
                    "Reconocimiento publicado — comunidad='%s' autor='%s' simulado=%s",
                    community, author, result.get("simulated"),
                )

        except Exception as exc:
            logger.error("Error en recognition_job para '%s': %s", community, exc)

    driver.close()
    logger.info("recognition_job completado — comunidades=%d", published)


# ── Job 6: Deteccion de bugs / problemas repetidos (cada 4 horas) ─────────────
def bug_detection_job() -> None:
    """
    Cada 4 horas. Detecta cuando 3+ usuarios reportan el mismo tipo de problema en 48h.
    - Si hay 3-4 afectados: envia email de alerta al coordinador.
    - Si hay 5+: ademas publica un aviso tecnico en el foro.
    """
    logger.info("Inicio bug_detection_job")
    driver  = _get_driver()
    llm     = get_profuturo_llm()
    cutoff  = (datetime.now() - timedelta(hours=48)).date()

    # Palabras que indican problema tecnico
    _BUG_PATTERNS = re.compile(
        r"\b(error|no\s+funciona|no\s+carga|no\s+avanza|no\s+aparece|caido|crash|"
        r"timeout|sin\s+acceso|no\s+puedo\s+entrar|fallo|bloqueado|problema\s+t[eé]cnico)\b",
        re.IGNORECASE,
    )

    try:
        communities = _get_communities()

        for community in communities:
            with driver.session() as session:
                recent_posts = session.run("""
                    MATCH (a:Author)-[:WROTE]->(p:Post)-[:IN_DISCUSSION]->(d:Discussion)
                          -[:PERTAINS_TO]->(c:Community)
                    WHERE c.name = $community AND date(p.date) >= $cutoff
                    RETURN a.name AS author, p.content AS content, d.topic AS topic
                """, community=community, cutoff=cutoff).data()

            bug_posts = [
                p for p in recent_posts
                if _BUG_PATTERNS.search(f"{p.get('topic', '')} {p.get('content', '')}")
            ]

            if len(bug_posts) < 3:
                continue

            affected_users = len({p["author"] for p in bug_posts})
            summary_lines  = [
                f"- {p['author']}: {p['topic']}: {str(p['content'])[:150]}"
                for p in bug_posts[:8]
            ]
            summary = "\n".join(summary_lines)

            logger.info(
                "Bug potencial detectado — comunidad='%s' afectados=%d",
                community, affected_users,
            )

            _send_alert(
                subject=f"Posible problema tecnico — {community} ({affected_users} usuarios)",
                body=(
                    f"Se han detectado {len(bug_posts)} posts con indicadores de problema tecnico "
                    f"en las ultimas 48 horas en '{community}'.\n\n"
                    f"Usuarios afectados: {affected_users}\n\n"
                    f"Detalle:\n{summary}"
                ),
            )

            if affected_users >= 5:
                prompt = (
                    f"Eres el Auditor IA de ProFuturo. Redacta un breve aviso tecnico para la comunidad "
                    f"'{community}'. Indica que el equipo tecnico es consciente del problema, que se esta "
                    f"trabajando en ello y que se notificara cuando este resuelto. Maximo 80 palabras. "
                    f"Tono profesional y tranquilizador. Sin emojis."
                )
                message = str(llm.invoke(prompt)).strip() + AI_SIGNATURE
                result  = create_forum_discussion(
                    forum_id=MOODLE_DEFAULT_FORUM_ID,
                    subject=f"Aviso tecnico — {community}",
                    message=message,
                )
                logger.info(
                    "Aviso tecnico publicado — comunidad='%s' simulado=%s",
                    community, result.get("simulated"),
                )

    except Exception as exc:
        logger.error("Error en bug_detection_job: %s", exc)
    finally:
        driver.close()

    logger.info("bug_detection_job completado")


# ── Scheduler ─────────────────────────────────────────────────────────────────
_autonomous_scheduler: BackgroundScheduler | None = None


def get_autonomous_scheduler() -> BackgroundScheduler | None:
    return _autonomous_scheduler


def start_autonomous_scheduler() -> None:
    global _autonomous_scheduler

    _autonomous_scheduler = BackgroundScheduler()

    _autonomous_scheduler.add_job(
        reactivation_job,
        IntervalTrigger(hours=6),
        id="autonomous_reactivation",
        name="Reactivacion de hilos sin respuesta",
        max_instances=1,
    )
    _autonomous_scheduler.add_job(
        welcome_job,
        IntervalTrigger(hours=2),
        id="autonomous_welcome",
        name="Bienvenida a nuevos usuarios",
        max_instances=1,
    )
    _autonomous_scheduler.add_job(
        mention_response_job,
        IntervalTrigger(minutes=30),
        id="autonomous_mentions",
        name="Respuesta a menciones @Auditor",
        max_instances=1,
    )
    _autonomous_scheduler.add_job(
        weekly_digest_post_job,
        CronTrigger(day_of_week="fri", hour=17, minute=0),
        id="autonomous_weekly_digest",
        name="Resumen semanal en foro",
        max_instances=1,
        misfire_grace_time=3600,
    )
    _autonomous_scheduler.add_job(
        recognition_job,
        CronTrigger(day_of_week="mon", hour=9, minute=0),
        id="autonomous_recognition",
        name="Reconocimiento semanal",
        max_instances=1,
        misfire_grace_time=3600,
    )
    _autonomous_scheduler.add_job(
        bug_detection_job,
        IntervalTrigger(hours=4),
        id="autonomous_bug_detection",
        name="Deteccion de problemas tecnicos repetidos",
        max_instances=1,
    )

    _autonomous_scheduler.start()
    logger.info(
        "Agente autonomo iniciado: reactivation(6h) + welcome(2h) + "
        "mentions(30min) + weekly_digest(vie 17h) + recognition(lun 9h) + "
        "bug_detection(4h)"
    )
