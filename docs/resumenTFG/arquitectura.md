# Arquitectura del Sistema: Auditor IA ProFuturo

## 1. Visión General de la Arquitectura

La arquitectura del Auditor IA sigue un diseño por capas desacopladas, donde cada componente tiene una responsabilidad única y bien definida. El sistema se divide en cuatro capas principales: la Capa de Presentación (Frontend), la Capa de Lógica y Orquestación (Backend + Agente), la Capa de Inteligencia (Modelos LLM) y la Capa de Datos y Conocimiento (Neo4j + S3). Todas las capas se comunican de forma asíncrona mediante APIs REST y se despliegan sobre infraestructura Amazon Web Services.

## 2. Componentes del Sistema

### 2.1. Frontend — Next.js

La interfaz de usuario está desarrollada en Next.js, el framework de React para producción. Proporciona una experiencia de usuario fluida y moderna que incluye:

- **Chat interactivo:** Interfaz conversacional en tiempo real donde los usuarios (tutores, coordinadores) pueden formular consultas al Auditor IA.
- **Visualizador de grafos:** Representación visual del grafo de conocimiento de Neo4j, mostrando las relaciones entre autores, hilos, comunidades y temas.
- **Descarga de reportes:** Capacidad de recibir y descargar documentos PDF generados dinámicamente por el agente.

El frontend se comunica exclusivamente con el backend mediante peticiones HTTP (POST) y no tiene acceso directo a los modelos de IA ni a la base de datos. Esta separación garantiza la seguridad y la escalabilidad del sistema.

### 2.2. Backend — FastAPI (Python)

El backend es el punto de entrada y orquestación de todas las operaciones del sistema. Desarrollado en Python con FastAPI, ofrece:

- **Rutas API REST** que reciben las consultas del frontend, las envían al agente y devuelven las respuestas formateadas.
- **Gestión de sesiones** y mantenimiento del historial conversacional.
- **Generación de PDFs** mediante la librería `fpdf2`, activada cuando el agente detecta que el usuario ha solicitado un reporte ejecutivo.
- **Configuración centralizada** a través de archivos `.env` que contienen las credenciales de AWS, los endpoints de SageMaker, los modelos de embeddings y las URLs de Neo4j.

La arquitectura del backend está diseñada para ser agnóstica al modelo utilizado. Un módulo denominado `src/llm_config.py` centraliza la conexión con el LLM, de modo que cambiar de un modelo local (Ollama) a un endpoint de SageMaker o incluso a una API externa requiere modificar únicamente este archivo de configuración — sin alterar la lógica del agente ni las rutas de la API.

### 2.3. Agente Cognitivo — LangGraph

LangGraph constituye el sistema nervioso central del Auditor IA. A diferencia de las cadenas lineales de LangChain (donde la información fluye en una sola dirección), LangGraph permite construir grafos de ejecución cíclicos. Esto significa que el agente puede:

1. **Recibir una consulta** del backend.
2. **Razonar** sobre la intención utilizando el LLM.
3. **Decidir** qué herramienta ejecutar (Tool Calling): consultar Neo4j, generar un reporte, ejecutar un script RPA, o simplemente responder con un saludo.
4. **Ejecutar** la herramienta seleccionada.
5. **Evaluar** si el resultado es suficiente. Si no lo es, volver al paso 2 (ciclo ReAct: Reason + Act).
6. **Sintetizar** la respuesta final y devolverla al backend.

**El fichero `src/agent.py`** define la estructura del grafo, los nodos (estados) y las transiciones. Cada nodo es una función Python que recibe el estado actual del agente (mensajes, herramientas disponibles, resultados intermedios) y devuelve el siguiente estado.

**El fichero `src/tools.py`** define las herramientas disponibles para el agente: funciones de extracción de contexto de Neo4j, generadores de reportes con KPIs, funciones de análisis de sentimiento y scripts de RPA.

### 2.4. Modelo de Lenguaje (LLM) — Qwen 2.5

El motor lingüístico del sistema es un modelo de la familia Qwen (Qwen 2.5), elegido tras una evaluación comparativa con Llama 3.2 y DeepSeek-R1. Qwen fue seleccionado por su rendimiento superior en tareas de razonamiento conversacional en español y su compatibilidad nativa con el formato ChatML para fine-tuning.

El modelo opera en dos modos posibles:

- **Inferencia local:** Mediante Ollama, un servidor de inferencia que carga el modelo en formato GGUF y expone una API local en el puerto 11434. Esta configuración se utilizó durante el desarrollo.
- **Inferencia en la nube:** Mediante un endpoint de Amazon SageMaker utilizando el contenedor **TGI (Text Generation Inference)** de HuggingFace. El modelo se despliega como un servicio de alta eficiencia sobre una instancia **ml.g5.xlarge** (NVIDIA A10G con 24GB VRAM), elegida para garantizar la compatibilidad total con los kernels de cuantización de `bitsandbytes`.

### 2.5. Base de Conocimiento — Neo4j (GraphRAG)

Neo4j aloja el grafo de conocimiento de ProFuturo, donde los datos de los foros se estructuran como un grafo de entidades y relaciones:

- **Nodos:** Autores, Posts, Hilos, Comunidades, Temas.
- **Aristas:** "ESCRIBIÓ", "PERTENECE_A", "RESPONDIÓ_A", "TRATA_SOBRE".

El agente consulta este grafo mediante el lenguaje Cypher, lo que le permite realizar consultas relacionales complejas como: *"¿Qué autores de la comunidad de Colombia participaron en hilos sobre incidencias técnicas en enero y también interactuaron con la comunidad de Perú?"* — una consulta imposible de resolver mediante búsqueda vectorial tradicional.

### 2.6. Modelo de Embeddings — nomic-embed-text

Para las operaciones de búsqueda semántica donde no se requiere navegación relacional, el sistema utiliza `nomic-embed-text` como modelo de embeddings. Este modelo convierte los textos en vectores densos que permiten la recuperación por similitud coseno, complementando la capacidad relacional del grafo con búsqueda semántica pura.

## 3. Infraestructura AWS

### 3.1. Amazon S3 (Data Lake)

S3 opera como el almacén centralizado y seguro de todos los artefactos del proyecto:

- **Datasets de entrenamiento:** Archivos `train.jsonl` y datasets en formato ChatML preparados para QLoRA.
- **Pesos de modelos:** Archivos `model.tar.gz` generados tras el entrenamiento, que contienen los adaptadores LoRA y los pesos fusionados.
- **Artefactos de producción:** Plantillas de PDF, reportes generados y archivos de configuración.

El bucket S3 está configurado con políticas de acceso restringido, de modo que solo las instancias EC2 y SageMaker autorizadas pueden leer o escribir en él.

### 3.2. Amazon SageMaker (Fábrica de Modelos y Endpoints)

SageMaker cumple dos funciones críticas diferenciadas:

**Función 1 — Merge & Training Jobs:**
Se utilizan instancias **ml.g4dn.2xlarge** (32GB RAM) para realizar la fusión (merge) de los adaptadores LoRA con el modelo base en CPU (fp16) antes del despliegue. Esta operación se "disfraza" como un Training Job para optimizar el uso de cuotas de AWS asignadas al proyecto.

**Función 2 — Endpoints TGI (Producción):**
Una vez el modelo está fusionado, SageMaker despliega un endpoint persistente con TGI. Este motor permite optimizaciones como continuous batching y PagedAttention, fundamentales para mantener la latencia baja en el Auditor IA.

### 3.3. Amazon EC2 (Servidor de Backend)

EC2 proporciona el cómputo persistente donde se ejecuta el backend de producción:

- **Tipo de instancia:** Familia `g4dn.xlarge` con GPU NVIDIA T4 para inferencia local con Ollama (en la configuración de desarrollo) o CPU para la configuración donde la inferencia se delega a SageMaker.
- **Sistema operativo:** AWS Deep Learning AMI (Ubuntu 22.04 LTS), preconfigurada con controladores NVIDIA y CUDA.
- **Almacenamiento:** Volumen EBS tipo `gp3` de 100 GB para alojar el SO, Docker y los pesos de modelos.
- **Red:** IP Elastic estática con Security Groups restrictivos: SSH (puerto 22) restringido a IP administrativa, API de Ollama (puerto 11434) restringido exclusivamente a la IP del backend.

### 3.4. Gestión de Identidad y Accesos (IAM)

La cuenta de AWS del proyecto opera bajo políticas IAM con protección MFA (Multi-Factor Authentication). El usuario del proyecto tiene asignados roles con las siguientes políticas:
- `AmazonEC2FullAccess` (limitado a la instancia del proyecto)
- `AmazonSageMakerFullAccess` (para gestionar notebooks y endpoints)
- `AmazonS3FullAccess` (limitado al bucket específico del proyecto)

## 4. Flujo de Datos End-to-End

El recorrido completo de una petición desde el usuario hasta la respuesta final sigue los siguientes pasos:

1. **Entrada del usuario:** Un tutor de ProFuturo escribe en el chat de Next.js: *"¿De qué están hablando hoy en la comunidad de Colombia?"*
2. **Recepción en el backend:** FastAPI recibe la petición HTTP POST y la entrega al agente LangGraph.
3. **Clasificación de intención:** El agente, utilizando el LLM, analiza la consulta y determina que se trata de una solicitud de análisis transversal de comunidad.
4. **Recuperación de conocimiento (GraphRAG):** El agente ejecuta la herramienta correspondiente, que lanza una consulta Cypher a Neo4j recorriendo los nodos (Autores → Posts → Hilos → Comunidades), filtra por fecha y comunidad, y devuelve los datos crudos.
5. **Síntesis de respuesta:** El agente vuelve a invocar al LLM con los datos extraídos como contexto, solicitando que redacte un resumen en formato Markdown corporativo.
6. **Generación de artefactos (opcional):** Si el usuario solicitó un reporte formal, el backend detecta la etiqueta de generación de PDF insertada por el agente, maqueta el documento con `fpdf2` usando los colores corporativos de ProFuturo, y adjunta el archivo a la respuesta.
7. **Respuesta al frontend:** Next.js recibe la respuesta formateada (texto + PDF adjunto) y la presenta al usuario en la interfaz del chat.

## 5. RAG Vectorial vs. GraphRAG: Comparativa Técnica

### 5.1. RAG Vectorial Tradicional

En un sistema RAG vectorial convencional, los documentos se fragmentan en chunks, se convierten en vectores mediante un modelo de embeddings y se almacenan en una base de datos vectorial (FAISS, Pinecone, OpenSearch). Cuando el usuario formula una pregunta, esta se vectoriza y se buscan los fragmentos con mayor similitud coseno. Estos fragmentos se inyectan como contexto en el prompt del LLM.

**Limitaciones para el caso de ProFuturo:**
- La búsqueda por similitud vectorial no captura relaciones entre entidades. Si un docente del foro de Colombia menciona un problema que ya fue resuelto en el foro de Perú, un sistema vectorial no puede establecer esa conexión relacional.
- Los chunks de texto pierden el contexto conversacional: un post de respuesta se almacena de forma aislada del post original al que responde.

### 5.2. GraphRAG (La Solución Implementada)

GraphRAG supera estas limitaciones al estructurar la información como un grafo de conocimiento. En lugar de buscar "palabras parecidas", el agente navega por las relaciones semánticas de la comunidad. Una consulta como *"¿Qué usuarios han tenido problemas técnicos recurrentes?"* se traduce en una travesía del grafo que identifica nodos de usuarios conectados a múltiples nodos de incidencias técnicas a través del tiempo.

**Ventajas específicas:**
- Comprensión de contexto relacional multi-nivel.
- Capacidad de realizar inferencias transitivas (A se relaciona con B, B con C, por tanto A tiene relación indirecta con C).
- Posibilidad de calcular métricas de red (centralidad, influencia, comunidades) directamente sobre los datos.

### 5.3. Capa de Acción y RPA (Automación de Tareas)

A diferencia de un buscador tradicional, el Auditor IA puede ejecutar herramientas externas basándose en el razonamiento del modelo. El flujo de acción (RPA) se integra en la arquitectura como una serie de conectores o "Tools" que el agente puede invocar:

- **Generador de Artefactos Formateados:** El sistema toma los datos extraídos de Neo4j y los procesa a través de la librería `fpdf2` para generar reportes PDF corporativos de forma desatendida.
- **Conectores de Comunicación:** Integración de herramientas para el envío de alertas y notificaciones proactivas basadas en la detección de sentimiento crítico.
- **Agentic RPA:** El LLM actúa como el controlador lógico que parametriza y dispara scripts de automatización (ej. apertura de tickets, resúmenes automáticos) sin necesidad de una programación rígida de flujos.

## 6. LangGraph: Orquestación del Agente

LangGraph es el framework que permite construir el grafo de ejecución del agente. A diferencia de las cadenas secuenciales de LangChain clásico, LangGraph implementa un modelo de estados finitos donde:

- **Cada nodo** es una función Python que representa un paso del razonamiento (clasificar intención, buscar en Neo4j, llamar al LLM, ejecutar RPA).
- **Cada arista** es una función condicional que determina la transición al siguiente nodo basándose en el resultado del nodo actual.
- **El estado** es un diccionario mutable que acumula mensajes, resultados de herramientas y decisiones intermedias a lo largo de toda la ejecución.

Este diseño permite al agente implementar el patrón **ReAct** (Reason + Act): en cada iteración, el agente razona sobre el estado actual, decide si necesita más información, ejecuta la acción correspondiente y evalúa si el resultado es satisfactorio antes de emitir la respuesta final. Si el resultado es insuficiente, el grafo permite volver a un nodo anterior (ciclo) para obtener más contexto.

## 7. Interacción entre Componentes

La interacción entre componentes sigue un patrón de responsabilidad en cadena:

| Componente | Responsabilidad | Se comunica con |
|---|---|---|
| Next.js (Frontend) | Interfaz de usuario, visualización | FastAPI (HTTP POST) |
| FastAPI (Backend) | Rutas API, sesiones, PDF | LangGraph (Python) |
| LangGraph (Agente) | Razonamiento, decisión, orquestación | LLM, Neo4j, Tools |
| Qwen (LLM) | Comprensión lingüística, generación | SageMaker Endpoint |
| Neo4j (Grafo) | Almacenamiento relacional, consultas Cypher | Agente (driver Bolt) |
| S3 (Data Lake) | Persistencia de datos y modelos | SageMaker, EC2 |
| SageMaker | Entrenamiento e inferencia GPU | S3, EC2 |

## 8. Futuras Integraciones Técnicas

El sistema ha sido diseñado de forma modular para permitir la expansión hacia plataformas externas y nuevas formas de interacción:

1. **API de Pinchtab:** Automatización de la publicación de recordatorios semanales (weekly reminders) directamente en el portal de foros de ProFuturo.
2. **Escucha Activa (@Auditor IA):** Implementación de un `mention_monitor_job` que, cada 5 minutos, escanee menciones directas al bot para proporcionar soporte interactivo inmediato en hilos de discusión.
