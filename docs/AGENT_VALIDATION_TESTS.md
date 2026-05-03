# Tests de Validación del Agente — Auditor IA ProFuturo

## Arquitectura del contexto (desde v2)

**Cambio clave:** el agente ya NO depende de triggers para obtener datos.
`get_mandatory_context()` se ejecuta en **CADA** consulta sin excepción.

```
_build_base_context(input, community)
  ├── get_forum_context()           ← siempre (posts recientes + búsqueda)
  ├── get_mandatory_context()       ← siempre (KPIs + ranking + tendencias)
  │     ├── get_community_kpis()
  │     ├── get_user_ranking(limit=10)
  │     └── get_trending_topics(days=30)
  └── [opcionales según trigger]
        ├── get_monthly_directive_report()  ← REPORT_HINTS
        ├── analyze_engagement()            ← ENGAGEMENT_HINTS
        └── generate_climate_audit()        ← AUDIT_HINTS
```

**Log esperado en TODA consulta:**
```
INFO  📊 Obteniendo contexto obligatorio de Neo4j...
INFO  ✅ Contexto obligatorio listo — 3/3 secciones obtenidas de Neo4j
INFO  ✅ Respuesta basada en datos Neo4j (contexto obligatorio inyectado)
```

---

## Test 1: Ranking de usuarios (pregunta directa)

**Input:** `"Dame el ranking de usuarios por participación"`

**Log esperado:**
```
INFO  📊 Obteniendo contexto obligatorio de Neo4j...
INFO  ✅ Contexto obligatorio listo — 3/3 secciones obtenidas de Neo4j
```

**Query manual de verificación:**
```cypher
MATCH (a:Author)-[:WROTE]->(p:Post)-[:IN_DISCUSSION]->(d:Discussion)-[:PERTAINS_TO]->(c:Community)
WHERE c.name = "Red de Líderes Innovadores"
RETURN a.name, count(p) AS posts, count(DISTINCT d) AS discussions
ORDER BY posts DESC LIMIT 10
```

**Resultado query manual:** [rellenar]

**Respuesta del agente:** [copiar aquí]

**¿Coinciden los top 3 nombres y cifras?** ✅ / ❌

---

## Test 2: Pregunta casual (sin keywords de datos)

**Input:** `"Hola, ¿qué tal está la comunidad?"`

**Verificar que también se ejecutó Neo4j:**
```
INFO  📊 Obteniendo contexto obligatorio de Neo4j...
INFO  ✅ Contexto obligatorio listo — 3/3 secciones obtenidas de Neo4j
```

**La respuesta debe incluir cifras reales** (aunque la pregunta sea informal).

**¿El agente menciona datos concretos sin que se los pidieran explícitamente?** ✅ / ❌

---

## Test 3: KPIs sin palabra "KPI"

**Input:** `"¿Cuánta gente participa aquí?"`

**Log esperado:** igual que Test 2 (obligatorio siempre)

**Query manual:**
```cypher
MATCH (a:Author)-[:WROTE]->(p:Post)-[:IN_DISCUSSION]->(:Discussion)-[:PERTAINS_TO]->(c:Community)
WHERE c.name = "Red de Líderes Innovadores"
  AND p.date >= date() - duration({days: 30})
RETURN count(DISTINCT a) AS activos_30_dias
```

**Resultado query:** [rellenar]

**¿El número del agente coincide?** ✅ / ❌

---

## Test 4: Top 3 comparación exacta

**Input:** `"Top 3 usuarios más activos de Red de Líderes Innovadores"`

**Query manual autorizada:**
```cypher
MATCH (a:Author)-[:WROTE]->(p:Post)-[:IN_DISCUSSION]->(:Discussion)
      -[:PERTAINS_TO]->(c:Community {name: "Red de Líderes Innovadores"})
RETURN a.name, count(p) AS posts
ORDER BY posts DESC LIMIT 3
```

**Resultado query:**
| Usuario | Posts |
|---------|-------|
| [?]     | [?]   |
| [?]     | [?]   |
| [?]     | [?]   |

**Respuesta del agente:**
| Usuario | Posts |
|---------|-------|
| [?]     | [?]   |
| [?]     | [?]   |
| [?]     | [?]   |

**¿Coinciden los 3 nombres y cifras exactas?** ✅ / ❌

---

## Test 5: Tendencias sin la palabra "tendencias"

**Input:** `"¿Qué temas se están hablando últimamente?"`

**Log esperado:** contexto obligatorio (incluye `get_trending_topics`)

**Query manual:**
```cypher
MATCH (:Author)-[:WROTE]->(p:Post)-[:IN_DISCUSSION]->(d:Discussion)-[:PERTAINS_TO]->(c:Community)
WHERE c.name = "Red de Líderes Innovadores"
  AND p.date >= date() - duration({days: 30})
RETURN d.topic AS topic, count(p) AS posts
ORDER BY posts DESC LIMIT 10
```

**Resultado query:** [rellenar]

**¿Los temas mencionados por el agente coinciden?** ✅ / ❌

---

## Test 6: Engagement con trigger

**Input:** `"¿Cuál es la tasa de respuesta en los hilos?"`

**Log adicional esperado** (trigger ENGAGEMENT_HINTS activo):
```
INFO  Funciones adicionales activadas por trigger: ['analyze_engagement']
```

**Query manual:**
```cypher
MATCH (d:Discussion)-[:PERTAINS_TO]->(c:Community)
WHERE c.name = "Red de Líderes Innovadores"
OPTIONAL MATCH (a:Author)-[:WROTE]->(:Post)-[:IN_DISCUSSION]->(d)
WITH d, count(DISTINCT a) AS unique_authors
RETURN count(d) AS total_discussions,
       sum(CASE WHEN unique_authors > 1 THEN 1 ELSE 0 END) AS with_response
```

**Resultado query:** [rellenar]

**¿Tasa del agente coincide?** ✅ / ❌

---

## Test 7: Frases prohibidas

**Verificar que el agente NO diga:**
- "basándome en lo que veo"
- "según los mensajes visibles"
- "en la pantalla"
- "puedo ver que"
- "no tengo acceso a los datos"
- "no dispongo de información"

**Método:** Ejecutar los 6 tests anteriores y revisar las respuestas.

**Resultado:** [0 apariciones / N apariciones — indicar cuáles]

---

## Tabla resumen de resultados

| Test | Neo4j en logs | Datos correctos | Frases prohibidas |
|------|--------------|-----------------|-------------------|
| T1 — Ranking (directo)         | ✅/❌ | ✅/❌ | ✅/❌ |
| T2 — Saludo casual             | ✅/❌ | ✅/❌ | ✅/❌ |
| T3 — Activos sin keyword       | ✅/❌ | ✅/❌ | ✅/❌ |
| T4 — Top 3 exacto              | ✅/❌ | ✅/❌ | ✅/❌ |
| T5 — Tendencias sin keyword    | ✅/❌ | ✅/❌ | ✅/❌ |
| T6 — Engagement con trigger    | ✅/❌ | ✅/❌ | ✅/❌ |

---

## Funciones Neo4j en agent.py

### Obligatorias (todas las consultas)
| Función | Datos que consulta |
|---------|-------------------|
| `get_forum_context` | Posts recientes + búsqueda por hint |
| `get_community_kpis` | Miembros activos, variación mensual, roles top 3 |
| `get_user_ranking` | Top 10 usuarios por posts + discusiones |
| `get_trending_topics` | Crecimiento temas (30 días vs 30 anteriores) |

### Opcionales (trigger regex)
| Función | Trigger | Datos que consulta |
|---------|---------|-------------------|
| `get_monthly_directive_report` | `REPORT_HINTS` | 800 posts, KPIs mensuales históricos |
| `analyze_engagement` | `ENGAGEMENT_HINTS` | Distribución actividad, tasa respuesta |
| `generate_climate_audit` | `AUDIT_HINTS` | Auditoría completa: totales, sentimiento, top5 |
| `evaluate_contributions` | `RUBRIC_HINTS` | Rúbrica pedagógica LLM sobre posts reales |
