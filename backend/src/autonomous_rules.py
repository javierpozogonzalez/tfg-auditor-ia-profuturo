"""
Reglas de decision para el agente autonomo de ProFuturo.

Todas las funciones son puras (sin I/O) y devuelven bool.
El agente las consulta antes de cada publicacion para decidir si actua.
"""
import re
from datetime import datetime, date

# Patron de conflicto grave: el agente NO publica, solo alerta al coordinador.
_CONFLICT_RE = re.compile(
    r"\b(acoso|amenaza|insulto|ataque|agresion|ofensivo|discrimina"
    r"|odio|racismo|sexismo|violencia|bullying)\b",
    re.IGNORECASE,
)

# Sentiment muy negativo: tambien deriva a coordinador humano.
_NEGATIVE_RE = re.compile(
    r"\b(p[eé]simo|horrible|terrible|muy\s+malo|un\s+desastre"
    r"|harto|decepcionante|inaceptable|imperdonable|vergonzoso)\b",
    re.IGNORECASE,
)

# Keywords de preguntas tecnicas frecuentes (FAQ).
_FAQ_RE = re.compile(
    r"\b(c[oó]mo\s+(accedo|entro|me\s+registro|descargo|subo|envio)"
    r"|no\s+puedo\s+(acceder|entrar|ver|descargar|subir)"
    r"|contrase[nñ]a|password|login|certificado|diploma|badge|insignia"
    r"|c[oó]mo\s+obtengo|plazo|fecha\s+l[ií]mite"
    r"|cu[aá]ndo\s+(termina|acaba|empieza|comienza)"
    r"|soporte|ayuda|problema\s+t[eé]cnico)\b",
    re.IGNORECASE,
)

# Menciones directas al agente.
_MENTION_RE = re.compile(r"@[Aa]uditor(\s*(IA|_IA)?)?", re.IGNORECASE)


def _parse_date(raw) -> date | None:
    if raw is None:
        return None
    if hasattr(raw, "year"):
        return raw if hasattr(raw, "month") else None
    try:
        return datetime.fromisoformat(str(raw)).date()
    except (ValueError, TypeError):
        return None


def can_reactivate_thread(thread_data: dict) -> bool:
    """
    True si el hilo es candidato a reactivacion automatica.

    Condiciones:
    - 0 respuestas (solo el post inicial)
    - Antigüedad entre 7 y 14 dias
    - Sin marca ai_reactivated previa
    """
    if int(thread_data.get("reply_count", 0)) > 0:
        return False
    if thread_data.get("ai_reactivated"):
        return False

    last = _parse_date(thread_data.get("last_activity"))
    if last is None:
        return False

    days_ago = (datetime.now().date() - last).days
    return 7 <= days_ago <= 14


def should_welcome_user(user_data: dict) -> bool:
    """
    True si el usuario debe recibir bienvenida automatica.

    Condiciones:
    - Es su primer y unico post (total_posts == 1)
    - El post se hizo hace 2 dias o menos
    - No ha sido bienvenido todavia (ai_welcomed != true)
    """
    if int(user_data.get("total_posts", 0)) != 1:
        return False
    if user_data.get("ai_welcomed"):
        return False

    first = _parse_date(user_data.get("first_post_date"))
    if first is None:
        return False

    return (datetime.now().date() - first).days <= 2


def can_answer_faq(message_content: str) -> bool:
    """
    True si el mensaje contiene una pregunta tecnica frecuente que el agente puede responder.
    """
    return bool(_FAQ_RE.search(message_content))


def can_respond_to_mention(post_data: dict) -> bool:
    """
    True si el post menciona al agente y aun no tiene respuesta del bot.

    Detecta: '@Auditor', '@Auditor IA', '@auditor', '@auditor_IA'.
    """
    if post_data.get("ai_answered"):
        return False
    return bool(_MENTION_RE.search(str(post_data.get("content", ""))))


def needs_moderation_alert(message_data: dict) -> bool:
    """
    True si el mensaje requiere alerta al coordinador humano.

    El agente NO publica en estos casos: solo notifica por email.
    Detecta lenguaje de conflicto grave o sentiment muy negativo.
    """
    text = f"{message_data.get('topic', '')} {message_data.get('content', '')}"
    return bool(_CONFLICT_RE.search(text) or _NEGATIVE_RE.search(text))
