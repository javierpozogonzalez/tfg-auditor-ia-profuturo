import os
import sys
import re
import base64
import logging
import smtplib
from datetime import datetime, timedelta
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from neo4j import GraphDatabase

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.llm_config import get_llm, get_fast_llm
from src.tools import generate_report_pdf, generate_critical_alert_pdf
from src.agent import run_agent

load_dotenv()

NEO4J_URI      = os.getenv("NEO4J_URI")
NEO4J_USER     = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
ADMIN_EMAIL    = os.getenv("ADMIN_EMAIL")
GMAIL_ADDRESS  = os.getenv("GMAIL_ADDRESS")
GMAIL_APP_PASS = os.getenv("GMAIL_APP_PASS")

ALERTS_DIR = Path(__file__).parent.parent / "alerts"
ALERTS_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    filename="profuturo_rpa.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)
logger = logging.getLogger(__name__)

CRITICAL_PATTERNS = re.compile(
    r"\b(odio|insulto|acoso|amenaza|spam|malware|virus|crisis|urgente|peligro|"
    r"error|fallo|bug|ca[ií]do|congelado|lento|crash|timeout|desconectado|"
    r"bloqueado|no funciona|no carga|credenciales|queja|inaceptable|harto|injusto)\b",
    re.IGNORECASE,
)

SEVERITY_PROMPT = """Eres un clasificador de incidencias para la plataforma educativa ProFuturo.
Analiza el siguiente contenido de foro y clasifica su severidad.

Criterios:
- CRITICA: Caida total del sistema, brecha de seguridad, acoso grave o emergencia inmediata.
- ALTA: Usuarios sin acceso, fallos de red recurrentes, quejas formales graves.
- MEDIA: Soporte tecnico estandar, quejas menores, sugerencias de mejora.
- BAJA: Conversacion normal, consultas rutinarias o falsos positivos.

Responde exclusivamente con una de estas palabras: CRITICA, ALTA, MEDIA, BAJA.

Contenido a clasificar:
{content}"""

SUMMARY_PROMPT = """Eres el Auditor IA de ProFuturo. Genera un resumen ejecutivo semanal para la comunidad '{community}'.

Datos del periodo (ultimos 7 dias):
{messages}

El informe debe incluir las siguientes secciones en formato Markdown:
## Resumen Ejecutivo
## Temas Principales
## Nivel de Participacion
## Tendencias Detectadas
## Recomendaciones

Mantén un tono institucional, objetivo y orientado a la toma de decisiones directivas."""

REMINDER_PROMPT = """Eres el Auditor IA de ProFuturo. Redacta un mensaje de recordatorio semanal para la comunidad '{community}'.

Contexto de la semana:
{context}

El mensaje debe:
- Saludar a la comunidad de forma cercana y profesional.
- Destacar brevemente la actividad de la semana.
- Invitar a la participacion con un mensaje motivador.
- Ser conciso, maximo 3 parrafos.
- No mencionar que eres una IA."""

MENTION_RESPONSE_PROMPT = """Eres el Auditor IA de ProFuturo. Un miembro de la comunidad '{community}' te ha mencionado con la siguiente pregunta:

"{question}"

Responde de forma clara, util y con tono institucional. Si necesitas datos concretos del foro, indícalo.
Basa tu respuesta en el contexto disponible y no inventes métricas."""


def _get_driver():
    return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


def get_communities_list():
    driver = _get_driver()
    try:
        with driver.session() as session:
            result = session.run("MATCH (c:Community) RETURN c.name AS name ORDER BY c.name")
            return [r["name"] for r in result] or ["todas"]
    finally:
        driver.close()


def get_last_days_messages(days: int, community: str = None):
    driver = _get_driver()
    try:
        with driver.session() as session:
            cutoff = (datetime.now() - timedelta(days=days)).date()
            params = {"cutoff": cutoff}
            if community and community != "todas":
                query = """
                MATCH (a:Author)-[:WROTE]->(p:Post)-[:IN_DISCUSSION]->(d:Discussion)
                      -[:PERTAINS_TO]->(c:Community)
                WHERE c.name = $community AND p.date >= $cutoff
                RETURN a.name AS author, p.content AS text,
                       d.topic AS topic, c.name AS community, p.date AS date
                ORDER BY p.date DESC
                """
                params["community"] = community
            else:
                query = """
                MATCH (a:Author)-[:WROTE]->(p:Post)-[:IN_DISCUSSION]->(d:Discussion)
                      -[:PERTAINS_TO]->(c:Community)
                WHERE p.date >= $cutoff
                RETURN a.name AS author, p.content AS text,
                       d.topic AS topic, c.name AS community, p.date AS date
                ORDER BY p.date DESC
                """
            return [r.data() for r in session.run(query, **params)]
    finally:
        driver.close()


def get_unhandled_mentions():
    driver = _get_driver()
    try:
        with driver.session() as session:
            query = """
            MATCH (a:Author)-[:WROTE]->(p:Post)-[:IN_DISCUSSION]->(d:Discussion)
                  -[:PERTAINS_TO]->(c:Community)
            WHERE p.content CONTAINS '@Auditor IA'
            AND NOT EXISTS { MATCH (p)<-[:REPLIES_TO]-(:Post {author: 'Auditor IA'}) }
            RETURN p.id AS post_id, p.content AS content,
                   d.topic AS topic, c.name AS community, a.name AS author
            ORDER BY p.date DESC
            LIMIT 20
            """
            return [r.data() for r in session.run(query)]
    finally:
        driver.close()


def save_ai_reply(post_id: str, reply_content: str):
    driver = _get_driver()
    try:
        with driver.session() as session:
            session.run("""
            MATCH (p:Post {id: $post_id})
            CREATE (r:Post {
                id: randomUUID(),
                content: $content,
                date: date(),
                author: 'Auditor IA'
            })-[:REPLIES_TO]->(p)
            """, post_id=post_id, content=reply_content)
    finally:
        driver.close()


def send_admin_email(subject: str, body: str, attachment_path: str = None):
    if not all([ADMIN_EMAIL, GMAIL_ADDRESS, GMAIL_APP_PASS]):
        logger.warning("Credenciales de email no configuradas. Alerta no enviada por correo.")
        return

    msg = MIMEMultipart()
    msg["From"]    = GMAIL_ADDRESS
    msg["To"]      = ADMIN_EMAIL
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    if attachment_path and Path(attachment_path).exists():
        with open(attachment_path, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition",
                        f"attachment; filename={Path(attachment_path).name}")
        msg.attach(part)

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(GMAIL_ADDRESS, GMAIL_APP_PASS)
            smtp.sendmail(GMAIL_ADDRESS, ADMIN_EMAIL, msg.as_string())
        logger.info(f"Email enviado al administrador: {subject}")
    except Exception as e:
        logger.error(f"Error enviando email al administrador: {e}")


def _save_pdf(pdf_b64: str, filename: str) -> Path:
    path = ALERTS_DIR / filename
    path.write_bytes(base64.b64decode(pdf_b64))
    return path


def weekly_summary_job():
    logger.info("Iniciando weekly_summary_job")
    communities = get_communities_list()
    llm = get_llm()

    for community in communities:
        try:
            messages = get_last_days_messages(7, community)
            if not messages:
                logger.info(f"Sin mensajes en los ultimos 7 dias: {community}")
                continue

            messages_text = "\n".join(
                f"- [{m['date']}] {m['author']} en '{m['topic']}': {m['text'][:200]}"
                for m in messages[:60]
            )
            prompt       = SUMMARY_PROMPT.format(community=community, messages=messages_text)
            summary_text = llm.invoke([HumanMessage(content=prompt)]).content

            title    = f"Resumen_Semanal_{re.sub(r'[^\\w]', '_', community)}_{datetime.now().strftime('%Y%m%d')}"
            pdf_path = _save_pdf(generate_report_pdf(summary_text, title), f"{title}.pdf")
            logger.info(f"Resumen semanal generado: {pdf_path}")

        except Exception as e:
            logger.error(f"Error en weekly_summary_job para '{community}': {e}")


def weekly_reminder_job():
    logger.info("Iniciando weekly_reminder_job")
    communities = get_communities_list()
    llm = get_llm()

    for community in communities:
        try:
            messages = get_last_days_messages(7, community)
            if not messages:
                continue

            context = "\n".join(
                f"- {m['author']} en '{m['topic']}': {m['text'][:150]}"
                for m in messages[:20]
            )
            prompt  = REMINDER_PROMPT.format(community=community, context=context)
            message = llm.invoke([HumanMessage(content=prompt)]).content

            driver = _get_driver()
            try:
                with driver.session() as session:
                    session.run("""
                    MATCH (c:Community {name: $community})
                    MATCH (d:Discussion)-[:PERTAINS_TO]->(c)
                    WITH d LIMIT 1
                    CREATE (:Post {
                        id: randomUUID(),
                        content: $content,
                        date: date(),
                        author: 'Auditor IA'
                    })-[:IN_DISCUSSION]->(d)
                    """, community=community, content=message)
            finally:
                driver.close()

            logger.info(f"Recordatorio publicado en: {community}")

        except Exception as e:
            logger.error(f"Error en weekly_reminder_job para '{community}': {e}")


def critical_monitor_job():
    logger.info("Iniciando critical_monitor_job")
    communities = get_communities_list()
    fast_llm    = get_fast_llm()

    for community in communities:
        try:
            messages = get_last_days_messages(days=1, community=community)
            if not messages:
                continue

            candidates = [
                m for m in messages
                if CRITICAL_PATTERNS.search(f"{m.get('topic', '')} {m.get('text', '')}")
            ]
            if not candidates:
                continue

            critical_text = "\n".join(
                f"- [{m['author']}] {m['topic']}: {m['text'][:300]}"
                for m in candidates[:10]
            )

            severity_raw = fast_llm.invoke([
                HumanMessage(content=SEVERITY_PROMPT.format(content=critical_text))
            ]).content.strip().upper()

            severity = severity_raw if severity_raw in {"CRITICA", "ALTA", "MEDIA", "BAJA"} else "MEDIA"
            logger.info(f"Severidad clasificada [{severity}] en '{community}'")

            if severity not in {"CRITICA", "ALTA"}:
                continue

            issue_summary = "\n".join(
                f"{m['author']} - {m['topic']}: {m['text'][:250]}"
                for m in candidates[:5]
            )

            timestamp      = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_community = re.sub(r"[^\w]", "", community)
            filename       = f"ALERTA_{safe_community}_{timestamp}.pdf"
            pdf_path       = _save_pdf(
                generate_critical_alert_pdf(community, issue_summary, severity),
                filename
            )
            logger.info(f"PDF de alerta generado: {pdf_path}")

            send_admin_email(
                subject=f"ALERTA {severity} — {community}",
                body=(
                    f"Se ha detectado una incidencia de severidad {severity} "
                    f"en la comunidad '{community}'.\n\n"
                    f"Detalle:\n{issue_summary}\n\n"
                    f"Se adjunta el informe completo."
                ),
                attachment_path=str(pdf_path)
            )

        except Exception as e:
            logger.error(f"Error en critical_monitor_job para '{community}': {e}")


def mention_monitor_job():
    logger.info("Iniciando mention_monitor_job")
    mentions = get_unhandled_mentions()

    if not mentions:
        return

    for mention in mentions:
        try:
            question = re.sub(r"@Auditor\s*IA\s*", "", mention["content"]).strip()
            if not question:
                continue

            result = run_agent(question, mention["community"])
            reply  = result.get("response", "").strip()

            if reply:
                save_ai_reply(mention["post_id"], reply)
                logger.info(
                    f"Mencion respondida de '{mention['author']}' "
                    f"en '{mention['community']}'"
                )

        except Exception as e:
            logger.error(f"Error respondiendo mencion de '{mention.get('author')}': {e}")


def start_scheduler():
    scheduler = BlockingScheduler()

    scheduler.add_job(
        weekly_summary_job,
        CronTrigger(day_of_week="fri", hour=18, minute=0),
        id="weekly_summary",
        name="Weekly Summary",
        max_instances=1,
        misfire_grace_time=3600,
    )
    scheduler.add_job(
        weekly_reminder_job,
        CronTrigger(day_of_week="fri", hour=9, minute=0),
        id="weekly_reminder",
        name="Weekly Reminder",
        max_instances=1,
        misfire_grace_time=3600,
    )
    scheduler.add_job(
        critical_monitor_job,
        IntervalTrigger(minutes=30),
        id="critical_monitor",
        name="Critical Monitor",
        max_instances=1,
    )
    scheduler.add_job(
        mention_monitor_job,
        IntervalTrigger(minutes=5),
        id="mention_monitor",
        name="Mention Monitor",
        max_instances=1,
    )

    logger.info("RPA Scheduler iniciado con 4 jobs activos")

    try:
        scheduler.start()
    except KeyboardInterrupt:
        logger.info("Scheduler detenido manualmente")
        scheduler.shutdown()


if __name__ == "__main__":
    start_scheduler()