import os
import re
from collections import defaultdict
from typing import Optional

from dotenv import load_dotenv
from neo4j import GraphDatabase
from langchain_core.tools import tool
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.prebuilt import create_react_agent

from scripts.utils import add_months, format_month_year_es, get_reporting_periods, apply_current_report_dates, is_noise_record, to_date_key
from src.llm_config import get_llm
from src.tools import generate_report_pdf

load_dotenv()

NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

@tool
def get_monthly_directive_report(community: str = "todas") -> str:
    """Genera un reporte directivo mensual estricto con KPIs y métricas cuantitativas de una comunidad."""
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        with driver.session() as session:
            if community and community != "todas":
                query = """
                MATCH (a:Author)-[:WROTE]->(p:Post)-[:IN_DISCUSSION]->(d:Discussion)-[:PERTAINS_TO]->(c:Community)
                WHERE c.name = $community
                RETURN a.name AS author, p.content AS text, p.date AS date, d.topic AS topic, c.name AS community
                ORDER BY p.date DESC LIMIT 800
                """
                rows = [r.data() for r in session.run(query, community=community)]
            else:
                query = """
                MATCH (a:Author)-[:WROTE]->(p:Post)-[:IN_DISCUSSION]->(d:Discussion)-[:PERTAINS_TO]->(c:Community)
                RETURN a.name AS author, p.content AS text, p.date AS date, d.topic AS topic, c.name AS community
                ORDER BY p.date DESC LIMIT 800
                """
                rows = [r.data() for r in session.run(query)]
    finally:
        driver.close()

    cleaned = []
    for row in rows:
        topic = str(row.get("topic") or "sin tema").strip()
        text = str(row.get("text") or "").strip()
        if is_noise_record(topic, text):
            continue
        cleaned.append({
            "author": str(row.get("author") or "Anonimo").strip(),
            "topic": topic,
            "text": text,
            "date": row.get("date"),
            "community": str(row.get("community") or "general").strip(),
        })

    if not cleaned:
        return "No hay datos suficientes para construir KPIs confiables en este periodo."

    month_counter = defaultdict(int)
    topic_counter = defaultdict(int)
    community_counter = defaultdict(int)
    unique_authors = set()

    for row in cleaned:
        month_counter[to_date_key(row.get("date"))] += 1
        topic_counter[row["topic"]] += 1
        community_counter[row["community"]] += 1
        unique_authors.add(row["author"])

    ordered_months = sorted(month_counter.keys())
    active_month = ordered_months[-1] if ordered_months else "sin-fecha"
    previous_month = ordered_months[-2] if len(ordered_months) > 1 else None
    active_count = month_counter.get(active_month, 0)
    previous_count = month_counter.get(previous_month, 0) if previous_month else 0
    delta = active_count - previous_count
    delta_pct = (delta / previous_count * 100.0) if previous_count > 0 else 0.0

    top_topics = sorted(topic_counter.items(), key=lambda item: item[1], reverse=True)[:5]
    
    report_month_label, generation_month_label, next_review_month_label = get_reporting_periods()

    report = [
        f"Comunidad objetivo: {community}",
        f"Mes de referencia: {report_month_label}",
        f"Fecha de generación: {generation_month_label}",
        f"Próxima revisión: {next_review_month_label}",
        f"Último mes con datos: {active_month}",
        f"Publicaciones válidas analizadas: {len(cleaned)}",
        f"Autores únicos: {len(unique_authors)}",
        f"Publicaciones mes activo: {active_count}",
        f"Variación vs mes anterior: {delta:+d} ({delta_pct:+.1f}%)" if previous_month else "Variación: N/D",
        "Top Hilos:"
    ]
    for t, c in top_topics:
        report.append(f"- {t}: {c} posts")

    return "\n".join(report)

@tool
def get_forum_context(community: str = "todas", limit: int = 50) -> str:
    """Extrae los mensajes recientes de los foros para resumir temas o responder preguntas específicas de los usuarios."""
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        with driver.session() as session:
            if community and community != "todas":
                query = """
                MATCH (a:Author)-[:WROTE]->(p:Post)-[:IN_DISCUSSION]->(d:Discussion)-[:PERTAINS_TO]->(c:Community)
                WHERE c.name = $community
                RETURN a.name AS author, p.content AS text, d.topic AS subject
                ORDER BY p.date DESC LIMIT $limit
                """
                results = session.run(query, community=community, limit=limit)
            else:
                query = """
                MATCH (a:Author)-[:WROTE]->(p:Post)-[:IN_DISCUSSION]->(d:Discussion)-[:PERTAINS_TO]->(c:Community)
                RETURN a.name AS author, p.content AS text, d.topic AS subject
                ORDER BY p.date DESC LIMIT $limit
                """
                results = session.run(query, limit=limit)

            records = [record.data() for record in results]
    finally:
        driver.close()

    filtered = []
    for rec in records:
        topic = str(rec.get("subject") or "sin tema").strip()
        text = str(rec.get("text") or "").strip()
        author = str(rec.get("author") or "Anonimo").strip()
        if not is_noise_record(topic, text):
            short_text = (text[:250] + "...") if len(text) > 250 else text
            filtered.append(f"Hilo: {topic} | Autor: {author} | Msg: {short_text}")

    if not filtered:
        return "No hay datos recientes en esta comunidad."
    
    return "\n".join(filtered)

tools = [get_monthly_directive_report, get_forum_context]
llm = get_llm()

system_message = SystemMessage(content=(
    "Eres el Auditor IA de ProFuturo.\n"
    "REGLAS OBLIGATORIAS:\n"
    "1. Antes de responder cualquier consulta, debes invocar al menos una herramienta de Neo4j.\n"
    "2. Nunca inventes datos, métricas, nombres, fechas ni conclusiones.\n"
    "3. Todas las respuestas y reportes deben basarse exclusivamente en el contexto devuelto por las herramientas.\n"
    "4. Si el usuario pide métricas o informe directivo, usa get_monthly_directive_report.\n"
    "5. Si el usuario pide resumen, temas o preguntas específicas, usa get_forum_context.\n"
    "6. Si no hay datos suficientes en herramientas, indícalo explícitamente y no completes con suposiciones.\n"
    "7. Responde siempre en Markdown estructurado (##, -, **).\n"
    "8. Si el usuario solicita generar un reporte, informe o PDF para descargar, incluye exactamente al final la etiqueta: "
    "[GENERATE_PDF: Titulo_Del_Documento]"
))

agent_executor = create_react_agent(llm, tools, prompt=system_message)

def run_agent(input_text: str, community: str = "todas") -> dict:
    if not input_text.strip():
        return {"response": "Por favor, ingresa una consulta.", "pdf_base64": None, "pdf_filename": ""}

    inputs = {"messages": [HumanMessage(content=f"Comunidad: {community}. Consulta: {input_text}")]}
    
    result = agent_executor.invoke(inputs)
    final_response = result["messages"][-1].content

    pdf_match = re.search(r"\[GENERATE_PDF:\s*([^\]]+)\]", final_response)
    pdf_base64 = None
    pdf_filename = ""

    if pdf_match:
        title = pdf_match.group(1).strip()
        final_response = final_response[:pdf_match.start()].rstrip()

        final_response = apply_current_report_dates(final_response)
        
        pdf_ready_text = final_response.encode("latin-1", "ignore").decode("latin-1")
        pdf_base64 = generate_report_pdf(pdf_ready_text, title)
        
        safe_title = re.sub(r"[^\w\s-]", "", title).strip().replace(" ", "_")[:60]
        pdf_filename = f"{safe_title}.pdf" if safe_title else "reporte.pdf"
        final_response += f"\n\n[PDF generado: {pdf_filename}]"

    final_response = apply_current_report_dates(final_response)

    return {
        "response": final_response,
        "pdf_base64": pdf_base64,
        "pdf_filename": pdf_filename
    }