# Memoria Global: Auditor IA ProFuturo

## 1. Descripción del Proyecto

El presente Trabajo de Fin de Grado (TFG) documenta el diseño, desarrollo e implementación de un sistema de inteligencia artificial denominado **Auditor IA ProFuturo**. Se trata de una plataforma cognitiva conversacional construida como un Agente Inteligente autónomo, capaz de auditar y analizar de forma transversal los foros educativos y canales de comunidad de la Fundación ProFuturo — un programa de educación digital impulsado por Fundación Telefónica y Fundación "la Caixa" que opera en entornos vulnerables de Latinoamérica, el Caribe, África y Asia.

El sistema trasciende la categoría de un chatbot convencional al incorporar capacidades de toma de decisión autónoma, enrutamiento inteligente de consultas, generación de reportes ejecutivos en PDF y automatización de procesos robóticos (RPA). La arquitectura está orquestada mediante LangGraph, un framework de última generación que permite la construcción de flujos de trabajo cíclicos y reflexivos, superando las limitaciones de los sistemas lineales tradicionales.

El proyecto se enmarca dentro de la disciplina de la Ingeniería de Datos e Inteligencia Artificial Aplicada, combinando técnicas de Procesamiento del Lenguaje Natural (NLP), Grafos de Conocimiento, Recuperación Aumentada por Generación (RAG/GraphRAG), Fine-Tuning de Modelos de Lenguaje con QLoRA y despliegue en infraestructura cloud nativa sobre Amazon Web Services (AWS).

## 2. Contexto del Problema

### 2.1. La Saturación Informativa en Comunidades Educativas Digitales

ProFuturo gestiona una red global de comunidades educativas compuestas por miles de docentes, coordinadores y facilitadores distribuidos en más de 40 países. Estos actores interactúan diariamente a través de foros digitales temáticos donde comparten experiencias pedagógicas, reportan incidencias técnicas, formulan dudas y generan debates sobre metodologías de enseñanza.

La magnitud de estas interacciones genera un volumen de datos que supera con creces la capacidad de supervisión manual. Los coordinadores regionales enfrentan una carga operacional insostenible: extraer conocimiento útil cruzado entre comunidades, detectar patrones de comportamiento, identificar picos de negatividad o dudas críticas no resueltas, y producir informes de seguimiento para la dirección ejecutiva. Todo ello requiere la lectura manual de cientos de hilos diarios — una tarea que, en la práctica, resulta imposible de realizar con la rigurosidad y la frecuencia necesarias.

### 2.2. Limitaciones de los Chatbots Tradicionales

Los sistemas conversacionales convencionales operan bajo un paradigma reactivo y lineal: reciben una entrada, la procesan mediante coincidencia de patrones o búsqueda semántica superficial y devuelven una respuesta predefinida o generada de forma aislada. Estos sistemas presentan limitaciones fundamentales para el escenario de ProFuturo:

- **Ausencia de contexto relacional:** Un chatbot tradicional basado en RAG vectorial busca fragmentos de texto estadísticamente similares a la consulta. Sin embargo, esta aproximación no captura las relaciones entre entidades (¿quién habló con quién?, ¿en qué comunidad?, ¿sobre qué tema?). La comprensión relacional es imprescindible para auditar dinámicas comunitarias.
- **Incapacidad de acción autónoma:** Los chatbots tradicionales no pueden ejecutar acciones más allá de generar texto. No pueden generar un PDF, abrir un ticket de soporte, enviar una alerta por correo electrónico o ejecutar un script de automatización.
- **Falta de razonamiento iterativo:** Un sistema lineal no puede detenerse a mitad de generación para evaluar si le falta información, volver a consultar una base de datos y luego continuar con una respuesta más completa.

### 2.3. Sistemas Conversacionales Cognitivos: Los Agentes Inteligentes

El presente proyecto implementa un paradigma radicalmente diferente: el de los **Agentes Inteligentes** (Agentic AI). Un agente, a diferencia de un chatbot, posee:

- **Autonomía de decisión:** Analiza la intención del usuario y elige la estrategia óptima entre múltiples herramientas disponibles (Tool Calling). Por ejemplo, si el usuario pide un reporte, el agente decide consultar la base de datos de grafos Neo4j, extraer métricas, calcular KPIs y maquetar un PDF — todo sin intervención humana.
- **Razonamiento cíclico (ReAct):** Gracias a LangGraph, el agente implementa el patrón Reason + Act. Esto significa que puede razonar sobre una consulta, ejecutar una acción, evaluar el resultado y, si no es satisfactorio, volver a razonar y ejecutar otra acción antes de emitir la respuesta final.
- **Memoria contextual:** El agente mantiene el historial de la conversación y puede referirse a consultas previas, lo que permite interacciones multi-turno coherentes y naturales.

### 2.4. El Agente como Operador (Agentic RPA)

El sistema trasciende el paradigma de la IA puramente informativa para entrar en el ámbito de la IA operativa o **Agentic RPA**. A través de su arquitectura de herramientas (Tool Calling), el agente puede ejecutar flujos de trabajo que tradicionalmente requerirían la intervención manual de un técnico o coordinador:

- **Ejecución de flujos de soporte:** Si un usuario reporta un problema crítico (ej. "falla la conectividad en el aula"), el agente no solo ofrece consejos; puede activar un script de RPA para abrir automáticamente un ticket en el sistema de soporte técnico de la organización.
- **Generación dinámica de artefactos:** La capacidad de transmutar datos crudos del grafo en reportes PDF estructurados y formateados según la identidad corporativa es, en sí misma, una tarea de RPA orquestada por el motor de razonamiento del LLM.
- **Intervención en segundo plano:** La arquitectura permite que el agente detecte patrones de riesgo y accione preventivamente alertas por canales externos (correo, notificaciones), fusionando la capacidad de análisis lingüístico con la ejecución de tareas robóticas.

## 3. Objetivo del Sistema

### 3.1. Objetivo General

Diseñar e implementar un sistema de auditoría inteligente basado en agentes cognitivos de IA que permita a ProFuturo automatizar el análisis transversal de sus comunidades educativas digitales, garantizando la soberanía del dato mediante el despliegue de modelos de lenguaje de código abierto en infraestructura cloud privada.

### 3.2. Objetivos Específicos

1. **Implementar un Agente Inteligente con capacidad de Tool Calling**, orquestado mediante LangGraph, que pueda clasificar intenciones, consultar bases de datos de grafos y ejecutar herramientas de automatización de forma autónoma.
2. **Construir una capa de recuperación basada en GraphRAG**, utilizando Neo4j como grafo de conocimiento, que permita al sistema comprender las relaciones semánticas entre usuarios, foros, hilos y comunidades — superando las limitaciones del RAG vectorial tradicional.
3. **Realizar el Fine-Tuning de un modelo de lenguaje open-source** (familia Qwen) utilizando técnicas de adaptación de bajo rango cuantizado (QLoRA) para especializar el modelo en el dominio educativo de ProFuturo sin comprometer su conocimiento general.
4. **Desplegar toda la infraestructura en Amazon Web Services (AWS)**, utilizando SageMaker para el entrenamiento y la inferencia, S3 como Data Lake y EC2 como servidor de backend, garantizando que ningún dato sensible de la organización abandone el perímetro de seguridad de la nube privada.
5. **Desarrollar un frontend interactivo en Next.js** y un backend de API REST en FastAPI que integren la experiencia de usuario completa, incluyendo la visualización de grafos de conocimiento, la interacción conversacional y la descarga de reportes ejecutivos en PDF.

## 4. Problema que Resuelve

El Auditor IA ProFuturo resuelve un conjunto interrelacionado de problemas operativos y estratégicos:

- **Problema operativo inmediato:** La imposibilidad humana de auditar manualmente los miles de interacciones diarias que se producen en los foros educativos de la fundación en más de 40 países.
- **Problema de conocimiento cruzado:** La información relevante sobre tendencias educativas, incidencias técnicas recurrentes y necesidades formativas está dispersa en hilos inconexos de múltiples foros. Un coordinador no puede, por definición, tener visibilidad simultánea de todas las comunidades.
- **Problema de soberanía del dato:** Las conversaciones de los foros contienen información sensible sobre docentes, alumnos y dinámicas educativas internas. La utilización de APIs comerciales externas (OpenAI, Anthropic) para procesar esta información implica que los datos abandonan el perímetro de seguridad de la organización, lo cual es inaceptable desde el punto de vista de la gobernanza de datos en un contexto educativo internacional.
- **Problema de latencia resolutiva:** El tiempo que transcurre entre que un docente reporta una incidencia o formula una pregunta y recibe una respuesta útil puede ser de horas o días. Un agente inteligente reduce esta latencia a segundos.

## 5. Visión General de la Solución

La solución implementada representa la evolución natural desde un primer prototipo de clasificador Question-Answering extractivo (utilizando el modelo BETO para español en Google Colab) hasta una plataforma asíncrona de próxima generación. Esta evolución se articula en las siguientes capas:

### 5.1. Capa de Inteligencia Artificial
El núcleo cognitivo del sistema se basa en modelos de la familia Qwen, optimizados mediante QLoRA (Quantized Low-Rank Adaptation) en 4 bits. Esta técnica permite inyectar conocimiento específico del dominio ProFuturo sin alterar los pesos originales de la red neuronal, evitando así el fenómeno de "Olvido Catastrófico" que se observó en iteraciones previas del proyecto con Full Fine-Tuning.

### 5.2. Capa de Recuperación de Conocimiento (GraphRAG)
La información de los foros se estructura como un grafo de conocimiento en Neo4j, donde los nodos representan entidades (autores, posts, hilos, comunidades) y las aristas capturan las relaciones entre ellas. El agente navega este grafo mediante consultas Cypher para extraer contexto relacional que un sistema vectorial convencional no podría proporcionar.

### 5.3. Capa de Orquestación (LangGraph)
LangGraph actúa como el sistema nervioso central del agente. Gestiona el flujo de decisión mediante un grafo dirigido acíclico donde cada nodo representa una etapa del razonamiento (clasificación de intención, recuperación de datos, generación de respuesta, ejecución de herramientas). Este diseño permite modularidad extrema y la capacidad de añadir nuevas herramientas o modelos sin reescribir la lógica principal.

### 5.4. Capa de Acción Operativa (Agentic RPA)
A diferencia de los sistemas de RPA tradicionales basados en reglas rígidas ("if-then"), el **Auditor IA** utiliza el LLM para decidir *cuándo* y *cómo* accionar un proceso robótico. El agente actúa como el "capataz" que, tras razonar sobre la necesidad del usuario y el contexto extraído de Neo4j, selecciona y parametriza la herramienta de automatización adecuada (ej. generar un resumen directivo o escalar una incidencia crítica).

### 5.5. Capa de Infraestructura Cloud
Toda la solución se despliega sobre AWS, donde SageMaker gestiona el ciclo de vida de los modelos (entrenamiento, inferencia, endpoints), S3 actúa como repositorio centralizado de datos y artefactos, y EC2 aloja el backend de producción con FastAPI. Las políticas de seguridad (IAM, Security Groups, Elastic IP) garantizan que el acceso al modelo esté restringido exclusivamente a la red interna del proyecto.

### 5.6. Impacto en Educación y Comunidades Digitales
El Auditor IA transforma la manera en que ProFuturo gestiona sus comunidades, pasando de un modelo reactivo manual a uno proactivo automatizado. El sistema no solo responde preguntas, sino que integra capas de **Agentic RPA** para generar resúmenes de clima de comunidad, crear informes directivos con KPIs de participación, detectar patrones de negatividad o descontento, y proponer alertas tempranas, donde el agente lea los foros durante la noche y genere reportes semanales listos para los coordinadores regionales cada viernes a las 8:00 AM — anticipándose a los problemas en lugar de reaccionar cuando ya es tarde.

#### Hoja de Ruta de Integración Futura
La arquitectura está preparada para las siguientes fases de expansión técnica:
- **Integración con Pinchtab:** Conexión del `weekly_reminder_job` con la API de la plataforma Pinchtab para la publicación automática y desatendida de recordatorios y síntesis semanales en los foros de la comunidad.
- **Interacción Interactiva @Auditor IA:** Implementación de un monitor de menciones en tiempo real que permita al agente responder de forma interactiva cuando un usuario lo invoque directamente en un hilo de discusión mediante la etiqueta `@Auditor IA`.
- **Despliegue Persistente:** Migración del backend de FastAPI a un servicio gestionado mediante `systemd` en instancias EC2 para garantizar el arranque automático y la alta disponibilidad del sistema.
