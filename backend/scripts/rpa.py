import os
import sys
import re
import base64
import logging
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from neo4j import GraphDatabase
from langchain_core.messages import HumanMessage

logging.basicConfig(
    filename="profuturo_rpa.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)
logger = logging.getLogger(__name__)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.llm_config import get_llm
from src.tools import generate_report_pdf, generate_critical_alert_pdf

load_dotenv()

NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

ALERTS_DIR = os.path.join(os.path.dirname(__file__), "..", "alerts")
Path(ALERTS_DIR).mkdir(exist_ok=True)


def get_communities_list():
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        with driver.session() as session:
            result = session.run("MATCH (c:Community) RETURN c.name AS name")
            communities = [record["name"] for record in result]
    finally:
        driver.close()
    return communities if communities else ["todas"]


def get_last_days_messages(days: int, community: str = None):
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        with driver.session() as session:
            cutoff_date = (datetime.now() - timedelta(days=days)).date()
            
            if community and community != "todas":
                query = """
                MATCH (a:Author)-[:WROTE]->(p:Post)-[:IN_DISCUSSION]->(d:Discussion)-[:PERTAINS_TO]->(c:Community)
                WHERE c.name = $community AND p.date >= $cutoff_date
                RETURN a.name AS author, p.content AS text, d.topic AS topic, c.name AS community, p.date AS date
                ORDER BY p.date DESC
                """
                result = session.run(query, community=community, cutoff_date=cutoff_date)
            else:
                query = """
                MATCH (a:Author)-[:WROTE]->(p:Post)-[:IN_DISCUSSION]->(d:Discussion)-[:PERTAINS_TO]->(c:Community)
                WHERE p.date >= $cutoff_date
                RETURN a.name AS author, p.content AS text, d.topic AS topic, c.name AS community, p.date AS date
                ORDER BY p.date DESC
                """
                result = session.run(query, cutoff_date=cutoff_date)
            
            records = [record.data() for record in result]
    finally:
        driver.close()
    return records


def weekly_summary_job():
    logger.info(f"[{datetime.now().isoformat()}] Iniciando weekly_summary_job")
    
    communities = get_communities_list()
    llm = get_llm()
    
    for community in communities:
        try:
            messages = get_last_days_messages(7, community)
            
            if not messages:
                logger.info(f"  No hay mensajes en los ultimos 7 dias para {community}")
                continue
            
            messages_text = "\n".join([
                f"- [{msg['date']}] {msg['author']} en '{msg['topic']}': {msg['text'][:200]}"
                for msg in messages[:50]
            ])
            
            prompt = f"""Genera un resumen ejecutivo semanal de la comunidad '{community}' basado en los siguientes mensajes de los últimos 7 días:

{messages_text}

El resumen debe incluir:
- Temas principales discutidos
- Nivel de participación
- Cambios o tendencias notables
- Recomendaciones clave

Usa formato Markdown estructurado."""
            
            response = llm.invoke([HumanMessage(content=prompt)])
            summary_text = response.content
            
            title = f"Resumen_Semanal_{community}_{datetime.now().strftime('%Y%m%d')}"
            pdf_b64 = generate_report_pdf(summary_text, title)
            
            pdf_filename = f"{title}.pdf"
            pdf_path = os.path.join(ALERTS_DIR, pdf_filename)
            pdf_bytes = base64.b64decode(pdf_b64)
            
            with open(pdf_path, "wb") as f:
                f.write(pdf_bytes)
            
            logger.info(f"  Resumen generado: {pdf_path}")
            
        except Exception as e:
            logger.error(f"  Error procesando {community}: {str(e)}")


def critical_monitor_job():
    logger.info(f"[{datetime.now().isoformat()}] Iniciando critical_monitor_job")
    
    communities = get_communities_list()
    llm = get_llm()
    
    critical_keywords = [
        r"\b(odio|insulto|acoso|amenaza|spam|malware|virus)\b",
        r"\b(crisis|urgente|peligro)\b",
        r"\b(error|fallo|bug|caído|congelado|lento|crash)\b",
        r"\b(red|conexión|wifi|internet|servidor|timeout|desconectado)\b",
        r"\b(acceso|login|contraseña|bloqueado|no funciona|no carga|entrar|credenciales)\b",
        r"\b(accesibilidad|lector|pantalla|subtítulos|no veo|no escucho)\b",
        r"\b(queja|inaceptable|decepción|harto|problema|soporte|ayuda|injusto)\b"
    ]
    
    for community in communities:
        try:
            messages = get_last_days_messages(days=1, community=community)
            
            if not messages:
                continue
            
            critical_issues = []
            for msg in messages:
                text = f"{msg.get('topic', '')} {msg.get('text', '')}".lower()
                for pattern in critical_keywords:
                    if re.search(pattern, text):
                        critical_issues.append(msg)
                        break
            
            if critical_issues:
                critical_text = "\n".join([
                    f"- [{msg['author']}] {msg['topic']}: {msg['text'][:300]}"
                    for msg in critical_issues[:10]
                ])
                
                evaluation_prompt = f"""Analiza si el siguiente contenido requiere accion inmediata por parte de los administradores.
Clasifica basandote en este criterio:
- CRITICA: Caida total del sistema, brechas de seguridad, acoso grave o emergencias.
- ALTA: Usuarios bloqueados sin acceso, fallos de red recurrentes, quejas formales graves.
- MEDIA: Dudas de soporte tecnico estandar, quejas menores o sugerencias.
- BAJA: Conversacion normal o falsos positivos.

Responde SOLO con una palabra: CRITICA, ALTA, MEDIA o BAJA.

Contenido:
{critical_text}"""
                
                severity_response = llm.invoke([HumanMessage(content=evaluation_prompt)])
                severity = severity_response.content.strip().upper()
                
                if severity in ["CRITICA", "ALTA"]:
                    issue_summary = "\n".join([
                        f"{msg['author']} - {msg['topic']}: {msg['text'][:250]}"
                        for msg in critical_issues[:5]
                    ])
                    
                    pdf_b64 = generate_critical_alert_pdf(
                        community=community,
                        issue_summary=issue_summary,
                        severity=severity
                    )
                    
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    safe_community = re.sub(r"[^\w]", "", community)
                    alert_filename = f"ALERTA_{safe_community}_{timestamp}.pdf"
                    alert_path = os.path.join(ALERTS_DIR, alert_filename)
                    
                    pdf_bytes = base64.b64decode(pdf_b64)
                    with open(alert_path, "wb") as f:
                        f.write(pdf_bytes)

                    logger.info(f"  ALERTA [{severity}] generada: {alert_path}")

        except Exception as e:
            logger.error(f"  Error en critical_monitor para {community}: {str(e)}")


def start_scheduler():
    scheduler = BlockingScheduler()
    
    scheduler.add_job(
        weekly_summary_job,
        CronTrigger(day_of_week='fri', hour=18, minute=0),
        id='weekly_summary_job',
        name='Weekly Summary Job'
    )
    
    scheduler.add_job(
        critical_monitor_job,
        IntervalTrigger(minutes=30),
        id='critical_monitor_job',
        name='Critical Monitor Job'
    )
    
    try:
        scheduler.start()
    except KeyboardInterrupt:
        logger.info("Deteniendo scheduler...")
        scheduler.shutdown()


if __name__ == "__main__":
    start_scheduler()
