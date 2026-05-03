# Agente Autonomo ProFuturo — Documentacion Tecnica

## Descripcion general

El agente autonomo es una capa sobre el Auditor IA que, ademas de responder consultas en
el chat, **publica mensajes directamente en los foros de Moodle** de forma proactiva y
programada. Actua como el usuario "Auditor IA ProFuturo" (username: `auditor_ia`).

El agente NUNCA modera, elimina ni edita posts de otros usuarios. Solo crea nuevo contenido.
Todas las acciones quedan registradas en Neo4j y en `autonomous_agent.log`.

---

## Arquitectura

```
autonomous_agent.py  (6 jobs APScheduler)
     |
     +── autonomous_rules.py   (reglas de decision — funciones puras)
     |
     +── moodle_writer.py      (escritura en Moodle REST API)
     |
     +── src/llm_config.py     (LLM SageMaker — genera los mensajes)
     |
     +── Neo4j                 (consulta candidatos + registra acciones)
```

**Flujo general de cada job:**
1. Query Neo4j → obtener candidatos
2. `autonomous_rules.py` → filtrar (puede_actuar?)
3. LLM → generar mensaje contextual
4. `moodle_writer.py` → publicar (o simular)
5. Neo4j → marcar como procesado (evitar duplicados)
6. Log de la accion

---

## Jobs programados

### Job 1: reactivation_job — cada 6 horas

Busca hilos con exactamente 1 post (sin respuesta) con una antiguedad de 7-14 dias.
Genera un mensaje de reactivacion contextual al tema del hilo e invita a participar.

- Condicion: `reply_count == 0`, `7 <= dias_sin_actividad <= 14`, no marcado como `ai_reactivated`
- Limite: `MAX_REACTIVATIONS_PER_RUN` publicaciones por ejecucion (por defecto: 5)
- Marca en Neo4j: `d.ai_reactivated = true, d.ai_reactivated_date = date()`

### Job 2: welcome_job — cada 2 horas

Detecta usuarios con exactamente 1 post publicado en los ultimos 2 dias.
Genera un mensaje de bienvenida personalizado mencionando el tema de su primer post
y los usuarios mas activos de la comunidad.

- Condicion: `total_posts == 1`, `primer_post <= 2 dias`, no marcado como `ai_welcomed`
- Limite: `MAX_WELCOMES_PER_RUN` por ejecucion (por defecto: 10)
- Marca en Neo4j: `a.ai_welcomed = true`

### Job 3: mention_response_job — cada 30 minutos

Detecta posts de las ultimas 24 horas que contengan `@Auditor` o `@auditor`.
Genera una respuesta directa a la pregunta del usuario usando contexto de la comunidad.

- Condicion: post contiene `@Auditor*`, no marcado como `ai_answered`, ultimas 24h
- Si el post requiere moderacion (`needs_moderation_alert`): solo envia email al
  coordinador, NO publica en Moodle
- Limite: `MAX_MENTIONS_PER_RUN` por ejecucion (por defecto: 10)
- Marca en Neo4j: `p.ai_answered = true`

### Job 4: weekly_digest_post_job — viernes 17:00

Genera y publica el resumen semanal de cada comunidad activa como nueva discusion en el foro.
Incluye: total posts, participantes, temas activos, hilos sin respuesta.

- Una nueva discusion por comunidad con datos reales de Neo4j
- Solo actua si la comunidad tuvo actividad en los ultimos 7 dias

### Job 5: recognition_job — lunes 09:00

Reconoce al usuario mas activo de la semana en cada comunidad (minimo 2 posts).
Publica un mensaje de reconocimiento con sus contribuciones concretas.

- 1 reconocimiento por comunidad por semana
- Solo si el usuario top tiene >= 2 posts en los ultimos 7 dias

### Job 6: bug_detection_job — cada 4 horas

Detecta cuando 3 o mas usuarios reportan el mismo tipo de problema tecnico en 48 horas.

- Si 3-4 afectados: envia email de alerta al coordinador
- Si 5+ afectados: ademas publica un aviso tecnico en el foro

---

## Menciones directas (@Auditor IA)

Los usuarios de Moodle pueden mencionar al agente con `@Auditor` o `@Auditor IA` en cualquier
post del foro. El `mention_response_job` detecta estos posts cada 30 minutos y genera una
respuesta contextual.

**Flujo:**
1. Usuario escribe: "Hola @Auditor, tengo una duda sobre el acceso al certificado"
2. El job detecta el post (ultimas 24h, no respondido)
3. Si el contenido requiere moderacion → email al coordinador, sin publicacion
4. Si es una pregunta normal → LLM genera respuesta (max 200 palabras) + firma
5. Se publica como respuesta en el mismo hilo
6. Se marca `p.ai_answered = true` en Neo4j

**El agente responde exclusivamente a preguntas sobre ProFuturo y sus foros.**

---

## Formato y firma de mensajes

Todos los mensajes del agente terminan con:

```
---
Auditor IA ProFuturo
Mensaje generado automaticamente
```

- Sin emojis en el cuerpo ni en la firma
- Tono profesional, empatico y educativo
- Longitud maxima segun el tipo (100-400 palabras)
- En castellano

---

## Variables de entorno

| Variable | Por defecto | Descripcion |
|----------|-------------|-------------|
| `MOODLE_URL` | — | URL base de la instancia Moodle de ProFuturo |
| `MOODLE_API_TOKEN` | — | Token Web Service (credencial de ProFuturo — pendiente) |
| `MOODLE_DEFAULT_FORUM_ID` | `1` | ID del foro por defecto hasta tener el mapeo real |
| `MOODLE_SIMULATION_MODE` | `true` | Sin token no publica nada — solo loggea |
| `AUTONOMOUS_AGENT_ENABLED` | `false` | Activa/desactiva el scheduler autonomo |
| `MAX_REACTIVATIONS_PER_RUN` | `5` | Limite de reactivaciones por ciclo |
| `MAX_WELCOMES_PER_RUN` | `10` | Limite de bienvenidas por ciclo |
| `MAX_MENTIONS_PER_RUN` | `10` | Limite de respuestas a menciones por ciclo |

---

## Modo simulacion vs modo real

**Modo simulacion (MOODLE_SIMULATION_MODE=true) — configuracion por defecto:**
- Todo el flujo ejecuta normalmente (Neo4j, LLM, reglas)
- `moodle_writer.py` NO hace ninguna peticion HTTP a Moodle
- En el log aparece: `[SIMULACION] post_to_forum — discussion_id=... post_id_simulado=900001`
- Los nodos en Neo4j SI se marcan (ai_welcomed, ai_answered, etc.)
- Util para testear el flujo completo sin token real

**Modo real (MOODLE_SIMULATION_MODE=false):**
- Requiere `MOODLE_URL` y `MOODLE_API_TOKEN` configurados
- ProFuturo debe haber creado el usuario `auditor_ia` con permisos en los foros
- Los posts aparecen como publicados por ese usuario en Moodle
- Cada publicacion loggea el post_id real devuelto por la API

---

## Como activar y testear

**Paso 1 — Solo simulacion (no requiere credenciales Moodle):**
```bash
# En backend/.env
AUTONOMOUS_AGENT_ENABLED=true
MOODLE_SIMULATION_MODE=true   # ya es el valor por defecto
```

**Paso 2 — Verificar que arranca:**
```bash
uvicorn src.main:app --host 0.0.0.0 --port 8000
# El log debe mostrar: "Agente autonomo iniciado"
```

**Paso 3 — Consultar estado:**
```bash
curl http://localhost:8000/api/autonomous/status
# Muestra los 6 jobs y sus proximas ejecuciones
```

**Paso 4 — Disparar jobs manualmente:**
```bash
curl -X POST http://localhost:8000/api/autonomous/test-reactivation
curl -X POST http://localhost:8000/api/autonomous/test-welcome
curl -X POST http://localhost:8000/api/autonomous/test-mention
```

**Paso 5 — Verificar logs:**
```bash
tail -f backend/autonomous_agent.log
# Debe mostrar: candidatos encontrados, decisiones, publicaciones simuladas
```

**Paso 6 — Activar modo real (cuando ProFuturo proporcione credenciales):**
```bash
MOODLE_API_TOKEN=<token_real>
MOODLE_SIMULATION_MODE=false
MOODLE_DEFAULT_FORUM_ID=<id_real>
```

---

## Limites de seguridad

| Proteccion | Implementacion |
|-----------|---------------|
| Sin publicacion si no hay token | `MOODLE_SIMULATION_MODE=true` por defecto |
| Sin duplicados | Marcas `ai_reactivated`, `ai_welcomed`, `ai_answered` en Neo4j |
| Sin moderacion de contenido ajeno | El agente SOLO crea posts, nunca edita ni elimina |
| Escala a humano si hay conflicto | `needs_moderation_alert()` → email a coordinador, sin publicacion |
| Limite por ejecucion | `MAX_REACTIVATIONS`, `MAX_WELCOMES`, `MAX_MENTIONS` |
| Timeout por operacion | `requests.post(..., timeout=30)` en moodle_writer.py |

---

## Flujo de deploy en EC2

El agente autonomo corre dentro del mismo proceso FastAPI que el backend principal.
No requiere proceso separado.

```bash
# 1. Actualizar .env con credenciales Moodle reales
# 2. Activar agente
AUTONOMOUS_AGENT_ENABLED=true
MOODLE_SIMULATION_MODE=false

# 3. Reiniciar el backend
sudo systemctl restart profuturo-backend

# 4. Verificar estado
curl http://localhost:8000/api/autonomous/status

# 5. Monitorizar
tail -f /path/to/backend/autonomous_agent.log
```

---

## Troubleshooting

**El agente no publica nada:**
- Verificar `AUTONOMOUS_AGENT_ENABLED=true`
- Verificar `MOODLE_SIMULATION_MODE` (si es true, solo simula)
- Revisar `autonomous_agent.log` — puede que no haya candidatos que cumplan las condiciones

**Error "MOODLE_URL o MOODLE_API_TOKEN no configurados":**
- Variables de entorno no cargadas — verificar `.env` y que se hace `load_dotenv()`

**Error de Neo4j en los jobs:**
- Verificar conectividad con `curl http://localhost:8000/health`
- Los jobs tienen try/except por comunidad: un fallo no detiene las demas

**"Moodle API error: ...":**
- El token no tiene permisos suficientes para la funcion invocada
- Verificar que el Web Service de Moodle tiene activadas:
  `mod_forum_add_discussion` y `mod_forum_add_discussion_post`

**Job no se ejecuta en el horario esperado:**
- APScheduler usa la hora del servidor — verificar timezone del servidor EC2
- `GET /api/autonomous/status` muestra la proxima ejecucion en ISO format

---

## Cambios recientes del proyecto (changelog tecnico)

### Sistema de contexto obligatorio Neo4j (2026-04-30)

- **`get_mandatory_context(community)`** — nueva funcion en `agent.py` que se ejecuta en
  CADA consulta del chat, sin excepcion. Llama siempre a `get_community_kpis()`,
  `get_user_ranking(limit=10)` y `get_trending_topics(days=30)`.
- Eliminacion de la dependencia de triggers regex para datos basicos: antes, si la
  pregunta no contenia "ranking" o "KPIs", el agente respondia sin datos reales.
  Ahora siempre tiene datos actualizados de Neo4j en el contexto.
- `MAX_CONTEXT_CHARS` ampliado de 3500 a 6000 chars para acomodar el contexto obligatorio.

### Nuevas funciones Neo4j en agent.py (2026-04-29)

Funciones añadidas para enriquecer el contexto del agente:

| Funcion | Trigger | Datos |
|---------|---------|-------|
| `generate_climate_audit(community)` | AUDIT_HINTS | Totales, sentimiento, top5 autores/temas |
| `get_user_ranking(community, limit)` | RANKING_HINTS + siempre | Top N por posts |
| `get_all_posts(community, limit)` | on-demand | Posts con contenido completo |
| `analyze_engagement(community)` | ENGAGEMENT_HINTS | Tasa respuesta, distribucion actividad |
| `get_trending_topics(community, days)` | TRENDING_HINTS + siempre | Crecimiento temas |

### Validacion runtime (2026-04-29)

En `run_agent()` se loggea:
- Warning si el contexto Neo4j llegó vacio (posible fallo de conexion)
- Confirmacion cuando el contexto obligatorio se inyecto correctamente

### Sistema de historial de conversaciones (2026-04-28)

- **`backend/src/chat_history.py`**: SQLite en `backend/chat_conversations.db`
- Tablas: `conversations` (id, community, title, created_at, updated_at) + `messages` (FK cascada)
- Sidebar en el chat con historial persistente, edicion de titulos, borrado
- 5 nuevos endpoints REST: `GET/POST /api/conversations`, `GET/PATCH/DELETE /api/conversations/{id}`

### Agente autonomo (2026-04-30)

- **`backend/src/moodle_writer.py`**: wrapper REST API de Moodle con modo simulacion
- **`backend/src/autonomous_rules.py`**: reglas de decision puras (can_reactivate, should_welcome, etc.)
- **`backend/src/autonomous_agent.py`**: 6 jobs APScheduler (reactivacion, bienvenida,
  menciones, resumen semanal, reconocimiento, deteccion de bugs)
- Integrado en `main.py` con flag `AUTONOMOUS_AGENT_ENABLED`
- Endpoints de testing: `/api/autonomous/test-*` y `/api/autonomous/status`
