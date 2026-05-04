import logging
import os
import re
from collections import defaultdict
from datetime import datetime, timedelta

from dotenv import load_dotenv
from langchain.memory import ConversationBufferMemory
from langchain_core.prompts import PromptTemplate
from langchain_core.messages import HumanMessage, AIMessage
from neo4j import GraphDatabase

logger = logging.getLogger(__name__)

from scripts.utils import get_reporting_periods, apply_current_report_dates, is_noise_record, to_date_key
from src.llm_config import get_profuturo_llm
from src.tools import generate_report_pdf

load_dotenv()

NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

# Tokens del modelo: 6144 limit. Presupuesto actualizado — contexto siempre obligatorio:
# - System prompt (instrucciones fijas): ~500 tokens
# - Contexto Neo4j obligatorio (KPIs + ranking + tendencias): ~900 tokens
# - Contexto foro (posts recientes + búsqueda): ~500 tokens
# - Historial (3 pares): ~600 tokens
# - Input usuario: ~150 tokens
# Total estimado: ~2650 tokens → ~3494 tokens disponibles para la respuesta
MAX_CONTEXT_CHARS = 6000
MAX_HISTORY_PAIRS = 3

_SEARCH_STOP = {
    "que", "los", "las", "del", "por", "con", "una", "uno", "son", "hay",
    "dijo", "dice", "dices", "habla", "hablan", "temas", "tema", "muestra",
    "como", "cual", "tiene", "tienen", "este", "esta", "estos", "estas",
    "para", "pero", "todo", "todos", "todas", "cada", "foro", "chat", "hilo",
    "mensaje", "mensajes", "comunidad", "escribe", "escrito", "publica",
    "genera", "dame", "dime", "hazme", "numero", "cuando", "donde", "porque",
    "aunque", "sobre", "desde", "hasta", "entre", "alguno", "algunas",
    "alguien", "usuarios", "usuario", "participantes", "participante",
    "miembro", "miembros", "datos", "informacion", "resumen", "reporte",
    "ranking", "muéstrame", "muestrame", "cuantos", "cuantas", "cuales",
}

REPORT_HINTS = re.compile(
    r"\b(reporte|resumen|informe|pdf|kpi|kpis|m[eé]trica|m[eé]tricas|estad[ií]stica|estad[ií]sticas|an[aá]lisis)\b",
    re.IGNORECASE,
)

EXCEL_HINTS = re.compile(
    r"\b(excel|hoja\s+de\s+c[aá]lculo|xlsx|exporta?\s+(?:a\s+)?excel|descarga\s+(?:en\s+)?excel|tabla\s+descargable)\b",
    re.IGNORECASE,
)

RUBRIC_HINTS = re.compile(
    r"\b("
    r"eval[uú]a\s+(las?\s+)?contribuciones?"
    r"|evaluaci[oó]n\s+pedag[oó]gica"
    r"|r[uú]brica\s+(?:pedag[oó]gica|de\s+evaluaci[oó]n|de\s+contribuciones?)"
    r"|calidad\s+de\s+(las?\s+)?contribuciones?"
    r"|mejor\s+contribuidor"
    r"|perfil\s+de\s+autor"
    r"|qui[eé]n\s+contribuye\s+mejor"
    r")\b",
    re.IGNORECASE,
)

RUBRIC_PROMPT = """Eres un evaluador pedagógico de ProFuturo. Analiza las contribuciones de estos miembros del foro '{community}' según la siguiente rúbrica (escala 1-10):
- PERTINENCIA: relevancia educativa y adecuación al tema de la comunidad
- APORTE_PEDAGOGICO: valor pedagógico, recursos o conocimiento útil aportado
- ARGUMENTACION: calidad de la argumentación y fundamento de las ideas
- APOYO_EMOCIONAL: empatía, motivación y apoyo a otros miembros

Contribuciones a evaluar:
{posts}

Para CADA AUTOR, responde EXACTAMENTE en este formato (sin texto adicional):
---
AUTOR: [nombre]
PERTINENCIA: X | APORTE_PEDAGOGICO: X | ARGUMENTACION: X | APOYO_EMOCIONAL: X
PUNTUACION_FINAL: X.X | CATEGORIA: [Lider/Experto/Conector/Participante]
FORTALEZAS: [frase breve]
AREAS_MEJORA: [frase breve]"""

try:
    from langdetect import detect as _langdetect_fn
    _LANGDETECT_OK = True
except ImportError:
    _LANGDETECT_OK = False

MEMBER_HINTS = re.compile(
    r"\b(miembro|miembros|activo|activos|l[ií]der|l[ií]deres|experto|expertos|conector|conectores|"
    r"riesgo|abandono|destacado|destacados|crecimiento|participaci[oó]n|porcentaje|evaluaci[oó]n|"
    r"perfil|perfiles|rol|roles|contribuci[oó]n|contribuciones)\b",
    re.IGNORECASE,
)
AUDIT_HINTS = re.compile(
    r"\b(auditor[ií]a|clima|sentimiento|an[aá]lisis\s+completo|diagn[oó]stico|estado\s+de)\b",
    re.IGNORECASE,
)
RANKING_HINTS = re.compile(
    r"\b(ranking|top\s+\d+|m[aá]s\s+activos?|mayor\s+contribu|participaci[oó]n\s+usuario)\b",
    re.IGNORECASE,
)
ENGAGEMENT_HINTS = re.compile(
    r"\b(engagement|tasa\s+de\s+respuesta|hilos?\s+activos?|interacci[oó]n|actividad\s+general|discusiones?\s+activas?)\b",
    re.IGNORECASE,
)
TRENDING_HINTS = re.compile(
    r"\b(tendencias?|trending|temas?\s+del\s+momento|m[aá]s\s+debatidos?|tema\s+creciendo)\b",
    re.IGNORECASE,
)

_conversation_memories: dict[str, ConversationBufferMemory] = {}
_profuturo_llm = None
_neo4j_driver = None


def _get_llm():
    global _profuturo_llm
    if _profuturo_llm is None:
        _profuturo_llm = get_profuturo_llm()
    return _profuturo_llm


def _get_driver():
    global _neo4j_driver
    if _neo4j_driver is None:
        _neo4j_driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    return _neo4j_driver


def _get_memory(community: str) -> ConversationBufferMemory:
    memory = _conversation_memories.get(community)
    if memory is None:
        memory = ConversationBufferMemory(
            memory_key="history",
            input_key="input",
            return_messages=True,
        )
        _conversation_memories[community] = memory
    return memory


def _trim_history(memory: ConversationBufferMemory) -> None:
    """Mantiene solo los últimos MAX_HISTORY_PAIRS pares de mensajes para no exceder el límite de tokens."""
    messages = memory.chat_memory.messages
    max_msgs = MAX_HISTORY_PAIRS * 2
    if len(messages) > max_msgs:
        memory.chat_memory.messages = messages[-max_msgs:]


def _format_client_history(history: list[dict]) -> str:
    """Convierte el historial del frontend a ChatML para inyectar en el prompt."""
    blocks: list[str] = []
    for msg in history[-6:]:
        role = msg.get("role", "")
        content = str(msg.get("content", "")).strip()
        content = re.sub(r"\*\*PDF generado:.*", "", content).strip()
        content = re.sub(r"\[?GENERATE_PDF:[^\]\n]+\]?", "", content).strip()
        if not content or len(content) < 5:
            continue
        if role == "user":
            blocks.append(f"<|im_start|>user\n{content}<|im_end|>")
        elif role == "ai":
            blocks.append(f"<|im_start|>assistant\n{content}<|im_end|>")
    return "\n".join(blocks) + ("\n" if blocks else "")


_PDF_OF_PREV_RE = re.compile(
    r"pdf\b.{0,50}\b(anterior|que\s+me\s+(d(?:ij|ist)|acab|gen)|lo\s+que|de\s+eso|que\s+me\s+acabas)"
    r"|(?:lo|eso)\s+quiero\s+descargar"
    r"|ponm[eo]lo?\s+en\s+pdf"
    r"|\bgenera\s+(el|un|ese)\s+pdf\b(?!.{10,}(sobre|de\s+la\s+comunidad|del\s+mes|audit|ranking|reporte))",
    re.IGNORECASE,
)


def _last_ai_content(history: list[dict]) -> str:
    """Extrae el ultimo mensaje sustancial del agente del historial del cliente."""
    for msg in reversed(history):
        if msg.get("role") == "ai":
            content = str(msg.get("content", "")).strip()
            content = re.sub(r"\*\*PDF generado:.*", "", content).strip()
            content = re.sub(r"\[?GENERATE_PDF:[^\]\n]+\]?", "", content).strip()
            if len(content) > 200:
                return content
    return ""


def _history_to_chatml(memory: ConversationBufferMemory) -> str:
    blocks: list[str] = []
    for msg in memory.chat_memory.messages:
        content = str(msg.content).strip()
        if isinstance(msg, HumanMessage):
            if content.startswith("<|im_start|>user"):
                blocks.append(content)
            else:
                blocks.append(f"<|im_start|>user\n{content}<|im_end|>")
        elif isinstance(msg, AIMessage):
            if content.startswith("<|im_start|>assistant"):
                blocks.append(content)
            else:
                blocks.append(f"<|im_start|>assistant\n{content}<|im_end|>")
    return "\n".join(blocks) + ("\n" if blocks else "")


def get_monthly_directive_report(community: str = "todas") -> str:
    """
    Genera KPIs cuantitativos mensuales consultando Neo4j directamente.

    🔍 FUENTE DE DATOS: Neo4j Graph Database (consulta directa, últimos 800 posts)
    ⚠️ NO usa datos visuales ni HTML

    CUÁNDO USARME:
    - Usuario pregunta: "Dame el reporte mensual" / "Estadísticas del último mes"
    - Keywords: reporte, resumen, informe, KPIs, métricas, estadísticas, análisis

    RETORNA:
    Comunidad objetivo, fechas de referencia, publicaciones válidas analizadas,
    autores únicos, actividad mensual, variación vs mes anterior, top 5 hilos.

    EJEMPLO:
    Input: get_monthly_directive_report("Red de Líderes")
    Output: "Publicaciones validas analizadas: 312, Autores unicos: 45, Top Hilos: ..."
    """
    driver = _get_driver()
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
        return "Sin datos suficientes para KPIs."

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

    lines = [
        f"Comunidad objetivo: {community}",
        f"Mes de referencia: {report_month_label}",
        f"Fecha de generacion: {generation_month_label}",
        f"Proxima revision: {next_review_month_label}",
        f"Ultimo mes con datos: {active_month}",
        f"Publicaciones validas analizadas: {len(cleaned)}",
        f"Autores unicos: {len(unique_authors)}",
        f"Publicaciones mes activo: {active_count}",
        f"Variacion vs mes anterior: {delta:+d} ({delta_pct:+.1f}%)" if previous_month else "Variacion: N/D",
        "Top Hilos:",
    ]
    for t, c in top_topics:
        lines.append(f"- {t}: {c} posts")

    return "\n".join(lines)


def get_community_kpis(community: str = "todas") -> str:
    """
    KPIs de comunidad: % activos, crecimiento y roles (líderes, expertos, conectores).

    🔍 FUENTE DE DATOS: Neo4j Graph Database (consulta directa)
    ⚠️ NO usa datos visuales ni HTML

    CUÁNDO USARME:
    - Usuario pregunta: "¿Cuántos usuarios activos hay?" / "¿Quiénes son los líderes?"
    - Keywords: miembros, activos, líderes, expertos, conectores, roles, participación

    RETORNA:
    Total miembros, % activos últimos 30 días, variación mensual,
    top 3 líderes (más posts), conectores (más discusiones), expertos (contenido más largo).

    EJEMPLO:
    Input: get_community_kpis("Red de Líderes")
    Output: "Total miembros: 45, % miembros activos (30 dias): 23/45 (51.1%), Lideres: María (12), ..."
    """
    cutoff_30 = (datetime.now() - timedelta(days=30)).date()
    cutoff_60 = (datetime.now() - timedelta(days=60)).date()
    driver = _get_driver()
    has_comm = bool(community and community != "todas")

    with driver.session() as session:
        if has_comm:
            total = (session.run("""
                MATCH (a:Author)-[:WROTE]->(:Post)-[:IN_DISCUSSION]->(:Discussion)-[:PERTAINS_TO]->(c:Community)
                WHERE c.name = $community RETURN count(DISTINCT a) AS n
            """, community=community).single() or {"n": 0})["n"]

            active_30 = (session.run("""
                MATCH (a:Author)-[:WROTE]->(p:Post)-[:IN_DISCUSSION]->(:Discussion)-[:PERTAINS_TO]->(c:Community)
                WHERE c.name = $community AND p.date >= $cutoff
                RETURN count(DISTINCT a) AS n
            """, community=community, cutoff=cutoff_30).single() or {"n": 0})["n"]

            active_prev = (session.run("""
                MATCH (a:Author)-[:WROTE]->(p:Post)-[:IN_DISCUSSION]->(:Discussion)-[:PERTAINS_TO]->(c:Community)
                WHERE c.name = $community AND p.date >= $cutoff_60 AND p.date < $cutoff_30
                RETURN count(DISTINCT a) AS n
            """, community=community, cutoff_60=cutoff_60, cutoff_30=cutoff_30).single() or {"n": 0})["n"]

            leaders = session.run("""
                MATCH (a:Author)-[:WROTE]->(p:Post)-[:IN_DISCUSSION]->(:Discussion)-[:PERTAINS_TO]->(c:Community)
                WHERE c.name = $community
                RETURN a.name AS name, count(p) AS posts ORDER BY posts DESC LIMIT 3
            """, community=community).data()

            connectors = session.run("""
                MATCH (a:Author)-[:WROTE]->(:Post)-[:IN_DISCUSSION]->(d:Discussion)-[:PERTAINS_TO]->(c:Community)
                WHERE c.name = $community
                RETURN a.name AS name, count(DISTINCT d) AS discussions ORDER BY discussions DESC LIMIT 3
            """, community=community).data()

            experts = session.run("""
                MATCH (a:Author)-[:WROTE]->(p:Post)-[:IN_DISCUSSION]->(:Discussion)-[:PERTAINS_TO]->(c:Community)
                WHERE c.name = $community
                RETURN a.name AS name, avg(size(p.content)) AS avg_len ORDER BY avg_len DESC LIMIT 3
            """, community=community).data()
        else:
            total = (session.run("""
                MATCH (a:Author)-[:WROTE]->(:Post)-[:IN_DISCUSSION]->(:Discussion)-[:PERTAINS_TO]->(:Community)
                RETURN count(DISTINCT a) AS n
            """).single() or {"n": 0})["n"]

            active_30 = (session.run("""
                MATCH (a:Author)-[:WROTE]->(p:Post)-[:IN_DISCUSSION]->(:Discussion)-[:PERTAINS_TO]->(:Community)
                WHERE p.date >= $cutoff RETURN count(DISTINCT a) AS n
            """, cutoff=cutoff_30).single() or {"n": 0})["n"]

            active_prev = (session.run("""
                MATCH (a:Author)-[:WROTE]->(p:Post)-[:IN_DISCUSSION]->(:Discussion)-[:PERTAINS_TO]->(:Community)
                WHERE p.date >= $cutoff_60 AND p.date < $cutoff_30
                RETURN count(DISTINCT a) AS n
            """, cutoff_60=cutoff_60, cutoff_30=cutoff_30).single() or {"n": 0})["n"]

            leaders = session.run("""
                MATCH (a:Author)-[:WROTE]->(p:Post)-[:IN_DISCUSSION]->(:Discussion)-[:PERTAINS_TO]->(:Community)
                RETURN a.name AS name, count(p) AS posts ORDER BY posts DESC LIMIT 3
            """).data()

            connectors = session.run("""
                MATCH (a:Author)-[:WROTE]->(:Post)-[:IN_DISCUSSION]->(d:Discussion)-[:PERTAINS_TO]->(:Community)
                RETURN a.name AS name, count(DISTINCT d) AS discussions ORDER BY discussions DESC LIMIT 3
            """).data()

            experts = session.run("""
                MATCH (a:Author)-[:WROTE]->(p:Post)-[:IN_DISCUSSION]->(:Discussion)-[:PERTAINS_TO]->(:Community)
                RETURN a.name AS name, avg(size(p.content)) AS avg_len ORDER BY avg_len DESC LIMIT 3
            """).data()

    pct = (active_30 / total * 100) if total > 0 else 0
    growth = active_30 - active_prev
    growth_pct = (growth / active_prev * 100) if active_prev > 0 else 0

    lines = [
        f"Total miembros: {total}",
        f"% miembros activos (30 dias): {active_30}/{total} ({pct:.1f}%)",
        f"Actividad mes anterior: {active_prev} activos",
        f"Variacion mensual: {growth:+d} ({growth_pct:+.1f}%)",
    ]
    if leaders:
        lines.append("Lideres (mas publicaciones): " + ", ".join(
            f"{r['name']} ({r['posts']})" for r in leaders
        ))
    if connectors:
        lines.append("Conectores (mas discusiones activas): " + ", ".join(
            f"{r['name']} ({r['discussions']})" for r in connectors
        ))
    if experts:
        lines.append("Expertos (contenido mas elaborado): " + ", ".join(
            f"{r['name']} ({int(r.get('avg_len') or 0)} chars/msg)" for r in experts
        ))
    return "\n".join(lines)


def generate_climate_audit(community: str) -> str:
    """
    Auditoría completa del clima de una comunidad educativa ProFuturo.

    🔍 FUENTE DE DATOS: Neo4j Graph Database (consulta directa)
    ⚠️ NO usa datos visuales ni HTML

    CUÁNDO USARME:
    - Usuario pregunta: "Genera una auditoría de clima completa"
    - Usuario pregunta: "¿Cuál es el estado general de la comunidad?"
    - Keywords: auditoría, clima, diagnóstico, análisis completo, estado de

    RETORNA:
    Total posts/autores, % activos, discusiones activas, sentimiento estimado
    por palabras clave, top 5 autores y top 5 temas más activos.

    EJEMPLO:
    Input: generate_climate_audit("Red de Líderes")
    Output: "Total publicaciones: 312, Sentimiento: Positivo, Top autores: María (45)..."
    """
    driver = _get_driver()
    has_comm = bool(community and community != "todas")
    cp  = {"community": community} if has_comm else {}
    cw  = "WHERE c.name = $community" if has_comm else ""
    cwa = "WHERE c.name = $community AND" if has_comm else "WHERE"
    cutoff_30 = (datetime.now() - timedelta(days=30)).date()

    with driver.session() as session:
        total_posts = (session.run(
            f"MATCH (:Author)-[:WROTE]->(p:Post)-[:IN_DISCUSSION]->(:Discussion)-[:PERTAINS_TO]->(c:Community) "
            f"{cw} RETURN count(p) AS n", **cp
        ).single() or {"n": 0})["n"]

        total_authors = (session.run(
            f"MATCH (a:Author)-[:WROTE]->(:Post)-[:IN_DISCUSSION]->(:Discussion)-[:PERTAINS_TO]->(c:Community) "
            f"{cw} RETURN count(DISTINCT a) AS n", **cp
        ).single() or {"n": 0})["n"]

        active_30 = (session.run(
            f"MATCH (a:Author)-[:WROTE]->(p:Post)-[:IN_DISCUSSION]->(:Discussion)-[:PERTAINS_TO]->(c:Community) "
            f"{cwa} p.date >= $cutoff RETURN count(DISTINCT a) AS n",
            **{**cp, "cutoff": cutoff_30}
        ).single() or {"n": 0})["n"]

        top_authors = session.run(
            f"MATCH (a:Author)-[:WROTE]->(p:Post)-[:IN_DISCUSSION]->(:Discussion)-[:PERTAINS_TO]->(c:Community) "
            f"{cw} RETURN a.name AS name, count(p) AS posts ORDER BY posts DESC LIMIT 5", **cp
        ).data()

        top_topics = session.run(
            f"MATCH (:Author)-[:WROTE]->(p:Post)-[:IN_DISCUSSION]->(d:Discussion)-[:PERTAINS_TO]->(c:Community) "
            f"{cw} RETURN d.topic AS topic, count(p) AS posts ORDER BY posts DESC LIMIT 5", **cp
        ).data()

        active_discussions = (session.run(
            f"MATCH (:Author)-[:WROTE]->(p:Post)-[:IN_DISCUSSION]->(d:Discussion)-[:PERTAINS_TO]->(c:Community) "
            f"{cw} WITH d, count(p) AS cnt WHERE cnt > 1 RETURN count(d) AS n", **cp
        ).single() or {"n": 0})["n"]

        positive_count = (session.run(
            f"MATCH (:Author)-[:WROTE]->(p:Post)-[:IN_DISCUSSION]->(:Discussion)-[:PERTAINS_TO]->(c:Community) "
            f"{cwa} (toLower(p.content) CONTAINS 'gracias' OR toLower(p.content) CONTAINS 'excelente' "
            f"OR toLower(p.content) CONTAINS 'genial' OR toLower(p.content) CONTAINS 'aprendí') "
            f"RETURN count(p) AS n", **cp
        ).single() or {"n": 0})["n"]

        negative_count = (session.run(
            f"MATCH (:Author)-[:WROTE]->(p:Post)-[:IN_DISCUSSION]->(:Discussion)-[:PERTAINS_TO]->(c:Community) "
            f"{cwa} (toLower(p.content) CONTAINS 'problema' OR toLower(p.content) CONTAINS 'error' "
            f"OR toLower(p.content) CONTAINS 'no funciona' OR toLower(p.content) CONTAINS 'difícil') "
            f"RETURN count(p) AS n", **cp
        ).single() or {"n": 0})["n"]

    sentiment = "Positivo" if positive_count > negative_count * 1.5 else (
        "Negativo" if negative_count > positive_count * 1.5 else "Neutro/Mixto"
    )
    pct_active = round(active_30 / total_authors * 100, 1) if total_authors > 0 else 0

    lines = [
        f"=== AUDITORÍA DE CLIMA — {community} ===",
        f"Total publicaciones: {total_posts}",
        f"Total autores únicos: {total_authors}",
        f"Autores activos (últimos 30 días): {active_30} ({pct_active}%)",
        f"Discusiones activas (>1 post): {active_discussions}",
        f"Sentimiento estimado: {sentiment} (indicadores positivos={positive_count}, negativos={negative_count})",
        "",
        "TOP 5 AUTORES POR PUBLICACIONES:",
    ]
    for i, r in enumerate(top_authors, 1):
        lines.append(f"  {i}. {r['name']}: {r['posts']} posts")
    lines.append("\nTOP 5 TEMAS MÁS ACTIVOS:")
    for i, r in enumerate(top_topics, 1):
        lines.append(f"  {i}. {r['topic']}: {r['posts']} posts")
    return "\n".join(lines)


def get_user_ranking(community: str, limit: int = 10) -> str:
    """
    Ranking de usuarios ordenado por número de publicaciones (consulta Neo4j directa).

    🔍 FUENTE DE DATOS: Neo4j Graph Database (consulta directa)
    ⚠️ NO usa datos visuales ni HTML

    CUÁNDO USARME:
    - Usuario pregunta: "Dame el ranking de usuarios por participación"
    - Usuario pregunta: "¿Quiénes son los más activos?" / "Top 10 usuarios"
    - Keywords: ranking, top, más activos, mayor contribución, participación usuarios

    RETORNA:
    Lista numerada con nombre, número de publicaciones y discusiones,
    ordenada de mayor a menor. Medallas para el top 3.

    EJEMPLO:
    Input: get_user_ranking("Red de Líderes", limit=5)
    Output: "🥇 María García: 45 publicaciones, 12 discusiones\\n🥈 Juan Pérez: 32 ..."
    """
    driver = _get_driver()
    has_comm = bool(community and community != "todas")
    cp = {"community": community} if has_comm else {}
    cw = "WHERE c.name = $community" if has_comm else ""

    with driver.session() as session:
        query = (
            f"MATCH (a:Author)-[:WROTE]->(p:Post)-[:IN_DISCUSSION]->(d:Discussion)-[:PERTAINS_TO]->(c:Community) "
            f"{cw} "
            f"RETURN a.name AS name, count(p) AS posts, count(DISTINCT d) AS discussions "
            f"ORDER BY posts DESC LIMIT {limit}"
        )
        rows = session.run(query, **cp).data()

    if not rows:
        return f"No hay datos de usuarios para la comunidad '{community}'."

    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    lines = [f"RANKING TOP {limit} USUARIOS — {community}"]
    for i, r in enumerate(rows, 1):
        pos = medals.get(i, f"{i}.")
        lines.append(f"  {pos} {r['name']}: {r['posts']} publicaciones, {r['discussions']} discusiones")
    return "\n".join(lines)


def get_all_posts(community: str, limit: int = 100) -> str:
    """
    Obtiene publicaciones reales de Neo4j con contenido completo para análisis de texto.

    🔍 FUENTE DE DATOS: Neo4j Graph Database (consulta directa)
    ⚠️ NO usa datos visuales ni HTML

    CUÁNDO USARME:
    - Se necesita analizar el contenido textual de los posts
    - El agente necesita contexto completo de publicaciones recientes

    RETORNA:
    Lista de publicaciones "[Tema] Autor: contenido" (hasta 400 chars por post),
    ordenadas por fecha descendente.

    EJEMPLO:
    Input: get_all_posts("Red de Líderes", limit=20)
    Output: "[Metodologías] María: He probado el aprendizaje por proyectos...\\n..."
    """
    driver = _get_driver()
    has_comm = bool(community and community != "todas")
    cp = {"community": community} if has_comm else {}
    cw = "WHERE c.name = $community" if has_comm else ""

    with driver.session() as session:
        query = (
            f"MATCH (a:Author)-[:WROTE]->(p:Post)-[:IN_DISCUSSION]->(d:Discussion)-[:PERTAINS_TO]->(c:Community) "
            f"{cw} "
            f"RETURN a.name AS author, d.topic AS topic, p.content AS content, p.date AS date "
            f"ORDER BY p.date DESC LIMIT {limit}"
        )
        rows = session.run(query, **cp).data()

    if not rows:
        return f"No hay publicaciones para la comunidad '{community}'."

    lines = [f"PUBLICACIONES RECIENTES — {community} ({len(rows)} posts)"]
    for r in rows:
        content = str(r.get("content") or "").strip()
        if len(content) > 400:
            content = content[:400] + "..."
        topic  = str(r.get("topic")  or "sin tema")
        author = str(r.get("author") or "Anónimo")
        lines.append(f"[{topic}] {author}: {content}")
    return "\n".join(lines)


def analyze_engagement(community: str) -> str:
    """
    Analiza métricas de engagement: posts/usuario, discusiones activas, tasa de respuesta.

    🔍 FUENTE DE DATOS: Neo4j Graph Database (consulta directa)
    ⚠️ NO usa datos visuales ni HTML

    CUÁNDO USARME:
    - Usuario pregunta: "¿Cómo está el engagement de la comunidad?"
    - Usuario pregunta: "Tasa de respuesta en los hilos"
    - Keywords: engagement, tasa de respuesta, hilos activos, interacción, actividad general

    RETORNA:
    Promedio posts/autor, % discusiones con respuesta real, publicaciones últimos
    30 días, distribución de actividad (1 post / baja / media / alta).

    EJEMPLO:
    Input: analyze_engagement("Red de Líderes")
    Output: "Promedio posts por autor: 6.9, Discusiones con respuesta: 78%, ..."
    """
    driver = _get_driver()
    has_comm = bool(community and community != "todas")
    cp  = {"community": community} if has_comm else {}
    cw  = "WHERE c.name = $community" if has_comm else ""
    cwa = "WHERE c.name = $community AND" if has_comm else "WHERE"
    cutoff_30 = (datetime.now() - timedelta(days=30)).date()

    with driver.session() as session:
        total_stats = session.run(
            f"MATCH (a:Author)-[:WROTE]->(p:Post)-[:IN_DISCUSSION]->(:Discussion)-[:PERTAINS_TO]->(c:Community) "
            f"{cw} RETURN count(p) AS total_posts, count(DISTINCT a) AS total_authors", **cp
        ).single() or {"total_posts": 0, "total_authors": 0}

        disc_stats = session.run(
            f"MATCH (d:Discussion)-[:PERTAINS_TO]->(c:Community) "
            f"{'WHERE c.name = $community' if has_comm else ''} "
            f"OPTIONAL MATCH (a:Author)-[:WROTE]->(:Post)-[:IN_DISCUSSION]->(d) "
            f"WITH d, count(DISTINCT a) AS unique_authors "
            f"RETURN count(d) AS total_discussions, "
            f"sum(CASE WHEN unique_authors > 1 THEN 1 ELSE 0 END) AS discussions_with_response",
            **cp
        ).single() or {"total_discussions": 0, "discussions_with_response": 0}

        dist = session.run(
            f"MATCH (a:Author)-[:WROTE]->(p:Post)-[:IN_DISCUSSION]->(:Discussion)-[:PERTAINS_TO]->(c:Community) "
            f"{cw} WITH a, count(p) AS posts "
            f"RETURN "
            f"sum(CASE WHEN posts = 1 THEN 1 ELSE 0 END) AS single_post, "
            f"sum(CASE WHEN posts >= 2 AND posts <= 5 THEN 1 ELSE 0 END) AS low_active, "
            f"sum(CASE WHEN posts >= 6 AND posts <= 20 THEN 1 ELSE 0 END) AS medium_active, "
            f"sum(CASE WHEN posts > 20 THEN 1 ELSE 0 END) AS high_active",
            **cp
        ).single() or {"single_post": 0, "low_active": 0, "medium_active": 0, "high_active": 0}

        recent_posts = (session.run(
            f"MATCH (:Author)-[:WROTE]->(p:Post)-[:IN_DISCUSSION]->(:Discussion)-[:PERTAINS_TO]->(c:Community) "
            f"{cwa} p.date >= $cutoff RETURN count(p) AS n",
            **{**cp, "cutoff": cutoff_30}
        ).single() or {"n": 0})["n"]

    total_p = total_stats["total_posts"]  or 0
    total_a = total_stats["total_authors"] or 0
    total_d = disc_stats["total_discussions"] or 0
    resp_d  = disc_stats["discussions_with_response"] or 0

    avg_posts  = round(total_p / total_a, 1) if total_a > 0 else 0
    resp_rate  = round(resp_d / total_d * 100, 1) if total_d > 0 else 0
    recent_pct = round(recent_posts / total_p * 100, 1) if total_p > 0 else 0

    lines = [
        f"=== ANÁLISIS DE ENGAGEMENT — {community} ===",
        f"Total publicaciones: {total_p}",
        f"Total autores únicos: {total_a}",
        f"Promedio posts por autor: {avg_posts}",
        f"Total discusiones: {total_d}",
        f"Discusiones con respuesta (>1 autor): {resp_d} ({resp_rate}%)",
        f"Publicaciones últimos 30 días: {recent_posts} ({recent_pct}% del total)",
        "",
        "DISTRIBUCIÓN DE ACTIVIDAD:",
        f"  - Solo 1 post (riesgo abandono): {dist['single_post']} usuarios",
        f"  - 2-5 posts (participación baja): {dist['low_active']} usuarios",
        f"  - 6-20 posts (participación media): {dist['medium_active']} usuarios",
        f"  - >20 posts (participación alta): {dist['high_active']} usuarios",
    ]
    return "\n".join(lines)


def get_trending_topics(community: str, days: int = 7) -> str:
    """
    Temas con mayor crecimiento en el período reciente vs período anterior.

    🔍 FUENTE DE DATOS: Neo4j Graph Database (query temporal directa)
    ⚠️ NO usa datos visuales ni HTML

    CUÁNDO USARME:
    - Usuario pregunta: "¿Qué temas están de moda?" / "Tendencias de la semana"
    - Keywords: tendencias, trending, temas del momento, más debatidos, crecimiento

    RETORNA:
    Lista de temas con posts período actual vs anterior,
    % crecimiento y clasificación (↗ Creciendo / → Estable / ↘ Bajando).

    EJEMPLO:
    Input: get_trending_topics("Red de Líderes", days=7)
    Output: "1. Metodologías activas: 10 posts (+150% vs 4 prev) ↗ Creciendo..."
    """
    driver = _get_driver()
    has_comm = bool(community and community != "todas")
    cp  = {"community": community} if has_comm else {}
    cw  = "WHERE c.name = $community" if has_comm else ""
    cwa = "WHERE c.name = $community AND" if has_comm else "WHERE"
    cutoff_recent = (datetime.now() - timedelta(days=days)).date()
    cutoff_prev   = (datetime.now() - timedelta(days=days * 2)).date()

    with driver.session() as session:
        recent = session.run(
            f"MATCH (:Author)-[:WROTE]->(p:Post)-[:IN_DISCUSSION]->(d:Discussion)-[:PERTAINS_TO]->(c:Community) "
            f"{cwa} p.date >= $cutoff "
            f"RETURN d.topic AS topic, count(p) AS posts ORDER BY posts DESC LIMIT 20",
            **{**cp, "cutoff": cutoff_recent}
        ).data()

        prev = session.run(
            f"MATCH (:Author)-[:WROTE]->(p:Post)-[:IN_DISCUSSION]->(d:Discussion)-[:PERTAINS_TO]->(c:Community) "
            f"{cwa} p.date >= $cutoff_prev AND p.date < $cutoff_recent "
            f"RETURN d.topic AS topic, count(p) AS posts",
            **{**cp, "cutoff_prev": cutoff_prev, "cutoff_recent": cutoff_recent}
        ).data()

    prev_map = {r["topic"]: r["posts"] for r in prev}

    if not recent:
        with driver.session() as session:
            fallback = session.run(
                f"MATCH (:Author)-[:WROTE]->(p:Post)-[:IN_DISCUSSION]->(d:Discussion)-[:PERTAINS_TO]->(c:Community) "
                f"{cw} RETURN d.topic AS topic, count(p) AS posts ORDER BY posts DESC LIMIT 15", **cp
            ).data()
        lines = [f"Sin datos para los últimos {days} días. Temas más activos en total:"]
        for i, r in enumerate(fallback, 1):
            lines.append(f"  {i}. {r['topic']}: {r['posts']} posts")
        return "\n".join(lines)

    results = []
    for r in recent:
        topic  = r["topic"]
        curr   = r["posts"]
        prev_c = prev_map.get(topic, 0)
        growth = round((curr - prev_c) / prev_c * 100) if prev_c > 0 else 100
        results.append({"topic": topic, "current": curr, "previous": prev_c, "growth": growth})
    results.sort(key=lambda x: x["growth"], reverse=True)

    lines = [f"=== TENDENCIAS (últimos {days} días vs {days} anteriores) — {community} ==="]
    for i, r in enumerate(results, 1):
        trend = "↗ Creciendo" if r["growth"] > 20 else ("→ Estable" if r["growth"] >= -20 else "↘ Bajando")
        new_label = " [NUEVO]" if r["previous"] == 0 else ""
        lines.append(
            f"  {i}. {r['topic']}: {r['current']} posts (+{r['growth']}% vs {r['previous']} prev)"
            f"{new_label} {trend}"
        )
    return "\n".join(lines)


def get_mandatory_context(community: str) -> str:
    """
    Contexto obligatorio de Neo4j — se ejecuta en CADA consulta sin excepción.

    Incluye siempre: KPIs de comunidad, ranking top 10 usuarios, tendencias 30 días.
    Garantiza que el agente nunca responda datos de memoria ni de pantalla.
    """
    logger.info("📊 Obteniendo contexto obligatorio de Neo4j...")
    parts: list[str] = []

    try:
        parts.append("KPIs de comunidad:\n" + get_community_kpis(community=community))
    except Exception as exc:
        logger.warning(f"get_community_kpis falló: {exc}")

    try:
        parts.append("Ranking usuarios (Neo4j):\n" + get_user_ranking(community=community, limit=10))
    except Exception as exc:
        logger.warning(f"get_user_ranking falló: {exc}")

    try:
        parts.append("Tendencias recientes (Neo4j):\n" + get_trending_topics(community=community, days=30))
    except Exception as exc:
        logger.warning(f"get_trending_topics falló: {exc}")

    logger.info(f"✅ Contexto obligatorio listo — {len(parts)}/3 secciones obtenidas de Neo4j")
    return "\n\n".join(parts)


def _detect_language(text: str) -> str:
    if not _LANGDETECT_OK or len(text.strip()) < 8:
        return "es"
    try:
        return _langdetect_fn(text)
    except Exception:
        return "es"


def _translate_to_spanish(text: str, source_lang: str) -> str:
    """Traduce la consulta al español usando el propio LLM. Solo se llama si detecta idioma no español."""
    try:
        result = str(_get_llm().invoke(
            f"Translate the following {source_lang} text to Spanish. Output ONLY the translation:\n{text}"
        )).strip()
        if result and 5 < len(result) < len(text) * 5:
            return result
    except Exception:
        pass
    return text


def _format_rubric_output(raw: str, community: str) -> str:
    """Convierte la salida raw del LLM de rúbrica en tabla markdown profesional."""
    import re as _re

    blocks = _re.split(r'\n---+\n?', raw)
    entries = []
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        e: dict = {}
        m = _re.search(r'AUTOR:\s*(.+)', block)
        if m:
            e["autor"] = m.group(1).strip()
        for key, pat in [
            ("pertinencia",   r'PERTINENCIA:\s*(\d+(?:\.\d+)?)'),
            ("aporte",        r'APORTE_PEDAGOGICO:\s*(\d+(?:\.\d+)?)'),
            ("argumentacion", r'ARGUMENTACION:\s*(\d+(?:\.\d+)?)'),
            ("apoyo",         r'APOYO_EMOCIONAL:\s*(\d+(?:\.\d+)?)'),
            ("total",         r'PUNTUACION_FINAL:\s*(\d+(?:\.\d+)?)'),
        ]:
            m = _re.search(pat, block)
            if m:
                e[key] = float(m.group(1))
        for key, pat in [
            ("categoria",    r'CATEGORIA:\s*(.+?)(?:\n|$)'),
            ("fortalezas",   r'FORTALEZAS:\s*(.+?)(?:\n|$)'),
            ("areas_mejora", r'AREAS_MEJORA:\s*(.+?)(?:\n|$)'),
        ]:
            m = _re.search(pat, block)
            if m:
                e[key] = m.group(1).strip()
        if e.get("autor"):
            entries.append(e)

    if not entries:
        return raw

    entries.sort(key=lambda e: e.get("total", 0), reverse=True)
    medals     = ["🥇", "🥈", "🥉"]
    cat_emoji  = {"Lider": "🏆", "Experto": "🎖️", "Conector": "🔗", "Participante": "📌"}

    def _fmt(v) -> str:
        return f"{v:.0f}/10" if isinstance(v, float) else str(v)

    lines = [
        f"## 📋 Evaluación Pedagógica — {community}\n",
        "| # | Usuario | 🎯 Pertinencia | 📚 Aporte Ped. | 💬 Argumentación | 💝 Apoyo Em. | **Total** | Categoría |",
        "|:-:|---------|:-------------:|:-------------:|:----------------:|:------------:|:---------:|-----------|",
    ]
    for i, e in enumerate(entries):
        pos     = medals[i] if i < 3 else str(i + 1)
        total   = e.get("total", "—")
        cat     = e.get("categoria", "—")
        cat_lbl = f"{cat_emoji.get(cat, '')} {cat}".strip()
        total_s = f"**{total:.1f}/10**" if isinstance(total, float) else f"**{total}**"
        lines.append(
            f"| {pos} | {e.get('autor', '?')} "
            f"| {_fmt(e.get('pertinencia', '—'))} "
            f"| {_fmt(e.get('aporte', '—'))} "
            f"| {_fmt(e.get('argumentacion', '—'))} "
            f"| {_fmt(e.get('apoyo', '—'))} "
            f"| {total_s} | {cat_lbl} |"
        )

    lines += ["", "---", "", "### Detalle por contribuidor", ""]
    for i, e in enumerate(entries):
        autor   = e.get("autor", "?")
        total   = e.get("total", "?")
        cat     = e.get("categoria", "?")
        emoji   = cat_emoji.get(cat, "📌")
        t_str   = f"{total:.1f}" if isinstance(total, float) else str(total)
        pos_lbl = medals[i] if i < 3 else f"{i+1}."
        lines.append(f"**{pos_lbl} {autor}** — {emoji} {cat} &nbsp;|&nbsp; Puntuación: **{t_str}/10**  ")
        if e.get("fortalezas"):
            lines.append(f"- ✅ {e['fortalezas']}  ")
        if e.get("areas_mejora"):
            lines.append(f"- ⚠️ {e['areas_mejora']}  ")
        lines.append("")

    return "\n".join(lines)


def evaluate_contributions(community: str, search_hints: list[str] = None) -> str:
    """
    Evalúa contribuciones por rúbrica pedagógica. Solo evalúa autores con ≥3 publicaciones sustanciales.

    🔍 FUENTE DE DATOS: Neo4j (posts reales) + LLM (evaluación pedagógica)
    ⚠️ NO usa datos visuales ni HTML

    CUÁNDO USARME:
    - Usuario pide EXPLÍCITAMENTE: "Evalúa las contribuciones" / "Evaluación pedagógica"
    - Keywords específicas: evalúa las contribuciones, evaluación pedagógica, rúbrica pedagógica

    RETORNA:
    Tabla markdown con puntuaciones por criterio y detalle por contribuidor.
    Excluye autores con menos de 3 publicaciones sustanciales (>50 caracteres).
    """
    driver = _get_driver()
    has_comm = bool(community and community != "todas")
    cp = {"community": community} if has_comm else {}
    cw = "WHERE c.name = $community" if has_comm else ""

    with driver.session() as session:
        targeted: list[dict] = []
        if search_hints:
            for hint in search_hints[:2]:
                rows = session.run(
                    f"MATCH (a:Author)-[:WROTE]->(p:Post)-[:IN_DISCUSSION]->(:Discussion)-[:PERTAINS_TO]->(c:Community) "
                    f"{'WHERE c.name = $community AND' if has_comm else 'WHERE'} toLower(a.name) CONTAINS $hint "
                    f"WITH a, collect(p) AS posts, count(p) AS total "
                    f"WHERE total >= 3 "
                    f"WITH a, [px IN posts WHERE size(px.content) > 50] AS sub, total "
                    f"WHERE size(sub) >= 1 "
                    f"RETURN a.name AS author, sub[0].content AS text, total AS post_count "
                    f"ORDER BY total DESC LIMIT 3",
                    **{**cp, "hint": hint.lower()}
                ).data()
                targeted.extend(rows)

        if not targeted:
            targeted = session.run(
                f"MATCH (a:Author)-[:WROTE]->(p:Post)-[:IN_DISCUSSION]->(:Discussion)-[:PERTAINS_TO]->(c:Community) "
                f"{cw} "
                f"WITH a, collect(p) AS posts, count(p) AS total "
                f"WHERE total >= 3 "
                f"WITH a, [px IN posts WHERE size(px.content) > 50] AS sub, total "
                f"WHERE size(sub) >= 3 "
                f"RETURN a.name AS author, sub[0].content AS text, total AS post_count "
                f"ORDER BY total DESC LIMIT 6",
                **cp
            ).data()

    if not targeted:
        return "Sin contribuciones suficientes para evaluar (se requieren al menos 3 publicaciones por autor)."

    by_author: dict[str, str] = {}
    for r in targeted:
        a = str(r.get("author") or "Anonimo")
        if a not in by_author:
            by_author[a] = str(r.get("text") or "")[:300]

    posts_text = "\n".join(
        f"[{author}]: {text}" for author, text in list(by_author.items())[:4]
    )
    raw = str(_get_llm().invoke(
        RUBRIC_PROMPT.format(community=community, posts=posts_text)
    )).strip()
    return _format_rubric_output(raw, community)


def build_excel_data(community: str) -> dict:
    """
    Construye datos estructurados consultando Neo4j para el Excel de reporte.

    🔍 FUENTE DE DATOS: Neo4j Graph Database (consulta directa)
    ⚠️ NO usa datos visuales ni HTML

    RETORNA:
    Dict con hojas: KPIs (métricas clave), Ranking_Usuarios (top 15 por posts),
    Tendencias (top 15 temas con actividad reciente vs total).
    """
    cutoff_30 = (datetime.now() - timedelta(days=30)).date()
    cutoff_60 = (datetime.now() - timedelta(days=60)).date()
    driver = _get_driver()
    has_comm = bool(community and community != "todas")
    cp  = {"community": community} if has_comm else {}
    cw  = "WHERE c.name = $community" if has_comm else ""
    cwa = "WHERE c.name = $community AND" if has_comm else "WHERE"

    with driver.session() as session:
        total = (session.run(
            f"MATCH (a:Author)-[:WROTE]->(:Post)-[:IN_DISCUSSION]->(:Discussion)-[:PERTAINS_TO]->(c:Community) "
            f"{cw} RETURN count(DISTINCT a) AS n", **cp
        ).single() or {"n": 0})["n"]

        active_30 = (session.run(
            f"MATCH (a:Author)-[:WROTE]->(p:Post)-[:IN_DISCUSSION]->(:Discussion)-[:PERTAINS_TO]->(c:Community) "
            f"{cwa} p.date >= $c RETURN count(DISTINCT a) AS n", **{**cp, "c": cutoff_30}
        ).single() or {"n": 0})["n"]

        active_prev = (session.run(
            f"MATCH (a:Author)-[:WROTE]->(p:Post)-[:IN_DISCUSSION]->(:Discussion)-[:PERTAINS_TO]->(c:Community) "
            f"{cwa} p.date >= $c60 AND p.date < $c30 RETURN count(DISTINCT a) AS n",
            **{**cp, "c60": cutoff_60, "c30": cutoff_30}
        ).single() or {"n": 0})["n"]

        ranking = session.run(
            f"MATCH (a:Author)-[:WROTE]->(p:Post)-[:IN_DISCUSSION]->(d:Discussion)-[:PERTAINS_TO]->(c:Community) "
            f"{cw} RETURN a.name AS name, count(p) AS posts, count(DISTINCT d) AS discussions "
            f"ORDER BY posts DESC LIMIT 15", **cp
        ).data()

        topics = session.run(
            f"MATCH (:Author)-[:WROTE]->(:Post)-[:IN_DISCUSSION]->(d:Discussion)-[:PERTAINS_TO]->(c:Community) "
            f"{cw} RETURN d.topic AS topic, count(*) AS total_posts ORDER BY total_posts DESC LIMIT 15",
            **cp
        ).data()

        topics_30d_rows = session.run(
            f"MATCH (:Author)-[:WROTE]->(p:Post)-[:IN_DISCUSSION]->(d:Discussion)-[:PERTAINS_TO]->(c:Community) "
            f"{cwa} p.date >= $c RETURN d.topic AS topic, count(*) AS posts_30d ORDER BY posts_30d DESC LIMIT 15",
            **{**cp, "c": cutoff_30}
        ).data()
        topics_30d = {r["topic"]: r["posts_30d"] for r in topics_30d_rows}

    pct    = (active_30 / total * 100) if total > 0 else 0
    growth = active_30 - active_prev
    gpct   = (growth / active_prev * 100) if active_prev > 0 else 0

    return {
        "KPIs": {
            "headers": ["Métrica", "Valor", "Variación"],
            "rows": [
                ["Total miembros", total, "—"],
                ["Activos últimos 30 días", active_30, f"{growth:+d} ({gpct:+.1f}%)"],
                ["Activos mes anterior", active_prev, "—"],
                ["% participación activa", f"{pct:.1f}%", "—"],
            ],
        },
        "Ranking_Usuarios": {
            "headers": ["Posición", "Usuario", "Publicaciones", "Discusiones"],
            "rows": [
                [i + 1, r["name"], r["posts"], r["discussions"]]
                for i, r in enumerate(ranking)
            ],
            "chart_col": 3,
            "chart_title": "Ranking de Participación",
        },
        "Tendencias": {
            "headers": ["Tema", "Posts totales", "Posts 30 días", "% reciente"],
            "rows": [
                [
                    str(r["topic"])[:40],
                    r["total_posts"],
                    topics_30d.get(r["topic"], 0),
                    f"{topics_30d.get(r['topic'], 0) / r['total_posts'] * 100:.0f}%"
                    if r["total_posts"] > 0 else "0%",
                ]
                for r in topics
            ],
            "chart_col": 2,
            "chart_title": "Temas más activos",
        },
    }


def _extract_search_hints(input_text: str) -> list[str]:
    """Extrae palabras clave (posibles nombres/temas) de la consulta del usuario."""
    words = re.findall(r'\b[a-záéíóúñA-ZÁÉÍÓÚÑ]{3,}\b', input_text)
    hints = [w for w in words if w.lower() not in _SEARCH_STOP]
    # Prioriza palabras capitalizadas (mas probable que sean nombres propios)
    hints.sort(key=lambda w: (0 if w[0].isupper() else 1, -len(w)))
    return hints[:4]


def _run_query(session, community: str, extra_where: str, params: dict, limit: int) -> list:
    base = """
    MATCH (a:Author)-[:WROTE]->(p:Post)-[:IN_DISCUSSION]->(d:Discussion)-[:PERTAINS_TO]->(c:Community)
    """
    where_parts = []
    if community and community != "todas":
        where_parts.append("c.name = $community")
        params["community"] = community
    if extra_where:
        where_parts.append(extra_where)
    where_clause = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""
    query = f"{base} {where_clause} RETURN a.name AS author, p.content AS text, d.topic AS subject ORDER BY p.date DESC LIMIT {limit}"
    return [r.data() for r in session.run(query, **params)]


def get_forum_context(community: str = "todas", limit: int = 20, search_hints: list[str] = None) -> str:
    """
    Extrae contexto de los foros para el agente. Busca por autor/tema si hay hints específicos.

    🔍 FUENTE DE DATOS: Neo4j Graph Database (consulta directa)
    ⚠️ NO usa datos visuales ni HTML — el agente NO puede "ver" el chat ni la pantalla

    CUÁNDO USARME:
    - Contexto general de conversación sobre una comunidad
    - Búsqueda de publicaciones de un autor específico o sobre un tema concreto

    RETORNA:
    Lista de posts "[Tema] Autor: extracto", priorizando resultados
    dirigidos (búsqueda por hint) sobre mensajes recientes generales.
    """
    driver = _get_driver()
    targeted: list[dict] = []
    recent: list[dict] = []

    with driver.session() as session:
        if search_hints:
            for hint in search_hints:
                hl = hint.lower()
                # Busca por nombre de autor O por tema de hilo
                rows = _run_query(
                    session, community,
                    "(toLower(a.name) CONTAINS $hint OR toLower(d.topic) CONTAINS $hint)",
                    {"hint": hl}, limit=15,
                )
                targeted.extend(rows)

        # Mensajes recientes como contexto general
        recent_limit = max(8, limit - len(targeted))
        recent = _run_query(session, community, "", {}, limit=recent_limit)

    lines: list[str] = []
    seen: set[str] = set()

    def _add(rec: dict, max_chars: int) -> None:
        topic = str(rec.get("subject") or "sin tema").strip()
        text = str(rec.get("text") or "").strip()
        author = str(rec.get("author") or "Anonimo").strip()
        if is_noise_record(topic, text):
            return
        key = f"{author}:{text[:60]}"
        if key in seen:
            return
        seen.add(key)
        display = (text[:max_chars] + "...") if len(text) > max_chars else text
        lines.append(f"[{topic}] {author}: {display}")

    # Resultados dirigidos primero: contenido completo (hasta 500 chars)
    for rec in targeted:
        _add(rec, max_chars=500)

    # Contexto reciente general: compacto (120 chars)
    for rec in recent:
        _add(rec, max_chars=120)

    if not lines:
        return "Sin mensajes en esta comunidad."

    return "\n".join(lines)


def _build_base_context(input_text: str, community: str) -> str:
    hints = _extract_search_hints(input_text)

    # Contexto de posts (búsqueda dirigida + mensajes recientes)
    forum_ctx = get_forum_context(community=community, limit=15, search_hints=hints or None)

    # Contexto obligatorio: siempre se obtiene de Neo4j, independientemente de la pregunta
    mandatory = get_mandatory_context(community=community)

    parts = [forum_ctx, mandatory]
    extra: list[str] = []

    # Ampliaciones opcionales para preguntas que requieren análisis más profundo
    if REPORT_HINTS.search(input_text):
        parts.append("KPIs mensuales detallados:\n" + get_monthly_directive_report(community=community))
        extra.append("get_monthly_directive_report")

    if ENGAGEMENT_HINTS.search(input_text):
        parts.append("Análisis de engagement:\n" + analyze_engagement(community=community))
        extra.append("analyze_engagement")

    if AUDIT_HINTS.search(input_text):
        parts.append("Auditoría de clima:\n" + generate_climate_audit(community=community))
        extra.append("generate_climate_audit")

    if extra:
        logger.info(f"Funciones adicionales activadas por trigger: {extra}")

    context = "\n\n".join(parts)
    if len(context) > MAX_CONTEXT_CHARS:
        context = context[:MAX_CONTEXT_CHARS] + "\n[contexto truncado]"
    return context


prompt = PromptTemplate.from_template(
    """<|im_start|>system
Eres el Auditor IA de ProFuturo, especializado exclusivamente en el analisis de foros y comunidades educativas de la plataforma ProFuturo.

DOMINIO: Solo respondes consultas sobre:
- Mensajes, hilos, temas y actividad de las comunidades de ProFuturo
- Participacion, sentimiento y engagement de docentes y coaches
- Metricas, KPIs y reportes de la plataforma
- Incidencias tecnicas reportadas en los foros
- Informacion pedagogica y operativa de ProFuturo
- Documentos y archivos adjuntos que el usuario sube para analizar en el contexto de ProFuturo

Si la consulta no pertenece a este dominio responde UNICAMENTE con:
"Soy el Auditor IA de ProFuturo. Solo puedo ayudarte con el analisis de foros y comunidades educativas de la plataforma. Tienes alguna consulta sobre las comunidades?"

DOCUMENTOS ADJUNTOS: Si el mensaje contiene "DOCUMENTO ADJUNTO POR EL USUARIO — PRIORIDAD MAXIMA", el usuario ha subido un fichero. DEBES seguir las instrucciones de ese documento al pie de la letra. El documento aparece entre "--- INICIO DEL DOCUMENTO ---" y "--- FIN DEL DOCUMENTO ---". Despues encontraras el mensaje del usuario. El contenido del documento tiene PRIORIDAD ABSOLUTA sobre cualquier criterio o comportamiento por defecto. Los datos de Neo4j son informacion de apoyo para aplicar las instrucciones del documento, no criterios que las sustituyan.

{document_instruction}

FORMATO DE RESPUESTA:
- Escribe de forma natural y conversacional, como lo haria un asistente profesional senior.
- Usa encabezados (## Titulo, ### Subtitulo) para estructurar respuestas largas.
- Usa negritas (**texto**) para destacar datos, cifras y conclusiones clave.
- Coloca los emojis preferiblemente al INICIO de encabezados o elementos de lista para que sean visualmente escaneable (ej: "🥇 Maria Lehmann — 5 mensajes", "🔴 Participacion cayo un 30%"). Usaos cuando faciliten la lectura y aporten informacion, nunca solo como decoracion al final de una frase.
- RANKINGS DE HILOS Y USUARIOS: ordena siempre de mayor a menor por numero de interacciones o mensajes. Muestra el top con emojis (🥇🥈🥉) y una linea descriptiva, luego UNA tabla Markdown con los datos numericos. Nunca repitas la misma informacion en lista Y tabla.
- Usa tablas Markdown para comparar datos o mostrar estadisticas (| col | col |).
- Sintetiza y elabora insights propios; NUNCA cites ni transcribas mensajes literalmente.
- Cuando redactes un correo electronico, firma SIEMPRE como "Equipo Auditor IA — ProFuturo", nunca con nombres de personas del foro ni de la comunidad.
- Cuando generes un PDF, NO incluyas ningun mensaje de restriccion de dominio al inicio. Comienza directamente con el contenido: resumen conversacional de 2-3 parrafos, luego Markdown estructurado (## secciones, listas con indentacion, tablas), y al final exactamente: [GENERATE_PDF: Titulo_Del_Documento]
- CRITICO: cuando el usuario pida explicitamente un PDF, documento o informe descargable (de cualquier tema anterior o nuevo), SIEMPRE genera el contenido completo y termina con [GENERATE_PDF: Titulo]. NUNCA digas que no puedes generar PDFs. El PDF del usuario siempre es posible.
- En el PDF combina parrafos explicativos, tablas para datos comparativos y listas numeradas para rankings. No pongas todo en listas de viñetas.
- EXCEL: cuando el usuario solicite un Excel, hoja de calculo, xlsx o exportacion de datos, responde con una breve descripcion y termina EXACTAMENTE con: [GENERATE_EXCEL: Titulo_Del_Excel]. El Excel incluira KPIs, ranking y tendencias de la comunidad.

Comunidad activa: {community}

Datos obtenidos de Neo4j en tiempo real (KPIs, ranking de usuarios, tendencias y mensajes recientes — SIEMPRE actualizados, NUNCA inventados):
{context}
<|im_end|>
{history}<|im_start|>user
{input}<|im_end|>
<|im_start|>assistant
"""
)


_DOMAIN_GUARD_RE = re.compile(
    r"Soy el Auditor IA de ProFuturo\.[^\n]*\n?[^\n]*\n?",
    re.IGNORECASE,
)


def run_agent(input_text: str, community: str = "todas", client_history: list[dict] = None) -> dict:
    if not input_text.strip():
        return {"response": "Por favor, ingresa una consulta.", "pdf_base64": None, "pdf_filename": "",
                "excel_base64": None, "excel_filename": ""}

    # --- Detección de idioma y traducción al español ---
    detected_lang = _detect_language(input_text)
    if detected_lang not in ("es", "ca", "gl"):  # catalán y gallego se procesan tal cual
        input_text = _translate_to_spanish(input_text, detected_lang)

    # --- Intercept: "hazme un pdf de lo anterior" ---
    if client_history and _PDF_OF_PREV_RE.search(input_text):
        prev_content = _last_ai_content(client_history)
        if prev_content:
            pdf_ready = prev_content.encode("latin-1", "ignore").decode("latin-1")
            title = f"Informe_{re.sub(r'[^\\w]', '_', community)[:40]}"
            pdf_b64 = generate_report_pdf(pdf_ready, title)
            safe = re.sub(r"[^\w\s-]", "", title).strip().replace(" ", "_")[:60]
            filename = f"{safe}.pdf" if safe else "reporte.pdf"
            return {
                "response": f"Aqui tienes el PDF con el contenido anterior.\n\n**PDF generado:** {filename}",
                "pdf_base64": pdf_b64,
                "pdf_filename": filename,
                "excel_base64": None,
                "excel_filename": "",
            }

    # --- Intercept: evaluación por rúbrica ---
    _has_document = (
        "DOCUMENTO ADJUNTO POR EL USUARIO" in input_text[:300]
        or input_text.startswith("El usuario ha adjuntado el siguiente documento")
    )
    if not _has_document and RUBRIC_HINTS.search(input_text):
        hints = _extract_search_hints(input_text)
        try:
            rubric_text = evaluate_contributions(community, hints or None)
            if rubric_text and len(rubric_text) > 50:
                memory = _get_memory(community)
                memory.chat_memory.add_user_message(f"<|im_start|>user\n{input_text}<|im_end|>")
                memory.chat_memory.add_ai_message(f"<|im_start|>assistant\n{rubric_text}<|im_end|>")
                return {
                    "response": rubric_text,
                    "pdf_base64": None,
                    "pdf_filename": "",
                    "excel_base64": None,
                    "excel_filename": "",
                }
        except Exception:
            pass  # cae al flujo normal si falla

    memory = _get_memory(community)
    _trim_history(memory)

    if client_history:
        history = _format_client_history(client_history)
    else:
        history = _history_to_chatml(memory)

    chain = prompt | _get_llm()
    context = _build_base_context(input_text, community)

    document_instruction = ""
    if _has_document:
        document_instruction = (
            "════════════════════════════════════════════════════\n"
            "ATENCION: DOCUMENTO CON PRIORIDAD ABSOLUTA\n"
            "════════════════════════════════════════════════════\n"
            "El usuario ha adjuntado un documento. Tu respuesta DEBE basarse en el\n"
            "contenido de ese documento. Si contiene criterios o instrucciones,\n"
            "APLICALOS exactamente tal cual, sin modificarlos ni reinterpretarlos,\n"
            "aunque contradigan tus comportamientos por defecto.\n"
            "Los datos de Neo4j son informacion de apoyo para aplicar las instrucciones\n"
            "del documento, no criterios que las sustituyan.\n"
            "════════════════════════════════════════════════════"
        )
        logger.info("Documento adjunto detectado — document_instruction inyectada en system prompt")

    final_response = str(
        chain.invoke({
            "input": input_text,
            "community": community,
            "context": context,
            "history": history,
            "document_instruction": document_instruction,
        })
    ).strip()

    # ═══ VALIDACIÓN RUNTIME ═══
    # get_mandatory_context() garantiza que Neo4j SIEMPRE se consultó.
    # Solo advertimos si el contexto llegó vacío (fallo de conexión).
    if "RANKING" not in context and "KPIs" not in context:
        logger.warning(
            f"⚠️  CRÍTICO: contexto Neo4j vacío — posible fallo de conexión. "
            f"input='{input_text[:80]}'"
        )
    else:
        logger.info(f"✅ Respuesta basada en datos Neo4j (contexto obligatorio inyectado)")

    pdf_base64    = None
    pdf_filename  = ""
    excel_base64  = None
    excel_filename = ""

    # --- Marker GENERATE_EXCEL ---
    excel_match = re.search(r"\[?GENERATE_EXCEL:\s*([^\]\n\[]+)\]?", final_response)
    if excel_match:
        try:
            excel_title = excel_match.group(1).strip()
            from src.tools import generate_report_excel
            excel_data  = build_excel_data(community)
            excel_base64 = generate_report_excel(excel_data, excel_title)
            safe_e = re.sub(r"[^\w\s-]", "", excel_title).strip().replace(" ", "_")[:60]
            excel_filename = f"{safe_e}.xlsx" if safe_e else "reporte.xlsx"
            final_response = re.sub(r"\[?GENERATE_EXCEL:[^\]\n\[]+\]?", "", final_response).strip()
            final_response += f"\n\n**Excel generado:** {excel_filename}"
        except Exception as exc:
            final_response = re.sub(r"\[?GENERATE_EXCEL:[^\]\n\[]+\]?", "", final_response).strip()
            final_response += f"\n\n_(Error generando Excel: {exc})_"

    # --- Marker GENERATE_PDF ---
    pdf_match = re.search(r"\[?GENERATE_PDF:\s*([^\]\n\[]+)\]?", final_response)
    if pdf_match:
        title  = pdf_match.group(1).strip()
        before = final_response[:pdf_match.start()].rstrip()
        after  = final_response[pdf_match.end():].lstrip()
        pdf_content = before if len(before) >= len(after) else after
        pdf_content = _DOMAIN_GUARD_RE.sub("", pdf_content).strip()
        pdf_content = re.sub(r"\[?GENERATE_PDF:[^\]\n]+\]?", "", pdf_content).strip()

        if len(pdf_content) < 150:
            for msg in reversed(memory.chat_memory.messages):
                if isinstance(msg, AIMessage):
                    raw = str(msg.content)
                    raw = re.sub(r"<\|im_start\|>assistant\n?", "", raw)
                    raw = re.sub(r"<\|im_end\|>", "", raw)
                    raw = _DOMAIN_GUARD_RE.sub("", raw).strip()
                    raw = re.sub(r"\[?GENERATE_PDF:[^\]\n]+\]?", "", raw).strip()
                    if len(raw) > 200:
                        pdf_content = raw
                        break

        final_response = pdf_content
        pdf_base64 = generate_report_pdf(
            pdf_content.encode("latin-1", "ignore").decode("latin-1"), title
        )
        safe_title = re.sub(r"[^\w\s-]", "", title).strip().replace(" ", "_")[:60]
        pdf_filename = f"{safe_title}.pdf" if safe_title else "reporte.pdf"
        final_response += f"\n\n**PDF generado:** {pdf_filename}"

    final_response = apply_current_report_dates(final_response)

    memory.chat_memory.add_user_message(f"<|im_start|>user\n{input_text}<|im_end|>")
    memory.chat_memory.add_ai_message(f"<|im_start|>assistant\n{final_response}<|im_end|>")

    return {
        "response":       final_response,
        "pdf_base64":     pdf_base64,
        "pdf_filename":   pdf_filename,
        "excel_base64":   excel_base64,
        "excel_filename": excel_filename,
    }
