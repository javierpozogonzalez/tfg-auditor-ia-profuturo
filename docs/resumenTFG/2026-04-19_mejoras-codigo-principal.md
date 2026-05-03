# Mejoras de estabilidad, rendimiento y UX — Componentes principales

**Fecha:** 2026-04-19
**Archivos afectados:** `backend/src/agent.py`, `backend/src/llm_config.py`, `backend/src/tools.py`, `backend/src/main.py`, `backend/scripts/rpa.py`, `components/dashboard/ai-chat.tsx`, `app/globals.css`

---

## 1. backend/src/llm_config.py — Cache del cliente boto3

**Problema:** `_build_client()` creaba un nuevo cliente boto3 en cada llamada al LLM, generando overhead de autenticacion y conexion innecesario.

**Solucion:** Renombrado a `_get_client()` con `PrivateAttr(default=None)` de Pydantic. El cliente se instancia una sola vez y se reutiliza durante toda la vida del proceso.

**Cambio adicional:** `LLM_MAX_TOKENS` cambiado de 512 a 2048 para aprovechar el margen disponible en el presupuesto de tokens (6144 limite del endpoint TGI).

---

## 2. backend/src/agent.py — Gestion de tokens, historial y formato

**Problema 1 — Token overflow:** Tras varios turnos de conversacion, el historial acumulado superaba el limite de 6144 tokens del modelo (`Given: 6979`).

**Solucion:** Introduccion de constantes de presupuesto (`MAX_CONTEXT_CHARS = 2800`, `MAX_HISTORY_PAIRS = 3`) y funcion `_trim_history()` que poda el historial a los ultimos 3 pares antes de cada inferencia. Contexto reducido a 20 posts con 120 chars cada uno.

**Problema 2 — Respuestas fuera de dominio:** El agente respondia consultas no relacionadas con ProFuturo (ej. futbol, preguntas generales).

**Solucion:** Guard de dominio en el system prompt: si la consulta no pertenece al dominio, el modelo devuelve un mensaje fijo predefinido.

**Problema 3 — Citado literal de mensajes:** El agente citaba textualmente fragmentos del foro en lugar de elaborar insights.

**Solucion:** Instruccion explicita en el system prompt: "Sintetiza y elabora insights propios; NUNCA cites ni transcribas mensajes de usuario literalmente."

**Problema 4 — Formato plano:** Respuestas sin estructura visual (sin encabezados, tablas ni emojis).

**Solucion:** Instrucciones de formato enriquecidas: uso obligatorio de `##`/`###`, negritas, listas, tablas Markdown y emojis moderados (max 3-4).

**Mejora adicional:** Eliminada la doble llamada a `apply_current_report_dates()` en el path de generacion de PDF.

---

## 3. backend/src/tools.py — PDF sin cabeceras azules

**Problema:** El PDF generado tenia rectangulos azules rellenos arriba y abajo que daban aspecto de documento tecnico generico.

**Solucion:** `_header_footer()` reescrita: logo ProFuturo en margen izquierdo + linea fina azul corporativa (1.5pt) en cabecera, linea fina gris + fecha y numero de pagina en pie. Sin rectangulos de relleno.

**Mejora adicional:** Path del logo migrado a `Path(__file__).resolve().parent.parent.parent / "logo.png"` (absoluto, independiente del directorio de trabajo). Emoji `⚠` eliminado de la alerta critica (Helvetica no soporta Unicode fuera del BMP).

---

## 4. backend/src/main.py — Lifespan y endpoints RPA

**Problema:** `@app.on_event("startup")` deprecado en FastAPI moderno genera warnings en consola.

**Solucion:** Migrado al patron `@asynccontextmanager async def lifespan(app)` recomendado desde FastAPI 0.93+.

**Mejora adicional:** Driver Neo4j en endpoints `/api/communities`, `/api/feed`, `/api/graph` convertido a singleton (no se cerraba entre requests, ahora se reutiliza).

**Nuevos endpoints RPA:**
- `GET /api/rpa/status` — estado del scheduler (running, proximas ejecuciones)
- `POST /api/rpa/trigger/{job_id}` — disparo manual de `critical_monitor` o `weekly_summary` (util para testing y demos)
- `GET /api/rpa/logs?lines=50` — ultimas N lineas del log del scheduler

---

## 5. backend/scripts/rpa.py — Log absoluto, email semanal, scheduler exportado

**Problema:** Path del log era relativo (`"profuturo_rpa.log"`), lo que hacia que el archivo se creara en el directorio de trabajo en lugar de en `backend/`.

**Solucion:** Cambiado a `Path(__file__).parent.parent / "profuturo_rpa.log"` (siempre en `backend/` independientemente del directorio desde donde se lanza).

**Mejora:** `weekly_summary_job()` ahora envia el PDF por email al administrador tras generarlo (mismo comportamiento que `critical_monitor_job()`).

**Para exposicion de estado:** `_scheduler` convertido en variable de modulo y exportado via `get_scheduler()` para que `main.py` pueda consultarlo.

---

## 6. Frontend — Markdown rendering y layout

**Problema:** El chat mostraba el markdown en texto plano (`##`, `**`, emojis como texto) en lugar de renderizarlo.

**Causa:** `remark-gfm` no estaba instalado (necesario para tablas GFM) y el plugin `@tailwindcss/typography` no estaba cargado en Tailwind v4.

**Solucion:**
- Instalado `remark-gfm` y anadido como plugin en `<ReactMarkdown remarkPlugins={[remarkGfm]}>`
- Anadido `@plugin "@tailwindcss/typography"` en `app/globals.css` (sintaxis requerida por Tailwind v4)

**Mejora de layout:** Burbujas de chat con `min-w-0 max-w-[85%]` + `break-words` + `overflow-x-auto` para evitar desbordamiento horizontal en mensajes largos o tablas.

---

## Verificacion rapida (RPA)

```bash
# Estado del scheduler
curl http://localhost:8000/api/rpa/status

# Disparar monitor de criticos manualmente
curl -X POST http://localhost:8000/api/rpa/trigger/critical_monitor

# Ver ultimas 30 lineas del log
curl "http://localhost:8000/api/rpa/logs?lines=30"
```

El log del scheduler se encuentra en `backend/profuturo_rpa.log` y es la fuente de verdad de todas las ejecuciones automaticas.
