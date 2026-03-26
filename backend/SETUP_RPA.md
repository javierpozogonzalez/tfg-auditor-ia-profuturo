# Setup RPA con Ollama Local

## Prerequisites

1. Ollama instalado y ejecutándose
2. Modelo "profuturo-auditor" descargado en Ollama
3. Neo4j funcionando
4. Backend venv activado

## Estructura de Cambios

### 1. llm_config.py (MODIFICADO)
- Eliminado: ChatBedrock (AWS)
- Agregado: ChatOllama para ejecutar modelo local
- Configuración via variables de entorno

### 2. tools.py (EXTENDIDO)
- Mantiene: generate_report_pdf()
- Nuevo: generate_critical_alert_pdf() para alertas de severidad crítica

### 3. rpa.py (NUEVO)
- Script de background scheduling con APScheduler
- Dos tareas programadas:
  - weekly_summary_job: cada viernes a las 18:00
  - critical_monitor_job: cada 30 minutos

## Instalación

### Paso 1: Configurar variables de entorno

Copia .env.example a .env y completa valores:

```bash
cd backend
cp .env.example .env
```

Edita backend/.env:
```
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=<tu_contraseña_neo4j>

OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL_NAME=profuturo-auditor
LLM_TEMPERATURE=0.1
```

### Paso 2: Instalar dependencias nuevas

```bash
cd backend
source venv/bin/activate
pip install -r requirements.txt
```

Las librerías nuevas:
- langchain-community (ChatOllama)
- apscheduler (background scheduling)

### Paso 3: Descargar modelo Ollama

Si aún no tienes el modelo "profuturo-auditor":

```bash
ollama pull profuturo-auditor
```

O si usas un modelo diferente, actualiza OLLAMA_MODEL_NAME en .env:

```bash
ollama pull mistral
ollama pull llama2
ollama pull neural-chat
```

### Paso 4: Verificar Ollama está corriendo

```bash
curl http://localhost:11434/api/tags
```

Debe retornar JSON con los modelos disponibles.

## Ejecución

### Opción A: Ejecutar RPA en terminal

```bash
cd backend
source venv/bin/activate
python scripts/rpa.py
```

Salida esperada:
```
[2026-03-21T18:30:45.123456] RPA Scheduler iniciado
```

### Opción B: Ejecutar RPA en background

```bash
cd backend
source venv/bin/activate
nohup python scripts/rpa.py > logs/rpa.log 2>&1 &
```

### Opción C: Ejecutar backend + RPA en paralelo

Terminal 1 (Backend API):
```bash
cd backend
source venv/bin/activate
python -m uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

Terminal 2 (RPA Worker):
```bash
cd backend
source venv/bin/activate
python scripts/rpa.py
```

## Verificar funcionamiento

### Logs

Todos los PDFs generados se guardan en: `backend/alerts/`

```bash
ls backend/alerts/
```

Tipos de archivos:
- `Resumen_Semanal_*.pdf` - Resúmenes semanales (viernes 18:00)
- `ALERTA_*.pdf` - Alertas críticas (cada 30 minutos)

### Probar jobs manualmente (desarrollo)

Edita backend/scripts/rpa.py y en la parte inferior:

```python
if __name__ == "__main__":
    print("Testing weekly_summary_job...")
    weekly_summary_job()
    
    print("\nTesting critical_monitor_job...")
    critical_monitor_job()
```

Luego ejecuta:
```bash
python scripts/rpa.py
```

## Configurar frecuencias (opcional)

En backend/scripts/rpa.py:

### Cambiar horario del resumen semanal:
```python
CronTrigger(day_of_week='fri', hour=18, minute=0),
```

Ejemplos:
- Todos los días a medianoche: `CronTrigger(hour=0, minute=0)`
- Cada lunes 09:00: `CronTrigger(day_of_week='mon', hour=9, minute=0)`
- Cada 6 horas: `IntervalTrigger(hours=6)`

### Cambiar frecuencia del monitor crítico:
```python
IntervalTrigger(minutes=30),
```

Ejemplos:
- Cada 10 minutos: `IntervalTrigger(minutes=10)`
- Cada hora: `IntervalTrigger(hours=1)`
- Cada 6 horas: `IntervalTrigger(hours=6)`

## Estructura de alertas generadas

### Resumen Semanal (generate_report_pdf)
- Título editado
- Contenido markdown convertido a HTML
- Logo ProFuturo en encabezado

### Alerta Crítica (generate_critical_alert_pdf)
- Header en rojo con "ALERTA CRITICA"
- Severidad de color: rojo (crítica), naranja (alta), amarillo (media), azul (baja)
- Comunidad afectada
- Timestamp de generación
- Issue summary (problemas detectados)
- Acciones recomendadas (5 pasos)

## Palabras clave que disparan alertas

El critical_monitor_job detecta automáticamente:

**Palabras de odio/acoso:**
- odio, hate, odia, insulto, insult
- acoso, harassment, bully, bullying

**Palabras de urgencia:**
- crisis, emergency, urgente, urgent
- danger, peligro, muerto, dead
- muerte, death, suicida, suicide

**Malware/Tech:**
- spam, malware, virus, bloqueado, blocked

Personaliza `critical_keywords` en rpa.py para tu contexto.

## Troubleshooting

### Error: "Connection refused to localhost:11434"
Verifica que Ollama está ejecutándose:
```bash
ollama serve
```

### Error: "Model 'profuturo-auditor' not found"
Descarga el modelo:
```bash
ollama pull profuturo-auditor
```

### Error: "Neo4j connection failed"
Verifica credenciales de .env y que Neo4j está corriendo:
```bash
neo4j status
```

### PDFs no se generan
Verifica que `backend/alerts/` existe o crea:
```bash
mkdir -p backend/alerts
```

### APScheduler no ejecuta jobs
Asegúrate que el script sigue ejecutándose (no está pausado).
Verifica logs en terminal para errores.

## Notas importantes

1. **RPA es blocking**: El script mantiene el proceso vivo. Para detener usa `Ctrl+C`.

2. **Timestamps de ejecución**: Los logs muestran ISO format con fecha/hora completa.

3. **LLM Performance**: Ollama local puede ser más lento que APIs cloud. 
   - Aumenta timeout si es necesario en agent.py

4. **Almacenamiento de PDFs**: backend/alerts/ puede crecer. Implementa rotación si es necesario.

5. **Neo4j Query Performance**: Los jobs hacen muchas queries. Asegúrate índices están creados:
   ```cypher
   CREATE INDEX ON :Author(name)
   CREATE INDEX ON :Post(date)
   CREATE INDEX ON :Community(name)
   ```

## Desactivar/activar jobs

Para desactivar un job sin eliminar el código:

```python
scheduler.pause_job('weekly_summary_job')
scheduler.pause_job('critical_monitor_job')
```

Para reactivar:

```python
scheduler.resume_job('weekly_summary_job')
scheduler.resume_job('critical_monitor_job')
```

## Monitoreo en Producción

Para monitoreo persistente, considera:

```bash
# systemd service
# supervisor 
# pm2 (Node.js)
# Docker container
```

O usa el comando simple con nohup mencionado arriba.
