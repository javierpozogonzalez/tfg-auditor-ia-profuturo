import os
import sys
import re
import base64
import logging
import smtplib
from collections import Counter
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
from neo4j import GraphDatabase

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.llm_config import get_profuturo_llm
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
    filename=str(Path(__file__).parent.parent / "profuturo_rpa.log"),
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)
logger = logging.getLogger(__name__)

CRITICAL_PATTERNS = re.compile(
    r"\b(acoso|amenaza|malware|virus|crisis|urgente|peligro|"
    r"ca[ií]do|congelad[oa]|crash|timeout|desconectado|bloqueado|"
    r"no funciona|no carga|no avanza|no aparece|no marca|sin acceso|"
    r"fallo de red|incidencia|soporte t[eé]cnico|credenciales|"
    r"error cr[ií]tico|fallo cr[ií]tico|sistema ca[ií]do|gracias|agradec|felicit)\b",
    re.IGNORECASE,
)

DOUBT_PATTERNS = re.compile(
    r"\b(no\s+entiendo|no\s+s[eé]|duda|pregunta|c[oó]mo\s+se|alguien\s+sabe|me\s+podr[ií]a|"
    r"pueden\s+ayudar|no\s+me\s+queda\s+claro|tengo\s+una\s+pregunta|consulta|no\s+logro|"
    r"no\s+puedo|qu[eé]\s+significa|c[oó]mo\s+funciona|explica|no\s+encuentro|no\s+aparece)\b",
    re.IGNORECASE,
)

SUGGESTION_PATTERNS = re.compile(
    r"\b(propongo|suger[ií]a|sugerencia|podr[ií]amos|ser[ií]a\s+bueno|ser[ií]a\s+[uú]til|"
    r"se\s+podr[ií]a|por\s+qu[eé]\s+no|mejora|mejorar[ií]a|idea|deber[ií]amos|"
    r"se\s+podr[ií]a\s+incluir|propuesta)\b",
    re.IGNORECASE,
)

MATERIAL_PATTERNS = re.compile(
    r"\b(el\s+curso|la\s+formaci[oó]n|el\s+m[oó]dulo|el\s+recurso|los\s+materiales|el\s+contenido|"
    r"la\s+lectura|el\s+libro|el\s+manual|la\s+gu[ií]a|la\s+actividad|el\s+ejercicio|"
    r"la\s+evaluaci[oó]n|la\s+tarea|el\s+video|el\s+tutorial|la\s+unidad)\b",
    re.IGNORECASE,
)

UNANSWERED_DAYS        = 365  # TESTING: en producción usar 2
DISCONNECTION_ACTIVE   = 90  # ventana histórica para definir "antes activo" (días)
DISCONNECTION_IDLE     = 21  # días sin publicar para marcar como en riesgo

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
## Propuestas de Formacion Recomendadas

En la seccion 'Propuestas de Formacion Recomendadas', basandote en los temas y dudas detectadas esta semana, sugiere entre 2 y 4 propuestas concretas de formacion para la comunidad, indicando el tema, el motivo y el formato sugerido (taller, recurso, sesion en vivo, etc.).

Manten un tono institucional, objetivo y orientado a la toma de decisiones directivas."""

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
                WHERE c.name = $community AND date(p.date) >= $cutoff
                RETURN a.name AS author, p.content AS text,
                       d.topic AS topic, c.name AS community, p.date AS date
                ORDER BY p.date DESC
                """
                params["community"] = community
            else:
                query = """
                MATCH (a:Author)-[:WROTE]->(p:Post)-[:IN_DISCUSSION]->(d:Discussion)
                      -[:PERTAINS_TO]->(c:Community)
                WHERE date(p.date) >= $cutoff
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


def get_unanswered_discussions(days_threshold: int = UNANSWERED_DAYS, community: str = None) -> list:
    """Discusiones cuyo último post tiene más de days_threshold días sin actividad."""
    driver = _get_driver()
    try:
        with driver.session() as session:
            cutoff = (datetime.now() - timedelta(days=days_threshold)).date()
            if community and community != "todas":
                query = """
                MATCH (p:Post)-[:IN_DISCUSSION]->(d:Discussion)-[:PERTAINS_TO]->(c:Community)
                WHERE c.name = $community
                WITH d, c, max(p.date) AS last_activity
                WHERE date(last_activity) <= $cutoff
                RETURN d.topic AS topic, toString(last_activity) AS last_activity, c.name AS community
                ORDER BY last_activity ASC LIMIT 15
                """
                params = {"community": community, "cutoff": cutoff}
            else:
                query = """
                MATCH (p:Post)-[:IN_DISCUSSION]->(d:Discussion)-[:PERTAINS_TO]->(c:Community)
                WITH d, c, max(p.date) AS last_activity
                WHERE date(last_activity) <= $cutoff
                RETURN d.topic AS topic, toString(last_activity) AS last_activity, c.name AS community
                ORDER BY last_activity ASC LIMIT 15
                """
                params = {"cutoff": cutoff}
            return [r.data() for r in session.run(query, **params)]
    finally:
        driver.close()


def get_disconnection_risk(community: str = None) -> dict:
    """Usuarios antes activos que han dejado de publicar y recién llegados con un solo post."""
    driver = _get_driver()
    try:
        with driver.session() as session:
            cutoff_active = (datetime.now() - timedelta(days=DISCONNECTION_ACTIVE)).date()
            cutoff_idle   = (datetime.now() - timedelta(days=DISCONNECTION_IDLE)).date()

            if community and community != "todas":
                at_risk = [r.data() for r in session.run("""
                    MATCH (a:Author)-[:WROTE]->(p:Post)-[:IN_DISCUSSION]->(:Discussion)-[:PERTAINS_TO]->(c:Community)
                    WHERE c.name = $community AND date(p.date) >= $cutoff_active
                    WITH a, max(p.date) AS last_post, count(p) AS total_posts
                    WHERE date(last_post) <= $cutoff_idle AND total_posts >= 3
                    RETURN a.name AS author, toString(last_post) AS last_post, total_posts
                    ORDER BY last_post ASC LIMIT 10
                """, community=community, cutoff_active=cutoff_active, cutoff_idle=cutoff_idle)]

                single_post = [r.data() for r in session.run("""
                    MATCH (a:Author)-[:WROTE]->(p:Post)-[:IN_DISCUSSION]->(:Discussion)-[:PERTAINS_TO]->(c:Community)
                    WHERE c.name = $community
                    WITH a, count(p) AS total_posts
                    WHERE total_posts = 1
                    RETURN a.name AS author, total_posts LIMIT 10
                """, community=community)]
            else:
                at_risk = [r.data() for r in session.run("""
                    MATCH (a:Author)-[:WROTE]->(p:Post)-[:IN_DISCUSSION]->(:Discussion)-[:PERTAINS_TO]->(:Community)
                    WHERE date(p.date) >= $cutoff_active
                    WITH a, max(p.date) AS last_post, count(p) AS total_posts
                    WHERE date(last_post) <= $cutoff_idle AND total_posts >= 3
                    RETURN a.name AS author, toString(last_post) AS last_post, total_posts
                    ORDER BY last_post ASC LIMIT 10
                """, cutoff_active=cutoff_active, cutoff_idle=cutoff_idle)]

                single_post = [r.data() for r in session.run("""
                    MATCH (a:Author)-[:WROTE]->(p:Post)
                    WITH a, count(p) AS total_posts
                    WHERE total_posts = 1
                    RETURN a.name AS author, total_posts LIMIT 10
                """)]

            return {"at_risk": at_risk, "single_post": single_post}
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
    """Resumen semanal consolidado — siempre 1 PDF con todas las comunidades activas."""
    logger.info("Iniciando weekly_summary_job")
    communities = get_communities_list()
    llm = get_profuturo_llm()

    sections = []
    total_messages = 0

    for community in communities:
        try:
            messages = get_last_days_messages(365, community)  # TESTING: 365 días
            if not messages:
                continue
            total_messages += len(messages)
            summary = "\n".join(
                f"- [{m['date']}] {m['author']}: {m['text'][:120]}"
                for m in messages[:30]
            )
            sections.append({"name": community, "count": len(messages), "data": summary})
        except Exception as e:
            logger.error(f"Error procesando '{community}': {e}")

    if not sections:
        logger.info("No hay actividad para resumen semanal")
        return

    prompt = (
        f"Eres el Auditor IA de ProFuturo. Genera un resumen ejecutivo semanal consolidado.\n\n"
        f"DATOS GENERALES:\n"
        f"- Total de mensajes: {total_messages}\n"
        f"- Comunidades activas: {len(sections)}\n\n"
        f"ACTIVIDAD POR COMUNIDAD:\n"
    )
    for sec in sections:
        prompt += f"\n## {sec['name']} ({sec['count']} mensajes)\n{sec['data']}\n"

    prompt += (
        "\n\nESTRUCTURA DEL INFORME:\n"
        "# Resumen Ejecutivo General\n"
        "(Visión global — destacar comunidades más/menos activas)\n\n"
        "# Análisis por Comunidad\n"
        "## [Comunidad 1]\n- Temas Principales\n- Participación\n- Tendencias\n\n"
        "# Recomendaciones Transversales\n"
        "(Acciones que aplican a múltiples comunidades)\n\n"
        "# Propuestas de Formación\n"
        "(2-4 propuestas priorizadas)\n\n"
        "Tono institucional, objetivo, orientado a decisiones."
    )

    try:
        content  = str(llm.invoke(prompt)).strip()
        timestamp = datetime.now().strftime("%Y%m%d")
        title    = f"Resumen_Semanal_{timestamp}"
        pdf_path = _save_pdf(generate_report_pdf(content, title), f"{title}.pdf")

        send_admin_email(
            subject=f"Resumen Semanal — ProFuturo — {datetime.now().strftime('%d/%m/%Y')}",
            body=(
                f"Resumen semanal consolidado.\n\n"
                f"Comunidades activas: {len(sections)}\n"
                f"Total de mensajes: {total_messages}\n\n"
                f"Generado automaticamente por el Auditor IA."
            ),
            attachment_path=str(pdf_path),
        )
        logger.info(f"Resumen consolidado enviado ({len(sections)} comunidades, {total_messages} mensajes)")
    except Exception as e:
        logger.error(f"Error generando resumen consolidado: {e}")


def weekly_reminder_job():
    logger.info("Iniciando weekly_reminder_job")
    communities = get_communities_list()
    llm = get_profuturo_llm()

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
            message = str(llm.invoke(prompt)).strip()

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
    """Monitor crítico — batch inteligente: 1 alerta consolidada por ciclo si hay incidencias ALTA/CRITICA."""
    logger.info("Iniciando critical_monitor_job")
    communities = get_communities_list()
    llm = get_profuturo_llm()

    all_issues = []

    for community in communities:
        try:
            messages = get_last_days_messages(days=365, community=community)  # TESTING
            if not messages:
                continue
            candidates = [
                m for m in messages
                if CRITICAL_PATTERNS.search(f"{m.get('topic', '')} {m.get('text', '')}")
            ]
            if candidates:
                all_issues.append({
                    "community": community,
                    "count": len(candidates),
                    "issues": candidates[:8],
                })
        except Exception as e:
            logger.error(f"Error en critical_monitor para '{community}': {e}")

    if not all_issues:
        logger.info("No se detectaron incidencias críticas")
        return

    full_text = ""
    for comm in all_issues:
        full_text += f"\n## {comm['community']} ({comm['count']} incidencias)\n"
        for issue in comm["issues"]:
            full_text += f"- [{issue['author']}] {issue['topic']}: {issue['text'][:200]}\n"

    severity_raw = str(llm.invoke(SEVERITY_PROMPT.format(content=full_text))).strip().upper()
    severity = severity_raw if severity_raw in {"CRITICA", "ALTA", "MEDIA", "BAJA"} else "MEDIA"
    total_issues = sum(c["count"] for c in all_issues)
    logger.info(f"Severidad batch: {severity} ({total_issues} incidencias en {len(all_issues)} comunidades)")

    if severity not in {"CRITICA", "ALTA"}:
        logger.info("Severidad no requiere alerta (MEDIA/BAJA)")
        return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if len(all_issues) == 1:
        comm      = all_issues[0]
        _comm_safe = re.sub(r'[^\w]', '', comm['community'])
        filename  = f"ALERTA_{_comm_safe}_{timestamp}.pdf"
        alert_title = comm["community"]
    else:
        filename    = f"ALERTA_CONSOLIDADA_{timestamp}.pdf"
        alert_title = f"{len(all_issues)} COMUNIDADES"

    pdf_path = _save_pdf(
        generate_critical_alert_pdf(alert_title, full_text, severity),
        filename,
    )

    communities_str = ", ".join(c["community"] for c in all_issues)
    send_admin_email(
        subject=f"ALERTA {severity} — {alert_title}",
        body=(
            f"Incidencias de severidad {severity} detectadas.\n\n"
            f"Comunidades afectadas: {communities_str}\n"
            f"Total de incidencias: {total_issues}\n\n"
            f"Detalle en PDF adjunto."
        ),
        attachment_path=str(pdf_path),
    )
    logger.info(f"Alerta consolidada enviada: {severity} ({len(all_issues)} comunidades)")


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


def unanswered_monitor_job():
    """Monitor de hilos sin respuesta — solo alerta si hay ≥5 hilos en total (consolidado)."""
    logger.info("Iniciando unanswered_monitor_job")
    communities = get_communities_list()
    llm = get_profuturo_llm()

    all_threads = []

    for community in communities:
        try:
            stale = get_unanswered_discussions(UNANSWERED_DAYS, community)
            if stale:
                all_threads.append({"community": community, "threads": stale[:10]})
        except Exception as e:
            logger.error(f"Error en unanswered_monitor para '{community}': {e}")

    total_count = sum(len(c["threads"]) for c in all_threads)

    if total_count < 5:
        logger.info(f"Solo {total_count} hilos sin respuesta — umbral mínimo no alcanzado (≥5)")
        return

    summary = f"Total: {total_count} hilos sin actividad reciente\n\n"
    for comm in all_threads:
        summary += f"## {comm['community']} ({len(comm['threads'])} hilos)\n"
        for t in comm["threads"]:
            summary += f"- {t['topic']} (última actividad: {t['last_activity']})\n"
        summary += "\n"

    prompt = (
        f"Eres el Auditor IA de ProFuturo. Analiza estos hilos sin respuesta "
        f"y sugiere acciones de dinamización:\n\n{summary}"
    )
    analysis = str(llm.invoke(prompt)).strip()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename  = f"HILOS_PENDIENTES_{timestamp}.pdf"
    pdf_path  = _save_pdf(
        generate_report_pdf(analysis, "Hilos_Sin_Respuesta"),
        filename,
    )

    send_admin_email(
        subject=f"Hilos sin actividad — {total_count} detectados",
        body=(
            f"Se detectaron {total_count} hilo(s) sin actividad reciente.\n\n"
            f"{summary}\n"
            f"Se adjunta análisis con recomendaciones."
        ),
        attachment_path=str(pdf_path),
    )
    logger.info(f"Alerta hilos pendientes enviada ({total_count} hilos en {len(all_threads)} comunidades)")


def disconnection_risk_job():
    """Riesgo de abandono — 1 PDF consolidado con secciones por comunidad."""
    logger.info("Iniciando disconnection_risk_job")
    communities = get_communities_list()
    llm = get_profuturo_llm()

    active_sections = []

    for community in communities:
        try:
            risk_data = get_disconnection_risk(community=community)
            at_risk   = risk_data.get("at_risk", [])
            single_p  = risk_data.get("single_post", [])

            if not at_risk and len(single_p) < 3:
                continue

            lines = [f"## {community}"]
            if at_risk:
                lines.append(f"\n**Usuarios antes activos sin actividad reciente ({len(at_risk)}):**")
                for r in at_risk:
                    lines.append(f"  - {r['author']}: último post {r['last_post']} ({r['total_posts']} posts totales)")
            if single_p:
                lines.append(f"\n**Recién llegados con un solo post ({len(single_p)}):**")
                for r in single_p[:8]:
                    lines.append(f"  - {r['author']}")

            active_sections.append({
                "community": community,
                "at_risk_count": len(at_risk),
                "single_count": len(single_p),
                "text": "\n".join(lines),
            })
        except Exception as e:
            logger.error(f"Error en disconnection_risk para '{community}': {e}")

    if not active_sections:
        logger.info("No se detectaron usuarios en riesgo de abandono")
        return

    total_at_risk  = sum(s["at_risk_count"] for s in active_sections)
    total_single   = sum(s["single_count"]   for s in active_sections)
    full_content   = "\n\n".join(s["text"] for s in active_sections)

    prompt = (
        f"Eres el Auditor IA de ProFuturo. Genera un informe consolidado de riesgo de abandono "
        f"para {len(active_sections)} comunidades.\n\n"
        f"DATOS POR COMUNIDAD:\n{full_content}\n\n"
        f"Para cada comunidad incluye:\n"
        f"- Análisis del perfil de usuarios en riesgo\n"
        f"- Recomendaciones de reactivación específicas\n\n"
        f"Cierra con recomendaciones transversales aplicables a todas las comunidades."
    )
    analysis = str(llm.invoke(prompt)).strip()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename  = f"RIESGO_ABANDONO_CONSOLIDADO_{timestamp}.pdf"
    pdf_path  = _save_pdf(
        generate_report_pdf(analysis, "Riesgo_Abandono_Consolidado"),
        filename,
    )

    communities_str = ", ".join(s["community"] for s in active_sections)
    send_admin_email(
        subject=f"Riesgo de abandono — {len(active_sections)} comunidades",
        body=(
            f"Informe consolidado de usuarios en riesgo de desconexión.\n\n"
            f"Comunidades analizadas: {communities_str}\n"
            f"Usuarios antes activos en riesgo: {total_at_risk}\n"
            f"Recién llegados con 1 solo post: {total_single}\n\n"
            f"Se adjunta el análisis completo con recomendaciones."
        ),
        attachment_path=str(pdf_path),
    )
    logger.info(f"Riesgo abandono consolidado enviado ({len(active_sections)} comunidades, {total_at_risk} en riesgo)")


def trending_topics_job():
    """Análisis de tendencias — solo reporta si ≥3 temas con crecimiento >50% (consolidado)."""
    logger.info("Iniciando trending_topics_job")
    communities = get_communities_list()
    llm = get_profuturo_llm()

    significant_trends = []

    for community in communities:
        try:
            current    = get_last_days_messages(days=60,  community=community)  # TESTING
            historical = get_last_days_messages(days=120, community=community)  # TESTING

            if not current:
                continue

            current_topics = Counter(m.get("topic") or "sin tema" for m in current)
            hist_topics    = Counter(m.get("topic") or "sin tema" for m in historical)
            prev_topics    = Counter({
                k: max(hist_topics[k] - current_topics.get(k, 0), 0)
                for k in hist_topics
            })

            trends = []
            for topic, count in current_topics.most_common(10):
                prev     = prev_topics.get(topic, 0)
                delta    = count - prev
                gpct     = (delta / prev * 100) if prev > 0 else float("inf")
                if gpct > 50 or (gpct == float("inf") and count >= 3):
                    trends.append((topic, count, prev, delta, gpct))

            if len(trends) >= 3:
                significant_trends.append({"community": community, "trends": trends[:5]})

        except Exception as e:
            logger.error(f"Error en trending_topics para '{community}': {e}")

    if not significant_trends:
        logger.info("No se detectaron tendencias significativas (crecimiento >50%)")
        return

    content = "# Temas Emergentes (Crecimiento >50%)\n\n"
    for comm in significant_trends:
        content += f"## {comm['community']}\n"
        for topic, cnt, prev, delta, gpct in comm["trends"]:
            growth = f"+{delta} (+{gpct:.0f}%)" if gpct != float("inf") else f"+{delta} (nuevo)"
            content += f"- **{topic}**: {cnt} posts ({growth})\n"
        content += "\n"

    prompt = (
        f"Eres el Auditor IA de ProFuturo. Analiza estos temas emergentes "
        f"y proporciona insights estratégicos:\n\n{content}"
    )
    analysis = str(llm.invoke(prompt)).strip()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename  = f"TENDENCIAS_{timestamp}.pdf"
    pdf_path  = _save_pdf(
        generate_report_pdf(f"{content}\n\n# Análisis\n\n{analysis}", "Tendencias"),
        filename,
    )

    send_admin_email(
        subject=f"Tendencias Emergentes — {len(significant_trends)} comunidades",
        body=(
            f"Temas con crecimiento >50% detectados en {len(significant_trends)} comunidad(es).\n\n"
            f"Se adjunta análisis estratégico."
        ),
        attachment_path=str(pdf_path),
    )
    logger.info(f"Reporte de tendencias enviado ({len(significant_trends)} comunidades)")


def doubt_suggestion_monitor_job():
    logger.info("Iniciando doubt_suggestion_monitor_job")
    communities = get_communities_list()
    llm = get_profuturo_llm()

    for community in communities:
        try:
            messages = get_last_days_messages(days=1, community=community)
            if not messages:
                continue

            doubts = [
                m for m in messages
                if DOUBT_PATTERNS.search(f"{m.get('topic', '')} {m.get('text', '')}")
            ]
            suggestions = [
                m for m in messages
                if SUGGESTION_PATTERNS.search(f"{m.get('topic', '')} {m.get('text', '')}")
            ]

            if not doubts and not suggestions:
                continue

            lines = []
            if doubts:
                lines.append(f"Dudas detectadas ({len(doubts)}):")
                for m in doubts[:8]:
                    lines.append(f"  [{m['author']}] {m['topic']}: {m['text'][:200]}")
            if suggestions:
                lines.append(f"\nSugerencias detectadas ({len(suggestions)}):")
                for m in suggestions[:8]:
                    lines.append(f"  [{m['author']}] {m['topic']}: {m['text'][:200]}")

            content = "\n".join(lines)
            prompt = (
                f"Eres el Auditor IA de ProFuturo. Resume y clasifica las siguientes dudas y sugerencias "
                f"detectadas hoy en la comunidad '{community}':\n\n{content}\n\n"
                f"Proporciona un resumen ejecutivo y recomendaciones de accion prioritaria."
            )
            analysis = str(llm.invoke(prompt)).strip()
            logger.info(f"Dudas/sugerencias en '{community}': {len(doubts)} dudas, {len(suggestions)} sugerencias")

            send_admin_email(
                subject=f"Dudas y sugerencias detectadas — {community}",
                body=(
                    f"Resumen diario de dudas y sugerencias en '{community}':\n\n"
                    f"{analysis}\n\nDetalle:\n{content}"
                ),
            )

        except Exception as e:
            logger.error(f"Error en doubt_suggestion_monitor_job para '{community}': {e}")


def material_feedback_monitor_job():
    logger.info("Iniciando material_feedback_monitor_job")
    communities = get_communities_list()
    llm = get_profuturo_llm()

    for community in communities:
        try:
            messages = get_last_days_messages(days=7, community=community)
            if not messages:
                continue

            feedback_msgs = [
                m for m in messages
                if MATERIAL_PATTERNS.search(f"{m.get('topic', '')} {m.get('text', '')}")
            ]

            if len(feedback_msgs) < 3:
                continue

            content = "\n".join(
                f"- [{m['author']}] {m['topic']}: {m['text'][:250]}"
                for m in feedback_msgs[:15]
            )
            prompt = (
                f"Eres el Auditor IA de ProFuturo. Analiza las siguientes opiniones sobre materiales "
                f"formativos en la comunidad '{community}':\n\n{content}\n\n"
                f"Identifica: (1) materiales mas mencionados, (2) valoraciones positivas y negativas, "
                f"(3) sugerencias de mejora. Genera un resumen ejecutivo con alertas si hay criticas graves."
            )
            analysis = str(llm.invoke(prompt)).strip()

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_comm = re.sub(r"[^\w]", "", community)
            filename  = f"FEEDBACK_MATERIALES_{safe_comm}_{timestamp}.pdf"
            pdf_path  = _save_pdf(
                generate_report_pdf(analysis, f"Feedback_Materiales_{safe_comm}"),
                filename,
            )

            send_admin_email(
                subject=f"Feedback sobre materiales formativos — {community}",
                body=(
                    f"Se han detectado {len(feedback_msgs)} mensaje(s) con feedback sobre materiales "
                    f"formativos en la comunidad '{community}'.\n\nSe adjunta el analisis completo."
                ),
                attachment_path=str(pdf_path),
            )
            logger.info(f"Feedback materiales en '{community}': {len(feedback_msgs)} mensajes")

        except Exception as e:
            logger.error(f"Error en material_feedback_monitor_job para '{community}': {e}")


_scheduler: BlockingScheduler | None = None


def get_scheduler() -> BlockingScheduler | None:
    return _scheduler


def start_scheduler():
    global _scheduler
    _scheduler = BlockingScheduler()

    # --- JOBS ACTIVOS ---

    _scheduler.add_job(
        weekly_summary_job,
        CronTrigger(day_of_week="fri", hour=18, minute=0),
        id="weekly_summary",
        name="Weekly Summary",
        max_instances=1,
        misfire_grace_time=3600,
    )
    _scheduler.add_job(
        critical_monitor_job,
        IntervalTrigger(minutes=30),
        id="critical_monitor",
        name="Critical Monitor",
        max_instances=1,
    )
    _scheduler.add_job(
        unanswered_monitor_job,
        IntervalTrigger(hours=6),
        id="unanswered_monitor",
        name="Unanswered Threads Monitor",
        max_instances=1,
    )
    _scheduler.add_job(
        disconnection_risk_job,
        CronTrigger(day_of_week="mon", hour=8, minute=0),
        id="disconnection_risk",
        name="Disconnection Risk Monitor",
        max_instances=1,
        misfire_grace_time=3600,
    )
    _scheduler.add_job(
        trending_topics_job,
        CronTrigger(day_of_week="fri", hour=17, minute=0),
        id="trending_topics",
        name="Trending Topics",
        max_instances=1,
        misfire_grace_time=3600,
    )

    # --- JOBS PENDIENTES DE INTEGRACIÓN (comentados) ---

    # [PINCHTAB] weekly_reminder_job: publica recordatorios semanales en los foros via API Pinchtab.
    # Pendiente: integrar con el endpoint real de Pinchtab para publicacion automatica desatendida.
    # scheduler.add_job(
    #     weekly_reminder_job,
    #     CronTrigger(day_of_week="fri", hour=9, minute=0),
    #     id="weekly_reminder",
    #     name="Weekly Reminder (Pinchtab)",
    #     max_instances=1,
    #     misfire_grace_time=3600,
    # )

    # [@AUDITOR IA] mention_monitor_job: responde menciones directas al bot en hilos del foro.
    # Pendiente: validar el flujo de escritura de respuestas en Neo4j y su sincronizacion con Pinchtab.
    # scheduler.add_job(
    #     mention_monitor_job,
    #     IntervalTrigger(minutes=5),
    #     id="mention_monitor",
    #     name="Mention Monitor (@Auditor IA)",
    #     max_instances=1,
    # )

    # [DIARIO] doubt_suggestion_monitor_job: clasifica dudas y sugerencias del feed.
    # Pendiente: ajustar patrones DOUBT/SUGGESTION con datos reales de Pinchtab antes de activar.
    # _scheduler.add_job(
    #     doubt_suggestion_monitor_job,
    #     CronTrigger(hour=9, minute=30),
    #     id="doubt_suggestion_monitor",
    #     name="Doubt & Suggestion Monitor",
    #     max_instances=1,
    # )

    # [SEMANAL] material_feedback_monitor_job: analiza opiniones sobre materiales formativos.
    # Pendiente: ajustar umbrales de deteccion con datos reales.
    # _scheduler.add_job(
    #     material_feedback_monitor_job,
    #     CronTrigger(day_of_week="wed", hour=10, minute=0),
    #     id="material_feedback",
    #     name="Material Feedback Monitor",
    #     max_instances=1,
    #     misfire_grace_time=3600,
    # )

    logger.info(
        "RPA Scheduler iniciado: weekly_summary + critical_monitor + "
        "unanswered_monitor + disconnection_risk + trending_topics activos"
    )

    try:
        _scheduler.start()
    except KeyboardInterrupt:
        logger.info("Scheduler detenido manualmente")
        _scheduler.shutdown()


if __name__ == "__main__":
    start_scheduler()