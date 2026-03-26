# ProFuturo AI Analytics Dashboard

**Sistema de auditoría y análisis de inteligencia artificial para comunidades educativas**

---

## Tabla de Contenidos

1. [Descripción General](#descripción-general)
2. [Características Principales](#características-principales)
3. [Arquitectura del Proyecto](#arquitectura-del-proyecto)
4. [Stack Tecnológico](#stack-tecnológico)
5. [Backend - Análisis Técnico](#backend---análisis-técnico)
6. [API REST - Integración Frontend-Backend](#api-rest---integración-frontend-backend)
7. [Instalación y Configuración](#instalación-y-configuración)
8. [Ejecución](#ejecución)

---

## Descripción General

ProFuturo AI Analytics es una solución integral de inteligencia artificial diseñada para analizar y auditar comunidades educativas en línea. El sistema proporciona:

- **Análisis de Sentimientos**: Evaluación del clima y engagement en foros educativos
- **Reportes Inteligentes**: Generación automática de reportes ejecutivos en PDF
- **Visualización Gráfica**: Grafos de interacción entre usuarios y temas
- **IA Conversacional**: Agente IA que responde preguntas basadas en datos reales
- **Panel Administrativo**: Dashboard intuitivo para moderadores y gestores

---

## Características Principales

### Frontend (Next.js 16 + TypeScript)
- Dashboard responsivo con panel lateral y área principal
- Panel de visualización de datos (feed de mensajes, grafo de interacciones)
- Chat interactivo con IA integrado
- Generación y descarga de reportes PDF
- Filtrado dinámico por comunidades educativas
- Interfaz moderna con Tailwind CSS y shadcn/ui

### Backend (FastAPI + Python 3.14)
- API REST de alta performance
- Agente IA con capacidades de razonamiento (LangGraph)
- Base de datos gráfica (Neo4j) para relaciones complejas
- Generación dinámica de PDFs con marca de agua
- Procesamiento asincrónico de consultas
- Soporte para carga de archivos (CSV, PDF)

### Datos y Inteligencia
- Base de datos Neo4j con nodos: Author, Post, Discussion, Community
- Análisis de sentimientos en tiempo real
- Cálculo automático de KPIs mensuales
- Embeddings vectoriales con Ollama (opcional)
- Modelo LLM: Claude Sonnet 4.5 (AWS Bedrock)

---

## Arquitectura del Proyecto

```
tfg/
├── app/                              # Frontend Next.js App Router
│   ├── page.tsx                      # Página principal del dashboard
│   ├── layout.tsx                    # Layout root con metadata
│   ├── globals.css                   # Estilos globales
│   └── favicon.ico                   # Icono ProFuturo
│
├── components/                       # Componentes React reutilizables
│   ├── dashboard/
│   │   ├── ai-chat.tsx              # Panel de chat con IA (ancho: 560px)
│   │   ├── data-panel.tsx           # Panel de datos (feed + grafo)
│   │   ├── sidebar.tsx              # Sidebar con filtros y acciones
│   │   ├── forum-feed.tsx           # Feed de puntos de fofo
│   │   └── interaction-graph.tsx    # Visualización de interacciones
│   └── ui/                           # Componentes shadcn (button, input, etc.)
│
├── lib/                              # Utilerías y contextos
│   ├── community-context.tsx        # Estado global de comunidad seleccionada
│   └── utils.ts                      # Funciones de utilidad
│
├── public/                           # Assets estáticos
│   └── logo.png                      # Logo ProFuturo
│
├── backend/                          # Backend FastAPI Python
│   ├── src/
│   │   ├── main.py                  # Aplicación FastAPI principal
│   │   │   ├── /health              # Endpoint de salud
│   │   │   ├── /api/chat            # Chat con IA (POST)
│   │   │   ├── /api/chat-with-file  # Chat con archivo adjunto (POST)
│   │   │   ├── /api/communities     # Lista comunidades disponibles (GET)
│   │   │   ├── /api/feed            # Feed de mensajes (GET)
│   │   │   └── /api/graph           # Grafo de interacciones (GET)
│   │   │
│   │   ├── agent.py                 # Agente IA (LangGraph + Tools)
│   │   │   ├── get_monthly_directive_report  # Herramienta: genera reportes
│   │   │   ├── get_forum_context             # Herramienta: extrae contexto
│   │   │   ├── run_agent()          # Ejecuta el agente con consulta
│   │   │   └── _apply_current_report_dates() # Aplica fechas dinámicas
│   │   │
│   │   ├── tools.py                 # Herramientas de procesamiento
│   │   │   └── generate_report_pdf() # Genera PDF con logo y formato
│   │   │
│   │   ├── llm_config.py            # Configuración del modelo LLM
│   │   │   └── get_llm()            # Retorna instancia de Claude
│   │   │
│   │   └── neo4j_client.py          # Utilidades Neo4j
│   │
│   ├── scripts/
│   │   ├── ingest.py                # ETL: Carga datos CSV a Neo4j
│   │   ├── prepare_finetuning_dataset.py   # Genera dataset JSONL QA
│   │   ├── clean_data.py            # Limpieza de datos
│   │   └── test_db.py               # Validación de conexión
│   │
│   ├── data/
│   │   ├── datos_profuturo.csv      # Dataset original
│   │   └── dataset_profuturo.jsonl  # Dataset para fine-tuning
│   │
│   ├── requirements.txt              # Dependencias Python
│   └── venv/                        # Entorno virtual Python
│
└── package.json                      # Dependencias Node.js
```

---

## Stack Tecnológico

### Frontend
| Librería | Versión | Propósito |
|----------|---------|----------|
| Next.js | 16.1.6 | Framework React con App Router |
| React | 18.x | Librería UI |
| TypeScript | 5.x | Tipado estático |
| Tailwind CSS | 3.x | Estilos utilitarios |
| shadcn/ui | Latest | Componentes accesibles |
| Lucide Icons | Latest | Iconografía |
| React Markdown | Latest | Renderizado de markdown |

### Backend
| Librería | Versión | Propósito |
|----------|---------|----------|
| FastAPI | 0.115.0 | Framework API REST |
| Uvicorn | 0.32.0 | Servidor ASGI |
| Pydantic | 2.x | Validación de datos |
| Neo4j Driver | 5.26.0 | Cliente de base de datos gráfica |
| LangChain Core | 0.3.x | Orquestación de IA |
| LangGraph | 0.2.x | Agente de razonamiento |
| fpdf2 | 2.8.2 | Generación de PDFs |
| python-dotenv | 1.0.1 | Gestión de variables .env |

### Infraestructura
| Componente | Versión | Propósito |
|-----------|---------|----------|
| Neo4j | 5.26.0 | Base de datos gráfica |
| AWS Bedrock | Latest | API de modelos LLM (Claude Sonnet) |
| Python | 3.14 | Runtime backend |
| Node.js | 18+ | Runtime frontend |

---

## Backend - Análisis Técnico

### 1. Estructura Principal (main.py)

**Responsabilidad**: Aplicación FastAPI que orquesta todos los endpoints y conecta frontend con agente IA.

**Puertos y Configuración**:
```python
# IP: 0.0.0.0 (accessible desde cualquier interfaz)
# Puerto: 8000
# Reload automático en desarrollo
```

**CORS Configuration**:
```python
origins = [
    "http://localhost:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:3001",
    "http://0.0.0.0:3000",
    "http://0.0.0.0:3001",
]
```

### 2. Endpoints API

#### 2.1 Health Check
```
GET /health
Response: {"status": "ok", "service": "ProFuturo AI Analytics"}
```

#### 2.2 Chat con IA (Endpoint Crítico)
```
POST /api/chat
Content-Type: application/json

Request:
{
  "message": "Genera un reporte sobre ProFuturo Conecta",
  "community": "ProFuturo Conecta"
}

Response (200):
{
  "response": "# Reporte Mensual\n...",
  "community": "ProFuturo Conecta",
  "pdf": {
    "base64": "JVBERi0xLjQK...",
    "filename": "Reporte_Mensual.pdf"
  },
  "success": true
}

Response (error 500):
{
  "response": "Error procesando la consulta: ...",
  "community": "ProFuturo Conecta",
  "pdf": null,
  "success": false
}
```

**Timeout**: 600 segundos (10 minutos)
**Procesamiento**: Ejecutor de threads con 4 workers

#### 2.3 Chat con Archivo Adjunto
```
POST /api/chat-with-file
Content-Type: multipart/form-data

Parámetros:
- message (text): Consulta
- community (text): Comunidad objetivo
- file (file): CSV o PDF adjunto

Response: Idéntica a /api/chat
```

**Soporta**:
- Archivos CSV: Se incluye contenido en mensaje
- Archivos PDF: Se adjunta metadata
- Tamaño máx.: No limitado explícitamente

#### 2.4 Listado de Comunidades
```
GET /api/communities

Response (200):
{
  "communities": [
    "ProFuturo Conecta",
    "Red de Líderes",
    "Comunidad Pruebas"
  ]
}
```

#### 2.5 Feed de Mensajes
```
GET /api/feed?community=ProFuturo Conecta

Response (200):
{
  "success": true,
  "community": "ProFuturo Conecta",
  "count": 20,
  "messages": [
    {
      "id": "p123",
      "author": "Juan García",
      "topic": "Metodologías innovadoras",
      "community": "ProFuturo Conecta",
      "excerpt": "Texto del mensaje truncado a 300 caracteres...",
      "time": "2026-03-20",
      "replies": 0,
      "sentiment": "positive"
    }
  ]
}

`LIMIT` en BD: 20 posts más recientes
`Ordenamiento`: Por fecha descendente
`Filtro`: Por comunidad si se especifica
```

#### 2.6 Grafo de Interacciones
```
GET /api/graph?community=todas

Response (200):
{
  "success": true,
  "community": "todas",
  "edges": [
    {
      "author": "Juan García",
      "discussion": "Innovación pedagógica",
      "community": "ProFuturo Conecta",
      "post_count": 15
    }
  ]
}

`LIMIT` en BD: 60 nodos más conectados
```

### 3. Agente IA (agent.py)

**Conceptualización**: Agente de razonamiento que decide qué herramientas usar según la consulta.

**Arquitectura**:
1. **LLM**: Claude Sonnet 4.5 vía AWS Bedrock
2. **Tools Disponibles**:
   - `get_monthly_directive_report()`: Extrae KPIs del mes
   - `get_forum_context()`: Recupera contexto de mensajes recientes

3. **System Prompt**:
```
"Eres el Auditor IA de ProFuturo. Tu función es analizar foros usando las herramientas proporcionadas.
REGLAS:
1. Usa las herramientas para buscar información antes de responder.
2. Si el usuario pide métricas o un informe directivo, usa get_monthly_directive_report.
3. Si el usuario pide un resumen, temas o hace una pregunta específica, usa get_forum_context.
4. Responde SIEMPRE con formato Markdown estructurado (##, -, **).
5. Si el usuario solicita generar un reporte, informe o PDF para descargar, INCLUYE SIEMPRE 
   exactamente esta etiqueta al final de tu respuesta: [GENERATE_PDF: Titulo_Del_Documento]"
```

**Flujo de Generación de reportes**:
1. Frontend envía consulta
2. Agente decide usar `get_monthly_directive_report`
3. Agente responde con `[GENERATE_PDF: Titulo]` al final
4. `run_agent()` detecta la etiqueta
5. Llama a `generate_report_pdf()` para crear PDF
6. Retorna PDF en base64 + respuesta limpia

**Fechas Dinámicas**:
```python
# Hoy: 21 marzo 2026
# Mes de reporte: Abril 2026 (hoy + 1 mes)
# Fecha de generación: Marzo 2026 (hoy)
# Próxima revisión: Mayo 2026 (hoy + 2 meses)
```

### 4. Generación de PDFs (tools.py)

**Características**:
- Librería: fpdf2 2.8.2
- Logo: 30x15mm en esquina superior izquierda
- Márgenes: 20mm (uniforme)
- Saltos de página: Automáticos
- Codificación: latin-1

**Procesamiento Markdown**:
```python
# Input: Texto markdown
html_content = markdown.markdown(text, extensions=['tables'])
pdf.write_html(html_content)  # Renderiza HTML en PDF
```

**Estructura PDF**:
- Encabezado: Título centrado (Helvetica Bold 14pt)
- Cuerpo: Contenido HTML desde markdown
- Salto: 10mm después del título
- Fuente base: Helvetica 10pt

### 5. Conexión Neo4j

**Librerías**: neo4j 5.26.0

**Esquema de nodos**:
```
(:Author)
  - name (String, PK)

(:Post)
  - id (String, PK)
  - content (Text)
  - date (Date)
  - sentiment (String)

(:Discussion)
  - topic (String, PK)

(:Community)
  - name (String, PK)

Relaciones:
- (Author)-[:WROTE]->(Post)
- (Post)-[:IN_DISCUSSION]->(Discussion)
- (Discussion)-[:PERTAINS_TO]->(Community)
```

**Recuperación de Conexión**:
```python
def _get_neo4j_driver():
    uri = os.getenv("NEO4J_URI")          # bolt://localhost:7687
    user = os.getenv("NEO4J_USER")        # neo4j
    password = os.getenv("NEO4J_PASSWORD")# <password>
    return GraphDatabase.driver(uri, auth=(user, password))
```

### 6. Configuración LLM (llm_config.py)

**Modelo Actual**: Claude Sonnet 4.5 (AWS Bedrock)
```python
ChatBedrock(
    model_id="us.anthropic.claude-sonnet-4-5-20250929-v1:0",
    temperature=0.0,  # Respuestas determinísticas
    max_tokens=8192   # Límite de contexto
)
```

**Variables de Entorno Requeridas**:
- `REGION_BEDROCK`: Región AWS (e.g., us-west-2)
- `AWS_ACCESS_KEY`: Credencial IAM
- `AWS_SECRET_KEY`: Credencial IAM

**Futuro**: Modelo local con Ollama en EC2 (comentado en código)

---

## API REST - Integración Frontend-Backend

### Diagrama de Flujo

```
┌─────────────────────────────────────────────────────────────┐
│                      FRONTEND (Next.js)                      │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  1. User abre dashboard → /3000                              │
│  2. Carga comunidades → GET /api/communities                 │
│  3. Carga feed de mensajes → GET /api/feed                   │
│  4. Carga grafo → GET /api/graph                             │
│     │                                                         │
│     ↓                                                         │
│  5. User escribe chat → POST /api/chat                       │
│     │                                                         │
│     ↓                                                         │
│     REQUEST BODY:                                            │
│     {                                                        │
│       "message": "Genera un reporte",                       │
│       "community": "ProFuturo Conecta"                      │
│     }                                                        │
│                                                               │
│     ↓↓↓ OVER THE WIRE (HTTP/JSON) ↓↓↓                        │
│                                                               │
└─────────────────────────────────────────────────────────────┘
                          ↓
        ┌──────────────────────────────────────┐
        │   API GATEWAY (FastAPI @ 0.0.0.0:8000)│
        └──────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│                    BACKEND (FastAPI)                         │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  6. /api/chat endpoint ejecuta:                              │
│     a) Valida ChatRequest (Pydantic)                         │
│     b) Crea ThreadPoolExecutor                               │
│     c) Ejecuta run_agent() en thread                         │
│        │                                                     │
│        ├─> Agente IA (LangGraph)                             │
│        │   │                                                 │
│        │   ├─> Selecciona herramienta                        │
│        │   │   • get_monthly_directive_report() o            │
│        │   │   • get_forum_context()                         │
│        │   │                                                 │
│        │   ├─> Ejecuta Cypher queries en Neo4j               │
│        │   │                                                 │
│        │   └─> Llama Claude Sonnet 4.5 (AWS Bedrock)         │
│        │       • Procesa respuesta                           │
│        │       • Detecta [GENERATE_PDF: Titulo]              │
│        │                                                     │
│        └─> generate_report_pdf()                             │
│            • Crea PDF con fpdf2                              │
│            • Añade logo + contenido markdown                │
│            • Codifica base64                                 │
│                                                               │
│  7. Retorna ChatResponse:                                    │
│     {                                                        │
│       "response": "# Reporte...",                           │
│       "community": "ProFuturo Conecta",                     │
│       "pdf": {                                               │
│         "base64": "JVBERi0xLjQK...",                        │
│         "filename": "Reporte.pdf"                           │
│       },                                                     │
│       "success": true                                        │
│     }                                                        │
│                                                               │
└─────────────────────────────────────────────────────────────┘
                          ↓
                ┌──────────────────────┐
                │   DATABASE (Neo4j)   │
                └──────────────────────┘
                (Consultas Cypher)
```

### Detalles de Integración

#### 1. **Configuración de Conexión (Frontend)**
```typescript
// components/dashboard/ai-chat.tsx
const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
```

#### 2. **Envío de Solicitud (Frontend)**
```typescript
response = await fetch(`${API_URL}/api/chat`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ 
    message: text, 
    community: selectedCommunity 
  }),
  signal: controller.signal,  // Timeout: 600s
})
```

#### 3. **Validación (Backend)**
```python
class ChatRequest(BaseModel):
    message: str
    community: str = "todas"

# Validación automática vía Pydantic
```

#### 4. **Procesamiento Asincrónico (Backend)**
```python
loop = asyncio.get_event_loop()
result = await asyncio.wait_for(
    loop.run_in_executor(_executor, run_agent, request.message, request.community),
    timeout=600.0  # 10 minutos máximo
)
```

#### 5. **Serialización de Respuesta (Backend)**
```python
pdf_data = PDFData(
    base64=result["pdf_base64"],
    filename=result.get("pdf_filename", "report.pdf"),
)
return ChatResponse(
    response=result.get("response", ""),
    community=request.community,
    pdf=pdf_data,
    success=True,
)
```

#### 6. **Deserialization & Renderizado (Frontend)**
```typescript
const data = await response.json()
const pdf = data.pdf?.base64 && data.pdf?.filename
  ? { base64: data.pdf.base64, filename: data.pdf.filename }
  : undefined
appendAIMessage(data.response || "Sin respuesta del servidor.", pdf)
if (pdf) triggerPDFDownload(pdf)  // Descarga automática
```

### Flujo de Manejo de Errores

**Timeout (>600s)**:
```
Frontend waits 600s → Abort signal → Backend returns ChatResponse
{
  "response": "La generacion del analisis y PDF supero el tiempo maximo permitido (600s). Reintenta.",
  "success": false
}
```

**Error de Validación (campo faltante)**:
```
Pydantic valida → HTTPException (422) → Frontend captura error
```

**Error de Neo4j (conexión perdida)**:
```
try/except en main.py → HTTPException (500) → Frontend muestra
"Error procesando la consulta: {error details}"
```

---

## Instalación y Configuración

### Requisitos Previos
- Python 3.14
- Node.js 18+
- Neo4j 5.26
- AWS Account (para Bedrock)
- Git

### Backend (Python)

#### 1. Crear entorno virtual
```bash
cd backend
python3 -m venv venv
source venv/bin/activate  # macOS/Linux
# o
venv\Scripts\activate     # Windows
```

#### 2. Instalar dependencias
```bash
pip install -r requirements.txt
```

#### 3. Configurar variables de entorno
```bash
# Crear archivo .env en backend/
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=<your_password>

# AWS Bedrock
REGION_BEDROCK=us-west-2
AWS_ACCESS_KEY=<your_key>
AWS_SECRET_KEY=<your_secret>

# CORS (opcional)
CORS_ORIGINS=http://localhost:3000,http://localhost:3001

# API
API_HOST=0.0.0.0
API_PORT=8000
```

#### 4. Cargar datos (primera ejecución)
```bash
python scripts/ingest.py
```

### Frontend (Node.js)

#### 1. Instalar dependencias
```bash
cd ..
npm install
```

#### 2. Configurar variables de entorno
```bash
# Crear archivo .env.local en raíz del proyecto
NEXT_PUBLIC_API_URL=http://localhost:8000
```

#### 3. Compilar
```bash
npm run build
```

---

## Ejecución

### Desarrollo

#### Terminal 1 - Backend
```bash
cd backend
source venv/bin/activate
python -m uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

#### Terminal 2 - Frontend
```bash
npm run dev
```

**Acceso**:
- Dashboard: http://localhost:3000
- API: http://localhost:8000
- Docs: http://localhost:8000/docs (Swagger UI)

### Producción

#### Backend
```bash
python -m uvicorn src.main:app --host 0.0.0.0 --port 8000 --workers 4
```

#### Frontend
```bash
npm run build
npm run start
```

---

## Documentación API

FastAPI genera automáticamente documentación interactiva en:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **OpenAPI JSON**: http://localhost:8000/openapi.json

---

## Notas Importantes

1. **Threads vs Async**: El endpoint `/api/chat` usa `ThreadPoolExecutor` porque `run_agent()` hace operaciones síncronas (llamadas a Neo4j, API AWS).

2. **CORS**: Configurado para aceptar orígenes localhost y 0.0.0.0 en puertos 3000/3001.

3. **PDF Generation**: Los PDFs se codifican en base64 para transmisión JSON. El navegador decodifica y descarga automáticamente.

4. **Timeout**: 600 segundos permitidos para análisis completos + generación de PDF. Crítico para análisis complejos.

5. **Neo4j Query Performance**: Las queries limitan a 20-60 resultados para mantener latencia <2s.

---

**Última actualización**: 21 de marzo de 2026  
**Versión**: 1.0.0  
**Autor**: ProFuturo AI Analytics Team
