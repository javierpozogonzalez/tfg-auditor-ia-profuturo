# Decisiones Arquitectónicas y Técnicas

## Introducción

El desarrollo del Auditor IA ProFuturo no siguió un camino lineal predefinido, sino un proceso iterativo de exploración, validación y pivotaje técnico. Cada decisión documentada en este capítulo fue el resultado de enfrentar limitaciones reales — de hardware, de rendimiento, de coste o de gobernanza de datos — y de evaluar rigurosamente las alternativas disponibles. El orden de presentación refleja la cronología real del desarrollo, donde cada decisión se construye sobre las lecciones aprendidas de las anteriores.

---

## Decisión 1: Modelo de Lenguaje Local (Open Source) frente a APIs Comerciales Externas

### Qué se eligió
Se optó por desplegar modelos de lenguaje de código abierto (familia Qwen) en infraestructura propia de AWS, en lugar de consumir APIs comerciales de terceros.

### Alternativas consideradas
1. **OpenAI GPT-4 / GPT-3.5 (vía API REST):** La opción más sencilla de integrar. Ofrece rendimiento de primer nivel con mínima configuración.
2. **Anthropic Claude (vía API REST):** Modelo con buenas capacidades de razonamiento y seguimiento de instrucciones largas.
3. **Amazon Bedrock (Claude, Amazon Nova Pro):** Servicio gestionado de AWS que ofrece acceso a modelos comerciales sin gestionar infraestructura.

### Por qué se descartaron
La decisión tiene raíces en un requisito no negociable del proyecto: la **soberanía del dato**. Las conversaciones de los foros de ProFuturo contienen información sensible sobre dinámicas educativas, incidencias de docentes, y datos de comunidades en contextos vulnerables de Latinoamérica y África. Enviar estos datos a servidores externos de OpenAI o Anthropic supone:
- Pérdida del control sobre la localización geográfica de los datos.
- Riesgo de retención de datos por parte del proveedor para entrenamiento de sus propios modelos.
- Incumplimiento potencial de políticas internas de gobernanza de datos de la fundación.

### Reflexión técnica (Trade-off)
Utilizar APIs comerciales habría reducido drásticamente el tiempo de desarrollo. De hecho, durante las fases intermedias del proyecto, se utilizó temporalmente una API comercial como acelerador táctico para estabilizar la arquitectura del agente y el grafo de conocimiento sin depender de la GPU local. Esta decisión temporal permitió avanzar en el diseño del sistema agéntico mientras se resolvían los problemas de infraestructura en AWS. En la memoria del TFG, esta transición se documenta como una decisión de ingeniería consciente: priorizar la maduración de la arquitectura lógica antes de resolver la infraestructura física.

---

## Decisión 2: Evolución desde BETO (Extractivo) hacia Modelos Generativos (Qwen)

### Qué se eligió
Se abandonó el prototipo inicial basado en BETO (un modelo BERT entrenado en español) y se migró a modelos generativos de la familia Qwen.

### Alternativas consideradas
1. **BETO / BERT en español:** Modelo transformer bidireccional especializado en comprensión del lenguaje. Adecuado para tareas de clasificación y extracción.
2. **Llama 3.2 (Meta):** Modelo generativo de código abierto con buenas capacidades multilingües.
3. **DeepSeek-R1 (versiones destiladas 7B/8B):** Modelo de razonamiento con rendimiento excepcional en benchmarks académicos.
4. **Qwen 2.5 (Alibaba):** Modelo generativo con soporte nativo para ChatML, excelente rendimiento en español y tamaños desde 3B hasta 72B parámetros.

### Por qué se descartaron las alternativas
- **BETO:** Aunque funcionaba para extracción de respuestas literales, no podía generar texto fluido ni mantener conversaciones multi-turno. Su paradigma (pregunta → fragmento extraído) era demasiado rígido para las necesidades del agente cognitivo.
- **Llama 3.2:** Se evaluó inicialmente y se utilizó en el primer prototipo de fine-tuning con datos de ProFuturo. Sin embargo, durante las pruebas comparativas en SageMaker, Qwen mostró un rendimiento superior en tareas de clasificación de intención en español y una integración más fluida con el formato ChatML requerido por el pipeline de entrenamiento QLoRA.
- **DeepSeek-R1:** Arquitecturalmente atractivo por su enfoque en razonamiento, pero su adopción habría añadido riesgo técnico innecesario al estar menos probado en entornos de producción con SageMaker en el momento del desarrollo.

### Reflexión técnica
La elección de Qwen se fundamentó en un criterio pragmático: era el modelo que ofrecía la mejor relación rendimiento/compatibilidad para el stack tecnológico elegido (HuggingFace Transformers + QLoRA + SageMaker containers + ChatML format). La transición desde BETO representó un salto paradigmático: del NLP extractivo (encontrar la respuesta en el texto) al NLP generativo (construir la respuesta razonando sobre el contexto).

---

## Decisión 3: Transición de Full Fine-Tuning a QLoRA con ChatML

### Qué se eligió
Se abandonó el entrenamiento completo (Full Fine-Tuning) de todos los pesos de la red neuronal y se adoptó QLoRA (Quantized Low-Rank Adaptation) en 4 bits, junto con la reestructuración del dataset al formato ChatML.

### Alternativas consideradas
1. **Full Fine-Tuning:** Modificar todos los parámetros del modelo base (7B parámetros) con los datos del dominio.
2. **LoRA (Low-Rank Adaptation):** Congelar los pesos originales e inyectar matrices de adaptación de bajo rango sin cuantización.
3. **QLoRA (Quantized LoRA):** Igual que LoRA pero con el modelo base cuantizado en 4 bits, reduciendo drásticamente el consumo de memoria.

### Por qué se descartó el Full Fine-Tuning
El primer intento de entrenamiento utilizó Full Fine-Tuning sobre Qwen 2.5 7B con un dataset en formato JSONL bruto. Los resultados fueron desastrosos:

- **Olvido Catastrófico (Catastrophic Forgetting):** Al modificar todos los pesos de la red neuronal con un dataset pequeño y específico, el modelo olvidó su conocimiento general. Perdió la capacidad de generar español gramaticalmente correcto y respondía de forma descontextualizada, repitiendo fragmentos del dataset de entrenamiento de forma mecánica.
- **Sobreajuste (Overfitting):** El modelo memorizó los pocos ejemplos del dataset en lugar de aprender patrones generalizables. Dado el tamaño relativamente reducido del corpus de ProFuturo comparado con los datos de preentrenamiento del modelo, la red acomodó toda su capacidad al dataset específico.
- **Consumo de recursos insostenible:** El entrenamiento completo de 7 mil millones de parámetros saturó las instancias `ml.g4dn.xlarge` de SageMaker, provocando errores de Out of Memory (OOM).

### Por qué se eligió QLoRA
QLoRA resolvió simultáneamente los tres problemas:

1. **Preservación del conocimiento base:** Al congelar los pesos originales de la red y únicamente entrenar matrices de adaptación de bajo rango (típicamente de rango r=16 o r=64), el modelo conserva todo su conocimiento general mientras adquiere las "habilidades" específicas del dominio ProFuturo.
2. **Cuantización en 4 bits:** La cuantización NF4 (Normal Float 4-bit) reduce el footprint de memoria del modelo de ~14 GB (fp16) a ~4 GB, permitiendo que tanto el entrenamiento como la inferencia quepan cómodamente en una sola GPU NVIDIA T4 (16 GB VRAM) de las instancias `ml.g4dn.xlarge`.
3. **Eficiencia de entrenamiento:** Los adaptadores LoRA representan menos del 1% de los parámetros totales del modelo, lo que reduce drásticamente el tiempo de entrenamiento y el coste computacional.

### La reestructuración a ChatML
Paralelamente al cambio de técnica de entrenamiento, se identificó que el dataset original estaba contaminado con ruido: instrucciones en múltiples idiomas, sesgos hacia la generación de reportes y formatos inconsistentes. Se desarrolló un script en Python para transformar un CSV con datos reales de foros de ProFuturo en un dataset conversacional estricto usando el formato ChatML (`<|im_start|>system`, `<|im_start|>user`, `<|im_start|>assistant`). Este formato estandarizado garantiza que el modelo aprende correctamente los turnos de conversación y sabe cuándo debe dejar de generar texto (gracias a los tokens de parada `<|im_end|>`).

### Reflexión técnica
La combinación QLoRA + ChatML representó el punto de inflexión del proyecto. Pasamos de un modelo que había "olvidado" cómo hablar español a un modelo que respondía con el tono, el vocabulario y la estructura propios de un auditor de comunidades educativas — sin perder su capacidad generalista de razonamiento.

---

## Decisión 4: Arquitectura Multi-Modelo (Operario + Cerebro) frente a Modelo Único

### Qué se eligió
Se diseñó inicialmente una arquitectura dual con dos modelos especializados, orquestados por LangGraph, que posteriormente fue simplificada a un modelo único por restricciones de infraestructura.

### Diseño de la arquitectura Multi-Modelo
La hipótesis inicial era que la separación de responsabilidades entre modelos optimizaría tanto el rendimiento como el coste:

- **El Operario (Qwen 3B):** Modelo ligero dedicado exclusivamente a la clasificación de intención. Su única función era leer el mensaje del usuario y emitir una etiqueta de clasificación (ej.: `TECNICO`, `ADMINISTRATIVO`, `SALUDO`, `CRITICO`). Al ser pequeño (3B parámetros), respondía en menos de 0.5 segundos y consumía mínimos recursos.
- **El Cerebro (Qwen 7B):** Modelo de mayor capacidad encargado de generar la respuesta final. Recibía del agente el contexto completo (etiqueta del Operario + datos de Neo4j + historial de conversación) y redactaba una respuesta detallada, empática y bien estructurada.

**Beneficios teóricos:**
- Especialización de tareas: cada modelo hace una sola cosa excepcionalmente bien.
- Ahorro de costes: para un simple saludo, no se enciende el modelo pesado.
- Modularidad: cada modelo puede actualizarse o reentrenarse de forma independiente.

### Por qué se pivotó al modelo único
En la práctica, la arquitectura dual colapsó por tres razones:

1. **Consumo de VRAM:** Ejecutar dos modelos simultáneamente en una sola instancia `ml.g4dn.xlarge` (16 GB VRAM) agotaba la memoria, provocando errores OOM y crashes del servidor de inferencia.
2. **Cold Starts:** Los endpoints de SageMaker tienen tiempos de arranque en frío (cold start) significativos. Mantener dos endpoints encendidos duplicaba el coste, mientras que apagarlos introducía latencias de varios minutos en la primera petición.
3. **Complejidad de enrutamiento:** Los bucles de enrutamiento entre el Operario y el Cerebro generaban errores intermitentes de conexión y timeouts que hacían el sistema inestable para una demo de producción.

### Modelo Único: La decisión de ingeniería
Aplicando el principio KISS (Keep It Simple, Stupid), se consolidó toda la inteligencia en un único endpoint con Qwen 2.5 7B entrenado con QLoRA. LangGraph conservó su rol de orquestador, pero ahora dirige todas las consultas a un solo modelo que asume tanto la clasificación como la generación.

### Reflexión técnica
La arquitectura multi-modelo quedó documentada en la memoria del TFG como prueba de diseño de sistemas complejos y se propone como línea de trabajo futuro. Esta decisión de documentar una arquitectura probada pero no desplegada tiene un alto valor académico: demuestra que el alumno comprende diseños avanzados y, al mismo tiempo, sabe justificar pragmáticamente por qué se optó por la alternativa más simple dadas las restricciones del entorno.

---

## Decisión 5: Despliegue en AWS (SageMaker + EC2) frente a Alternativas Cloud

### Qué se eligió
Se utilizó Amazon Web Services como plataforma cloud exclusiva, combinando SageMaker para entrenamiento e inferencia y EC2 para el backend.

### Alternativas consideradas
1. **Google Colab:** Utilizado en las primeras fases del proyecto para prototipado rápido de fine-tuning. Descartado porque los recursos son compartidos, efímeros y con límites estrictos de tiempo de ejecución.
2. **Inferencia local (Mac):** Se probó la ejecución del modelo en el equipo de desarrollo local. Descartado porque el Mac no dispone de GPU NVIDIA dedicada, lo que hacía que la inferencia tardara minutos en lugar de segundos.
3. **Ollama en EC2 (sin SageMaker):** Ejecutar Ollama directamente en la instancia EC2. Funcional para desarrollo, pero carece de las capacidades de gestión de ciclo de vida de modelos, autoescalado y monitorización que ofrece SageMaker.

### Reflexión técnica
La elección de SageMaker para el entrenamiento permitió adoptar un modelo de "pago por uso" donde la máquina con GPU se enciende exclusivamente durante la duración del Training Job (típicamente 20-40 minutos) y se apaga automáticamente al finalizar. En contraste, mantener una instancia EC2 con GPU encendida 24/7 para entrenamiento habría supuesto un sobrecoste de órdenes de magnitud superior. SageMaker también proporcionó una capa de abstracción sobre la gestión de contenedores Docker, la instalación de dependencias y el versionado de artefactos de entrenamiento.

---

## Decisión 6: GraphRAG (Neo4j) frente a RAG Vectorial Tradicional

### Qué se eligió
Se implementó GraphRAG con Neo4j como base de conocimiento, en lugar de un pipeline de RAG vectorial convencional con FAISS o Pinecone.

### Alternativas consideradas
1. **FAISS + ChromaDB:** Base de datos vectorial local para búsqueda por similitud.
2. **Pinecone:** Servicio gestionado de base de datos vectorial en la nube.
3. **Amazon OpenSearch:** Servicio de búsqueda vectorial integrado en el ecosistema AWS.

### Por qué se eligió Neo4j
Los datos de los foros de ProFuturo son inherentemente relacionales: un autor pertenece a una comunidad, escribe posts en hilos específicos, responde a otros autores y participa en debates temáticos. Un modelo de datos en grafo captura estas relaciones de forma nativa, permitiendo consultas que un sistema vectorial no puede resolver:

- *"¿Qué comunidades tienen usuarios que también participan en otras comunidades?"* (traversía multi-hop)
- *"¿Cuál es el autor más influyente del foro de tecnología educativa?"* (métricas de centralidad sobre el grafo)
- *"¿Hay patrones de negatividad recurrentes entre usuarios específicos?"* (análisis de subgrafos)

### Reflexión técnica
El trade-off principal fue la complejidad de implementación. GraphRAG requiere un pipeline de ingestión de datos más sofisticado (parsear hilos → crear nodos → establecer relaciones → mantener la coherencia del grafo) y un lenguaje de consulta específico (Cypher) que la búsqueda vectorial no necesita. Sin embargo, la riqueza del análisis relacional justifica la inversión técnica y constituye uno de los pilares diferenciadores del TFG.

---

## Decisión 7: Pivotaje de Hardware (Tesla T4 a NVIDIA A10G)

### Qué se eligió
Se migró la instancia de inferencia de la familia **ml.g4dn.xlarge** (Tesla T4) a la familia **ml.g5.xlarge** (NVIDIA A10G con 24GB VRAM).

### Por qué se eligió
Durante el despliegue del endpoint con TGI, se identificó una incompatibilidad crítica de los kernels de cuantización de `bitsandbytes` con la arquitectura Turing (compute capability 7.5) de las Tesla T4. El modelo no podía realizar la des-cuantización NF4 en tiempo real, provocando errores de punteros nulos. La migración a instancias G5 (Ampere) resolvió este bloqueo y proporcionó un 50% más de VRAM, permitiendo manejar contextos de conversación mucho más largos (hasta 8192 tokens).

---

## Decisión 8: Orquestación del Merge Job como Training Job

### Qué se eligió
La fusión de los adaptadores LoRA con el modelo base se configuró como un **SageMaker Training Job** utilizando instancias **ml.g4dn.2xlarge** con 32GB de RAM dedicado exclusivamente a la CPU.

### Por qué se eligió
SageMaker impone cuotas estrictas y diferenciadas para "Training", "Processing" e "Inference". Dada la limitación de cuotas de la cuenta institucional, se optó por "disfrazar" la tarea de procesamiento del merge como un Training Job. Esto permitió utilizar la cuota de entrenamiento disponible y, al mismo tiempo, aprovechar instancias con mayor RAM (2xlarge) para evitar el error SIGKILL del sistema operativo al cargar el modelo Qwen 7B en memoria fp16 para su fusión definitiva.
