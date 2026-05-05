# Agente Autonomo ProFuturo

El sistema tiene dos capas de automatizacion que funcionan en paralelo:
- **RPA** — solo lectura + email. No escribe en Moodle.
- **Agente Moodle** — lee Neo4j, genera texto con el LLM y publica en foros.

---

## RPA — Alertas por email

Scheduler bloqueante (`rpa.py`). Activo siempre que corra el backend.

| Job | Frecuencia | Que hace | Que genera |
|-----|------------|----------|------------|
| `critical_monitor_job` | cada 30 min | Detecta posts con lenguaje de crisis, acoso o problemas técnicos graves | Email de alerta urgente + PDF adjunto al coordinador |
| `unanswered_monitor_job` | cada 6 h | Detecta hilos sin respuesta durante más de N días | Email con listado de hilos abandonados |
| `disconnection_risk_job` | lunes 08:00 | Identifica usuarios antes activos que llevan semanas sin publicar | Email con lista de usuarios en riesgo de abandono |
| `trending_topics_job` | viernes 17:00 | Detecta temas con pico de actividad esta semana | Email con ranking de temas en auge |
| `weekly_summary_job` | viernes 18:00 | Consolida métricas de la semana (posts, usuarios, incidencias) | Email con resumen ejecutivo semanal en PDF |

---

## Agente Moodle — Publicacion en foros

Scheduler en background (`autonomous_agent.py`). Solo activo si `AUTONOMOUS_AGENT_ENABLED=true`.

| Job | Frecuencia | Que hace | Publica en Moodle |
|-----|------------|----------|-------------------|
| `reactivation_job` | cada 6 h | Detecta hilos con 0 respuestas y 7-14 días de antigüedad, genera mensaje de reactivación | Respuesta en el hilo (`mod_forum_add_discussion_post`) |
| `welcome_job` | cada 2 h | Detecta usuarios con su primer post (≤ 2 días), genera bienvenida personalizada | Respuesta en su primer hilo |
| `mention_response_job` | cada 30 min | Detecta posts con `@Auditor` sin respuesta, genera respuesta contextual | Respuesta en el hilo mencionado |
| `weekly_digest_post_job` | viernes 17:00 | Genera resumen semanal de actividad por comunidad | Nueva discusión por comunidad (`mod_forum_add_discussion`) |
| `recognition_job` | lunes 09:00 | Identifica el usuario más activo de la semana, genera mensaje de reconocimiento | Nueva discusión de reconocimiento |
| `bug_detection_job` | cada 4 h | Detecta cuando 3+ usuarios reportan el mismo problema técnico en 48 h | Aviso técnico si hay 5+ afectados; email al coordinador siempre |

---

## Que se necesita de Moodle

### Usuario "Auditor IA"
- Crear usuario con username `auditor_ia` en la instancia ProFuturo
- Asignar rol custom con permisos de escritura en foros (sin acceso a calificaciones ni configuración)

### Web Service Token
- Activar Web Services en Moodle: `Administración > Plugins > Web Services`
- Crear token para `auditor_ia` con las funciones:

```
mod_forum_get_forums_by_courses       (leer foros de un curso)
mod_forum_get_forum_discussions       (leer discusiones)
mod_forum_get_forum_discussion_posts  (leer posts)
mod_forum_add_discussion_post         (responder en hilo)
mod_forum_add_discussion              (crear nueva discusión)
```

- Copiar el token en `.env`: `MOODLE_API_TOKEN=wsxxxxxxxxxxxxxxxx`

---

## Integracion API LLM ↔ Moodle

```
Neo4j (contexto)
     │
     ▼
LLM SageMaker (genera texto)
     │
     ▼
moodle_writer.py ──▶ Moodle REST API ──▶ Foro ProFuturo
```

### Opcion A: Backend centralizado (implementacion actual)

Nuestro backend en EC2 consulta Neo4j + LLM y publica via API REST de Moodle.

- Ventaja: control total, logs centralizados, fácil de activar/desactivar
- Se activa por foro mediante `MOODLE_SYNC_COURSE_IDS` en `.env`

### Opcion B: Plugin Moodle nativo (alternativa futura)

Plugin PHP dentro de Moodle que llama a nuestra API `/api/chat` por cada evento de foro.

- Ventaja: gestión desde el panel de administración de Moodle, familiar para admins de ProFuturo
- Cada foro tiene checkbox "Activar Auditor IA" en su configuración
- Requiere: desarrollar plugin PHP + exponer endpoint público del LLM con autenticación

---

## Activar/desactivar por foro

**Opcion inmediata (`.env`):**
```env
MOODLE_SYNC_COURSE_IDS=101,102,103   # solo estos cursos reciben posts del agente
AUTONOMOUS_AGENT_ENABLED=true
MOODLE_SIMULATION_MODE=false          # false = publica de verdad
```

**Opcion futura (endpoint de configuracion):**
```
POST /api/autonomous/config
{ "forum_ids": [101, 102], "enabled": true }
```
Almacena la lista en Neo4j o en la BD SQLite de conversaciones.
El agente comprueba esta lista antes de publicar en cada foro.
