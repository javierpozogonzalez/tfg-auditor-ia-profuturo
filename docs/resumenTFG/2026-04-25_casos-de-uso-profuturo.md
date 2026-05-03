# 2026-04-25 — Integración de casos de uso oficiales ProFuturo

## Contexto

El MVP de ProFuturo define 10 casos de uso en 2 bloques. Se realizó un análisis completo del código existente y se implementaron los casos pendientes en esta sesión. Los casos 1.3 (Excel + gráficos) y 1.1 (búsqueda multilingüe) quedan fuera del alcance del TFG por dependencia de librerías externas de visualización y traducción.

---

## Cambios implementados

### `backend/src/agent.py`

**Caso 1.2 completado** — KPIs cuantitativos de comunidad:
- Añadida constante `MEMBER_HINTS` (regex): detecta consultas sobre miembros, líderes, expertos, conectores, riesgo, abandono, evaluación, participación.
- Añadida función `get_community_kpis(community)`: ejecuta 6 queries Cypher que calculan:
  - Total de miembros (`Author` únicos)
  - % miembros activos en los últimos 30 días
  - Actividad mes anterior (30–60 días) y variación mensual
  - Líderes: top 3 autores por número de publicaciones
  - Conectores: top 3 autores por número de discusiones distintas
  - Expertos: top 3 autores por longitud media de contenido (indicador de contribuciones elaboradas)
- Actualizada `_build_base_context()`: incluye `get_community_kpis()` cuando `MEMBER_HINTS` detecta consultas relevantes.

**Caso 2.2 parcial** — Detección de roles en el grafo incluida en `get_community_kpis()` (líderes, conectores, expertos). La evaluación por rúbrica semántica (pertinencia pedagógica, argumentación) requeriría LLM por post individual y queda fuera del alcance.

---

### `backend/scripts/rpa.py`

**Caso 2.6 completado** — `SUMMARY_PROMPT` actualizado con sección `## Propuestas de Formacion Recomendadas`: el resumen semanal automático ahora incluye 2–4 propuestas concretas de formación basadas en los temas y dudas de la semana (tema, motivo, formato sugerido).

**Caso 2.1 implementado** — Nuevos patrones de detección:
- `DOUBT_PATTERNS`: 16 expresiones de duda (no entiendo, duda, pregunta, cómo funciona, etc.)
- `SUGGESTION_PATTERNS`: 12 expresiones de sugerencia (propongo, sugerencia, sería bueno, mejora, etc.)
- `doubt_suggestion_monitor_job()`: analiza el feed diario, separa dudas de sugerencias, genera resumen LLM y envía email al administrador.

**Caso 2.3 implementado** — `trending_topics_job()`: compara frecuencia de topics en última semana vs semana anterior (usando `Counter`), identifica los 5 más crecientes, genera análisis LLM y publica en el foro (Neo4j). Programado los viernes a las 17:00.

**Caso 2.4 implementado** — Helper `get_unanswered_discussions(days_threshold)` y `unanswered_monitor_job()`: detecta discusiones sin actividad en N días (por defecto 2), genera informe PDF y envía alerta por email. Activo cada 6 horas.

**Caso 2.5 implementado** — Helper `get_disconnection_risk(community)` y `disconnection_risk_job()`: identifica (a) autores con ≥3 posts en los últimos 90 días pero ninguno en los últimos 21, y (b) recién llegados con un solo post. Genera informe PDF con recomendaciones de reactivación. Programado los lunes a las 8:00.

**Caso 2.7 implementado** — `MATERIAL_PATTERNS` (15 expresiones: curso, formación, módulo, recurso, guía, etc.) y `material_feedback_monitor_job()`: escanea el feed semanal, detecta opiniones sobre materiales formativos (mínimo 3 menciones), genera análisis diferenciando valoraciones positivas/negativas y genera PDF con alerta si hay críticas graves. Programado (comentado, pendiente validación con datos reales).

**Nuevas constantes de configuración:**
```python
UNANSWERED_DAYS      = 2   # días sin actividad para alerta
DISCONNECTION_ACTIVE = 90  # ventana histórica "antes activo"
DISCONNECTION_IDLE   = 21  # días sin publicar = en riesgo
```

**Scheduler actualizado — 5 jobs activos:**
| Job | Frecuencia |
|-----|-----------|
| `weekly_summary` | Viernes 18:00 |
| `critical_monitor` | Cada 30 min |
| `unanswered_monitor` | Cada 6 horas |
| `disconnection_risk` | Lunes 8:00 |
| `trending_topics` | Viernes 17:00 |

**2 jobs pendientes de validación (comentados):**
- `doubt_suggestion_monitor` — diario 9:30, pendiente ajuste de patrones con datos reales
- `material_feedback_monitor` — miércoles 10:00, pendiente ajuste de umbrales

---

### `backend/src/main.py`

- Import actualizado para incluir los 3 nuevos jobs.
- `rpa_trigger` endpoint: `allowed` expandido a 5 jobs (`critical_monitor`, `weekly_summary`, `unanswered_monitor`, `disconnection_risk`, `trending_topics`). Usa `_fn_map` dict en lugar de condicional binario.

---

## Estado final de los casos de uso

| # | Caso de uso | Estado tras esta sesión |
|---|-------------|------------------------|
| 1.1 | Selección múltiple + búsqueda multilingüe | PARCIAL (sin capa de traducción) |
| 1.2 | Informe por objetivos con KPIs | IMPLEMENTADO |
| 1.3 | Informes en Excel con gráficos | FUERA DE ALCANCE TFG |
| 2.1 | Detección dudas/sugerencias en feed | IMPLEMENTADO |
| 2.2 | Evaluador por rúbrica + roles en grafo | PARCIAL (roles implementados) |
| 2.3 | Monitorización temas emergentes | IMPLEMENTADO |
| 2.4 | Alertas hilos sin respuesta | IMPLEMENTADO |
| 2.5 | Detección usuarios en riesgo abandono | IMPLEMENTADO |
| 2.6 | Tendencias → propuestas formación | IMPLEMENTADO |
| 2.7 | Feedback sobre materiales formativos | IMPLEMENTADO |
