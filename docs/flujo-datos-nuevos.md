# Como el agente lee los datos nuevos de los foros

## Respuesta corta

El agente lee Neo4j en tiempo real en cada consulta. No hay cache. Cuando un nuevo mensaje aparece en Neo4j, la siguiente pregunta al agente ya lo incluye automaticamente. Lo unico que no es automatico todavia es la **ingestion de datos**: pasar los mensajes de los foros de Pinchtab a Neo4j.

---

## Flujo completo de datos

```
[Foros de ProFuturo en Pinchtab]
        |
        | Paso 1: Extraccion (pendiente de automatizar)
        v
[Script de ingestion / scraper]
        |
        | Paso 2: Carga en Neo4j
        v
[Neo4j — grafo de conocimiento]
        |
        | Paso 3: Lectura en tiempo real (ya implementado)
        v
[Auditor IA — cada consulta hace MATCH en Neo4j]
```

### Paso 1 — Extraccion de datos de Pinchtab (pendiente)

Pinchtab es la plataforma de foros que usa ProFuturo. Para que el agente lea mensajes nuevos, hay que extraerlos de Pinchtab y cargarlos en Neo4j. Hay dos enfoques:

**Opcion A — API de Pinchtab (ideal)**
Si Pinchtab expone una API REST o webhook, se puede crear un job en el RPA scheduler que cada X horas llame a esa API, obtenga los mensajes nuevos y los inserte en Neo4j. Este job seria similar a `critical_monitor_job` pero enfocado en ingestion.

**Opcion B — Scraping web (alternativa)**
Si no hay API, se puede usar `selenium` o `playwright` para navegar por los foros autenticado y extraer el HTML. Mas fragil que una API pero funciona si Pinchtab no ofrece acceso programatico.

**Estado actual del MVP:**
Los datos de los foros se cargaron manualmente mediante el script `backend/scripts/clean_data.py` (limpieza del CSV exportado de Pinchtab) y el script de ingestion (eliminado tras la migracion al nuevo schema). Para el MVP de entrega, este paso se hizo una vez con los datos historicos. La automatizacion continua es trabajo futuro que depende de lo que ProFuturo proporcione (acceso API, exportaciones periodicas, etc.).

### Paso 2 — Schema de Neo4j

Los datos se almacenan en un grafo con este schema:

```
(:Author)-[:WROTE]->(:Post)-[:IN_DISCUSSION]->(:Discussion)-[:PERTAINS_TO]->(:Community)
```

| Nodo | Propiedades clave |
|------|------------------|
| `Author` | `name` |
| `Post` | `id`, `content`, `date`, `sentiment` |
| `Discussion` | `topic` |
| `Community` | `name` |

Cualquier herramienta que inserte nodos y relaciones con este schema es compatible con el agente sin cambios.

### Paso 3 — Lectura en tiempo real (ya implementado)

El agente ejecuta queries Cypher a Neo4j en cada consulta del chat:

```cypher
MATCH (a:Author)-[:WROTE]->(p:Post)-[:IN_DISCUSSION]->(d:Discussion)-[:PERTAINS_TO]->(c:Community)
WHERE c.name = $community
RETURN a.name, p.content, d.topic
ORDER BY p.date DESC LIMIT 20
```

No hay cache de mensajes. En cuanto un post nuevo existe en Neo4j, el agente lo incluye en su contexto en la siguiente consulta. No hace falta reiniciar nada.

---

## Y el modelo de IA? se actualiza solo?

No. El modelo (Qwen 2.5 7B fine-tuneado con QLoRA) es estatico una vez desplegado. No aprende de los nuevos mensajes automaticamente.

Lo que si es automatico y en tiempo real es el **contexto** que recibe el modelo: los mensajes recientes del foro se inyectan en cada prompt como contexto (GraphRAG). El modelo no aprende, pero si ve los datos nuevos en cada consulta.

### Cuando tendria sentido reentrenar el modelo

El fine-tuning actual (QLoRA 4-bit sobre Qwen 2.5 7B) se entrenara con datos de ProFuturo para que el modelo entienda el dominio, el tono institucional y las casuisticas especificas de los foros. Una vez en produccion, re-entrenar tendria sentido si:

- Cambian significativamente los tipos de consultas que hacen los administradores
- El modelo comete errores sistematicos en casos de uso especificos
- Hay suficientes nuevos datos etiquetados de alta calidad para mejorar el dataset

El ciclo de re-entrenamiento seria:
1. Exportar nuevos ejemplos de consulta/respuesta de calidad
2. Preparar el dataset QLoRA con `backend/preparar_dataset.py` (o el script equivalente)
3. Lanzar el job de training en SageMaker (`ml.g5.2xlarge`) con el script `backend/train.py`
4. Evaluar el nuevo modelo y, si mejora, actualizar el endpoint TGI con el nuevo artefacto en S3

---

## En produccion con AWS: es todo "magia"?

Si — una vez desplegado en EC2 y con la ingestion automatizada, el ciclo completo es:

```
Docente publica en Pinchtab
        → scraper/webhook ingesta el post en Neo4j (automatico)
        → RPA critical_monitor lo analiza en los proximos 30 min (automatico)
        → si es critico, el admin recibe email con PDF de alerta (automatico)
        → si un admin abre el chat y pregunta "que paso esta semana", 
          el agente ya tiene ese post en su contexto (automatico)
```

Lo unico que necesita intervencion humana es:
- Que ProFuturo proporcione el mecanismo de extraccion de Pinchtab (API o acceso)
- Que el equipo tecnico configure el `.env` en la instancia EC2 con las URIs y credenciales correctas

### Conectividad con la base de datos en produccion

Si Neo4j esta en la red interna de ProFuturo (lo mas probable para proteger los datos de los docentes), la instancia EC2 conectara a Neo4j mediante:

- **VPN Site-to-Site** entre AWS y el datacenter de ProFuturo, o
- **Neo4j AuraDB** (instancia cloud de Neo4j que ProFuturo gestionaria), o
- **EC2 en la misma VPC** que el servidor Neo4j si ProFuturo ya tiene infraestructura en AWS

En cualquier caso, solo cambia el valor de `NEO4J_URI` en el `.env`. El codigo no cambia.

---

## Resumen ejecutivo para ProFuturo

| Pregunta | Respuesta |
|----------|-----------|
| El agente ve los mensajes nuevos automaticamente? | Si, en tiempo real desde Neo4j |
| Hay que reiniciar algo cuando hay datos nuevos? | No |
| La ingestion de Pinchtab a Neo4j es automatica? | Pendiente — necesitamos acceso a la API de Pinchtab |
| El modelo de IA aprende solo? | No — el contexto es dinamico pero el modelo es estatico |
| Cuando habria que reentrenar el modelo? | Solo si cambian significativamente los patrones de uso |
| Donde corre el sistema en produccion? | EC2 (backend + scheduler) + SageMaker (LLM) + Neo4j |
| Necesita VPN? | Solo si Neo4j esta en red interna de ProFuturo |
