# Lógica Inteligente del RPA

## Filosofía
El RPA debe ser útil, no spam. Genera alertas solo cuando aportan valor real.
Cada job es **consolidado** (1 email por ciclo máximo) e **inteligente** (no actúa sin datos suficientes).

---

## Comportamiento por Job

### `weekly_summary` — Viernes 18:00
- **Siempre consolidado:** recorre todas las comunidades activas en un solo ciclo
- **Incluye:** solo comunidades con actividad en el periodo (365 días en testing, 7 en producción)
- **Output:** 1 PDF + 1 email con resumen ejecutivo global y análisis por comunidad
- **Prompt:** estructura fija: Resumen Ejecutivo → Análisis por Comunidad → Recomendaciones Transversales → Propuestas de Formación

### `critical_monitor` — Cada 30 minutos
- **Lógica batch:** recorre todas las comunidades en el mismo ciclo y agrupa incidencias
- **Filtro de severidad:** solo alerta si el LLM clasifica CRITICA o ALTA (descarta MEDIA/BAJA)
- **Si 1 comunidad:** PDF específico con nombre de la comunidad
- **Si varias:** PDF consolidado `ALERTA_CONSOLIDADA_*.pdf`
- **Output:** 0 o 1 email por ciclo (nunca varios)
- **Patrones TESTING:** incluye `gracias|agradec|felicit` para forzar detección

### `unanswered_monitor` — Cada 6 horas
- **Umbral mínimo:** solo actúa si hay ≥5 hilos sin respuesta en total (suma de todas las comunidades)
- **Siempre consolidado:** 1 PDF con secciones por comunidad
- **Output:** 0 o 1 email por ciclo
- **Umbral TESTING:** `UNANSWERED_DAYS = 365` (captura todos los hilos históricos)

### `disconnection_risk` — Lunes 08:00
- **Consolidado:** 1 PDF con secciones independientes por comunidad
- **Incluye por comunidad:**
  - Usuarios antes activos que llevan ≥21 días sin publicar (habiendo publicado en los últimos 90)
  - Recién llegados con un solo post (≥3 para activar la sección)
- **Output:** 0 o 1 email por ciclo
- **Cierre del PDF:** recomendaciones transversales para todas las comunidades

### `trending_topics` — Viernes 17:00
- **Filtro de significancia:** solo reporta si hay ≥3 temas con crecimiento >50% en alguna comunidad
- **Crecimiento infinito** (tema nuevo con ≥3 posts) también cuenta como significativo
- **Siempre consolidado:** 1 PDF con secciones por comunidad + análisis estratégico del LLM
- **Output:** 0 o 1 email por ciclo (silencioso si no hay cambios)
- **Periodos TESTING:** ventana actual 60 días, histórico 120 días

---

## Umbrales en TESTING vs Producción

| Parámetro | TESTING | Producción |
|-----------|---------|------------|
| `UNANSWERED_DAYS` | 365 | 2 |
| `weekly_summary` días | 365 | 7 |
| `critical_monitor` días | 365 | 1 |
| `trending_topics` ventana | 60 / 120 días | 7 / 14 días |

---

## Resultado esperado (producción)

| Job | Emails/semana (típico) |
|-----|------------------------|
| `weekly_summary` | 1 (siempre) |
| `critical_monitor` | 0–2 (solo incidencias reales) |
| `unanswered_monitor` | 0–1 (solo si acumula ≥5 hilos) |
| `disconnection_risk` | 1 (lunes, si hay datos) |
| `trending_topics` | 0–1 (viernes, solo si hay cambios) |

**No spam. Contextual. Accionable.**
