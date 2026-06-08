# Auditor IA ProFuturo

Sistema inteligente de auditoría y análisis para las comunidades educativas de [ProFuturo](https://profuturo.education/) — un programa de educación digital de Fundación Telefónica y Fundación "la Caixa".

## Descripción

El Auditor IA es un agente conversacional que permite a los coordinadores de ProFuturo consultar, analizar y dinamizar los foros educativos de la organización mediante lenguaje natural. El sistema combina un grafo de conocimiento en Neo4j con un modelo de lenguaje (Qwen 2.5 7B) especializado con QLoRA, desplegado en infraestructura privada de AWS.

### Funcionalidades principales

- **Chat interactivo** — Consultas en lenguaje natural con respuestas basadas en datos reales de Neo4j
- **Generación de informes** — PDF con identidad corporativa y Excel con gráficos automáticos
- **Sistema RPA** — Monitorización continua de los foros con alertas por email
- **Agente autónomo** — Publicación proactiva en Moodle: bienvenidas, reactivación de hilos, resúmenes semanales, reconocimiento de contribuidores
- **Streaming** — Respuestas en tiempo real token a token

## Arquitectura

El sistema corre en una única instancia EC2 de AWS (g4dn.xlarge, GPU NVIDIA Tesla T4):

- **Frontend:** Next.js + TypeScript (puerto 3001)
- **Reverse proxy:** Nginx (puerto 3000)
- **Backend:** FastAPI (puerto 8000)
- **Modelo de lenguaje:** Qwen 2.5 7B QLoRA en formato GGUF, servido con llama-server (puerto 8090)
- **Base de datos:** Neo4j Community Edition (puerto 7687)
- **Entrenamiento:** AWS SageMaker (solo para fine-tuning, no para inferencia)
- **Almacenamiento:** AWS S3

## Estructura del proyecto
```
├── app/                        # Next.js app directory
├── backend/
│   ├── scripts/
│   │   ├── clean_data.py           # Limpieza del CSV bruto de los foros
│   │   ├── ingest_neo4j.py         # Ingesta en el grafo de conocimiento
│   │   ├── moodle_sync.py          # Sincronización incremental Moodle → Neo4j
│   │   └── rpa.py                  # 5 jobs de monitorización proactiva
│   ├── src/
│   │   ├── agent.py                # Agente con contexto obligatorio Neo4j
│   │   ├── autonomous_agent.py     # 6 jobs de publicación en Moodle
│   │   ├── autonomous_rules.py     # Reglas de decisión y moderación
│   │   ├── chat_history.py         # Historial de conversaciones (SQLite)
│   │   ├── llm_config.py           # Configuración LLM (local / SageMaker)
│   │   ├── main.py                 # API REST FastAPI
│   │   ├── moodle_writer.py        # Escritura en Moodle + modo simulación
│   │   └── tools.py                # Generación PDF y Excel
│   ├── training/
│   │   ├── lanzar_training_job.py  # Lanzamiento de Training Job en SageMaker
│   │   └── preparar_dataset.py     # Transformación CSV → ChatML
│   └── requirements.txt
├── components/                 # Componentes React del frontend
│   ├── dashboard/
│   │   ├── ai-chat.tsx             # Chat principal con streaming
│   │   ├── interaction-graph.tsx   # Visualización del grafo
│   │   ├── forum-feed.tsx          # Feed de actividad
│   │   ├── data-panel.tsx          # Panel de métricas
│   │   └── sidebar.tsx             # Navegación + historial
│   └── login-page.tsx
└── public/                     # Assets estáticos
```

## Configuración

```bash
# Clonar
git clone https://github.com/javierpozogonzalez/tfg-auditor-ia-profuturo.git

# Backend
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Editar .env con las credenciales

# Frontend
cd ..
npm install
npm run dev
```

Ver `.env.example` para todas las variables de configuración disponibles.

## Autor

**Javier Pozo González** — Trabajo de Fin de Grado, Universidad Pontificia de Salamanca (2026)

Desarrollado en colaboración con el equipo técnico de ProFuturo (Fundación Telefónica).
