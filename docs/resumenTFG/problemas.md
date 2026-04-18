# Retos Técnicos, Problemas y Diagnóstico de Soluciones

## Introducción

El camino desde el prototipo académico hasta el sistema funcional desplegado en AWS estuvo plagado de bloqueos técnicos reales. Cada uno de ellos se documenta aquí con el rigor que exige una memoria de ingeniería: describiendo el contexto en el que apareció, la causa raíz diagnosticada, la solución aplicada y el aprendizaje técnico extraído. Los problemas se presentan en orden cronológico.

---

## Problema 1: Olvido Catastrófico en el Modelo (Catastrophic Forgetting)

### Contexto
En la fase inicial del proyecto se realizó un entrenamiento completo (Full Fine-Tuning) del modelo Qwen 2.5 7B. Se modificaron todos los pesos de la red neuronal utilizando un dataset en formato JSONL preparado con datos de los foros de ProFuturo. El objetivo era especializar el modelo en el dominio educativo de la fundación.

### Manifestación del problema
Tras completar el entrenamiento, el modelo perdió su capacidad de generar texto coherente en español. Las respuestas eran fragmentos mecánicos del dataset de entrenamiento, repetidos fuera de contexto. El modelo había "olvidado" el conocimiento general adquirido durante su preentrenamiento: no podía mantener una conversación fluida, no comprendía preguntas formuladas con variaciones lingüísticas y mostraba un sobreajuste severo a los pocos ejemplos del dataset de ProFuturo.

### Causa raíz
El fenómeno de olvido catastrófico ocurre cuando un modelo preentrenado ve todos sus pesos modificados por un corpus de entrenamiento significativamente más pequeño que los datos originales de preentrenamiento. Al actualizar los ~7 mil millones de parámetros con apenas unos miles de ejemplos, la red neuronal acomodó toda su representación interna al nuevo dataset, destruyendo las representaciones generales aprendidas previamente. Adicionalmente, el dataset contenía ruido: instrucciones en varios idiomas, sesgos hacia generación de reportes y formatos inconsistentes entre ejemplos.

### Solución aplicada
Se abandonó el Full Fine-Tuning y se adoptó QLoRA (Quantized Low-Rank Adaptation) en 4 bits. Esta técnica congela todos los pesos originales del modelo y únicamente entrena matrices de adaptación de bajo rango — típicamente menos del 1% de los parámetros totales. De esta forma, el modelo conserva íntegramente su conocimiento general mientras adquiere las habilidades específicas del dominio ProFuturo.

Simultáneamente, se descartó el dataset defectuoso y se creó un pipeline de limpieza en Python que transformó los CSV con datos reales de foros en un formato conversacional estricto ChatML (`<|im_start|>system`, `<|im_start|>user`, `<|im_start|>assistant`, `<|im_end|>`), eliminando el ruido y garantizando la coherencia de turnos.

### Aprendizaje
El Full Fine-Tuning solo es viable cuando se dispone de un corpus de entrenamiento de tamaño y diversidad comparables al preentrenamiento original. Para dominios específicos con datasets pequeños, las técnicas de adaptación paramétrica eficiente (PEFT) como LoRA y QLoRA son la opción correcta. La calidad y el formato del dataset son tan importantes como la técnica de entrenamiento: un dataset ruidoso producirá un modelo ruidoso, independientemente de la sofisticación del algoritmo empleado.

---

## Problema 2: Bloqueo de IAM y Políticas MFA en AWS (AccessDenied 403)

### Contexto
Al configurar el pipeline de entrenamiento en SageMaker, el flujo requería que los Training Jobs descargasen el dataset de entrenamiento desde un bucket S3. La arquitectura estándar de SageMaker asume que el rol de ejecución (SageMaker Execution Role) tiene permisos de lectura sobre S3.

### Manifestación del problema
El Training Job fallaba inmediatamente al arrancar con un error `AccessDenied 403` al intentar acceder al bucket S3. Los intentos de listar buckets, crear nuevos buckets o modificar políticas IAM desde la consola también resultaban en errores de permisos 403 o "Forbidden".

### Causa raíz
La cuenta de AWS del proyecto era una cuenta educativa gestionada por la organización (ProFuturo), con políticas de seguridad extremadamente restrictivas:
- Las políticas Service Control Policies (SCP) bloqueaban la creación de nuevos buckets S3 y la modificación de roles IAM.
- El acceso programático (via Access Keys) estaba protegido por MFA (Multi-Factor Authentication), lo que significaba que las credenciales estáticas del usuario caducaban y requerían un token temporal para cada sesión.
- El usuario asignado no tenía el permiso `iam:PassRole`, necesario para que SageMaker asuma el rol de ejecución durante un Training Job.

### Solución aplicada
Se implementaron múltiples estrategias complementarias:

**Estrategia 1 — Empaquetado Local del Dataset:**
En lugar de que SageMaker descargase el dataset de S3 durante el entrenamiento, se inyectó el dataset directamente en el contenedor Docker del Training Job a través del parámetro `source_dir` de la API de SageMaker. De esta forma, el script de entrenamiento y los datos viajan juntos como un paquete, eliminando la necesidad de acceso a S3 durante la ejecución.

**Estrategia 2 — Generador de Tokens STS:**
Se desarrolló un script en Python (`generate_sts_token.py`) que utiliza el servicio AWS STS (Security Token Service) para generar credenciales temporales con sesión MFA. El script solicita el código MFA del dispositivo virtual, genera un `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` y `AWS_SESSION_TOKEN` temporales (válidos durante 12 horas) y los escribe en el archivo `.env` del proyecto. Esto permitió que Boto3 y el SDK de SageMaker pudieran autenticarse correctamente.

**Estrategia 3 — Escalado al administrador:**
Para las operaciones que requerían `iam:PassRole` (despliegue de endpoints), fue necesario contactar al administrador de la cuenta AWS para solicitar la activación temporal de este permiso en el rol del usuario del proyecto.

### Aprendizaje
En entornos empresariales con cuentas AWS gestionadas, la seguridad por defecto puede ser un obstáculo significativo para el desarrollo. Es fundamental comprender las políticas de la organización antes de diseñar la arquitectura, y tener planes de contingencia para los bloqueos de permisos. El patrón de empaquetado local del dataset es una técnica válida y documentada para entornos donde S3 no es accesible directamente desde los Training Jobs. La generación programática de tokens STS con MFA es una práctica estándar en entornos corporativos que debe integrarse en el flujo de trabajo desde el inicio.

---

## Problema 3: Inferencia Infinita y Timeouts del Backend (El "Micrófono Abierto")

### Contexto
Tras desplegar el modelo entrenado con QLoRA en un endpoint de SageMaker, se conectó el backend de FastAPI para realizar la primera prueba de inferencia end-to-end. El backend enviaba la consulta del usuario al endpoint y esperaba la respuesta.

### Manifestación del problema
Las primeras peticiones tardaban más de 60 segundos en devolver una respuesta, momento en el cual el servidor FastAPI abortaba la conexión con un error `ReadTimeoutError`. En los logs de CloudWatch se observaba que el modelo seguía generando texto indefinidamente, sin detenerse, alcanzando los miles de tokens de salida.

### Causa raíz
El problema, denominado internamente como el "Síndrome del Micrófono Abierto", tenía una explicación técnica precisa: el modelo no recibía las instrucciones de parada correctas en el payload de inferencia. Cuando un modelo generativo recibe un prompt sin tokens de parada (stop tokens), continúa generando texto hasta alcanzar el límite máximo de tokens configurado — que por defecto puede ser de miles de tokens. El contenedor de inferencia de HuggingFace en SageMaker espera que los stop tokens se especifiquen explícitamente en el JSON de la petición, pero la integración por defecto de LangChain para SageMaker no los incluía.

Además, el fenómeno del "cold start" agravaba el problema: la primera invocación tras desplegar el endpoint requería que la máquina cargase el modelo completo en la GPU, añadiendo varios minutos de latencia adicional antes de que la inferencia pudiera comenzar.

### Solución aplicada
Se desarrolló un `LLMContentHandler` personalizado para la integración de LangChain con SageMaker. Este handler customizado realiza dos funciones críticas:

1. **Inyección de stop tokens:** En el método `transform_input`, el handler añade explícitamente los tokens de parada propios del modelo Qwen (los tokens especiales ChatML de fin de turno) al payload JSON de la petición. De esta forma, el modelo sabe cuándo debe dejar de generar texto.
2. **Estructuración del payload:** El handler formatea la petición en el formato JSON estricto que exige el contenedor de inferencia de HuggingFace en SageMaker, incluyendo parámetros de generación como `max_new_tokens`, `temperature` y `do_sample`.

Además, se aumentó el timeout del cliente Boto3 de 60 a 120 segundos para acomodar el cold start de la primera invocación, y se documentó que la primera petición tras desplegar un endpoint siempre tardará más debido a la carga del modelo en GPU.

### Aprendizaje
La integración entre frameworks de alto nivel (LangChain) y servicios cloud (SageMaker) raramente funciona out-of-the-box con modelos personalizados. La creación de un `ContentHandler` customizado es un patrón esencial para cualquier despliegue de modelos fine-tuneados en SageMaker. Los stop tokens no son opcionales: son la diferencia entre un modelo que responde en 2 segundos y uno que se cuelga durante 60 segundos generando texto basura. Entender la anatomía del payload de inferencia (formato de entrada, parámetros de generación, tokens de control) es un conocimiento crítico que no suele cubrirse en tutoriales introductorios.

---

## Problema 4: Conflictos de Paquetes en Contenedores SageMaker (Dependency Hell)

### Contexto
Los Training Jobs de SageMaker utilizan contenedores Docker preconfigurados por AWS (Deep Learning Containers) que incluyen versiones específicas de PyTorch, CUDA y las librerías fundamentales de HuggingFace. El script de fine-tuning QLoRA requería versiones específicas de `transformers`, `trl`, `peft` y `bitsandbytes` para funcionar correctamente.

### Manifestación del problema
Los Training Jobs fallaban durante la fase de inicialización del script de entrenamiento con errores variados:
- `NameError: name 'torch' is not defined` — indicando un conflicto en la importación de PyTorch.
- `Tokenizer no encontrado` — el tokenizer del modelo no podía cargarse porque la versión de `transformers` instalada no era compatible con el formato del modelo.
- Errores silenciosos donde el entrenamiento aparentaba progresar pero producía adaptadores corruptos.

### Causa raíz
La colisión se producía porque el contenedor Docker de SageMaker ya incluía una versión de PyTorch (instalada a nivel de sistema) y el archivo `requirements.txt` del proyecto intentaba instalar versiones diferentes o incompatibles de las librerías dependientes. Las librerías `trl` (para el entrenamiento con SFTTrainer), `peft` (para los adaptadores LoRA) y `bitsandbytes` (para la cuantización en 4 bits) tienen dependencias cruzadas estrictas con versiones específicas de `transformers` y `torch`. Instalar una combinación incorrecta provocaba fallos en cascada.

### Solución aplicada
Se creó un archivo `requirements.txt` con versiones estrictamente congeladas y compatibles entre sí, verificadas manualmente contra la versión de PyTorch nativa del contenedor de AWS:

```
transformers==4.45.2
trl==0.8.1
peft==0.11.1
bitsandbytes==0.43.1
datasets==2.19.0
accelerate==0.30.0
```

Este archivo se incluía en el `source_dir` del Training Job, forzando a SageMaker a instalar exactamente estas versiones antes de ejecutar el script de entrenamiento. La clave fue no incluir `torch` en el `requirements.txt`, permitiendo que el contenedor usase su propia instalación nativa de PyTorch (que ya estaba optimizada para las GPUs NVIDIA T4 de la instancia `ml.g4dn.xlarge`).

### Aprendizaje
El versionado estricto de dependencias (dependency pinning) no es una buena práctica opcional: es un requisito obligatorio en entornos de entrenamiento remoto donde el contenedor base no se controla directamente. Cada vez que se cambia una versión de cualquier librería del ecosistema HuggingFace, se debe verificar la compatibilidad con todas las demás dependencias. La documentación de las versiones exactas que funcionan es un artefacto de ingeniería tan valioso como el propio código de entrenamiento.

---

## Problema 5: Agotamiento de Memoria GPU y RAM (Out of Memory)

### Contexto
Este problema se manifestó en múltiples fases del proyecto, tanto en el entorno de desarrollo local (Mac) como en las instancias de AWS.

### Manifestación del problema — Entorno local
Al intentar ejecutar dos modelos simultáneamente en la máquina de desarrollo (el "Operario" Qwen 3B y el "Cerebro" Qwen 7B) mediante Ollama, la carga combinada excedía la memoria disponible del sistema. El equipo Mac no disponía de GPU NVIDIA dedicada, por lo que toda la inferencia se ejecutaba en CPU con aceleración Metal limitada. Los tiempos de respuesta eran de varios minutos por consulta, haciendo inviable el desarrollo iterativo.

### Manifestación del problema — AWS
Al intentar fusionar los adaptadores LoRA con los pesos base del modelo en un SageMaker Notebook, la operación de merge requería cargar el modelo completo en FP16 (~14 GB) más los adaptadores en memoria simultáneamente. La instancia del notebook (que tenía menos RAM disponible que la instancia de entrenamiento) fallaba con un error `OutOfMemoryError`.

### Causa raíz
- **Local:** La arquitectura Apple Silicon del Mac, aunque potente para tareas generales, no ofrece la VRAM dedicada ni los CUDA Cores necesarios para inferencia eficiente de modelos LLM de más de 3B parámetros. La inferencia en CPU es orden de magnitud más lenta que en GPU NVIDIA.
- **AWS:** La operación de merge de pesos requiere más memoria que el entrenamiento con QLoRA (donde el modelo base está cuantizado a 4 bits). Al descargar el modelo a FP16 para la fusión, el consumo de memoria se multiplica por 3-4x respecto al consumo durante el entrenamiento.

### Solución aplicada
**En el entorno local:**
- Se abandonó la ejecución dual de modelos y se pivotó a un modelo único.
- Se configuraron técnicas de memoria Swap virtual para extender la RAM disponible del Mac durante sesiones de desarrollo intensivas.
- Se priorizó la migración a AWS para toda operación de inferencia que requiriese rendimiento en tiempo real.

**En AWS:**
- Se implementó la fusión de pesos directamente en la instancia de entrenamiento (que disponía de más memoria) en lugar de en la instancia de notebook.
- Se adoptó la técnica de desplegar directamente los adaptadores LoRA sobre el modelo base cuantizado (sin fusión previa), utilizando `bitsandbytes` para cuantización en inferencia. Esta técnica evita la necesidad de la operación de merge y permite que el modelo completo (base + adaptadores) quepa en la GPU de la instancia `ml.g4dn.xlarge`.

### Aprendizaje
La gestión de memoria es el cuello de botella real en el despliegue de modelos LLM. Las estimaciones teóricas de consumo de VRAM deben multiplicarse por un factor de seguridad de 1.5x-2x para acomodar los buffers de generación, el KV-cache y las estructuras auxiliares del framework de inferencia. La decisión de desplegar adaptadores LoRA sin fusionar (usando PEFT en inferencia) es una práctica avanzada que sacrifica una mínima velocidad (~5% de overhead) a cambio de una reducción drástica de los requisitos de memoria.

---

## Problema 6: Conflictos de Puerto y Conectividad entre Backend y Endpoints

### Contexto
El sistema requiere la coordinación de múltiples servicios ejecutándose simultáneamente: el frontend de Next.js (puerto 3000), el backend de FastAPI (puerto 8000), Neo4j (puertos 7474/7687) y, opcionalmente, Ollama (puerto 11434).

### Manifestación del problema
Al arrancar el backend, los logs mostraban errores de tipo `Address already in use` o la conexión al endpoint de SageMaker fallaba sin error visible. En otros casos, el frontend enviaba peticiones correctamente pero recibía errores CORS o respuestas vacías.

### Causa raíz
Procesos zombi de sesiones anteriores de desarrollo ocupaban los puertos necesarios. Además, la URL del endpoint de SageMaker cambiaba cada vez que se redesplegaba el modelo, y si el archivo `.env` no se actualizaba con la nueva URL, el backend apuntaba a un endpoint inexistente o inactivo.

### Solución aplicada
- Se estableció un protocolo de arranque sistemático: verificar puertos libres con `lsof -i :8000`, matar procesos residuales, verificar que las variables de entorno apuntan al endpoint activo, y solo entonces arrancar los servicios en el orden correcto (Neo4j → Backend → Frontend).
- Se cambió el puerto del backend de 8000 a otro cuando el conflicto con el puerto por defecto de macOS era persistente.
- Se documentó la secuencia de arranque completa como un script de verificación reutilizable.

### Aprendizaje
La orquestación de múltiples servicios locales requiere disciplina operacional. Un simple puerto bloqueado puede generar horas de debugging si no se tiene un checklist de arranque. La recomendación para entornos de producción es utilizar Docker Compose para gestionar la orquestación de servicios, eliminando los conflictos de puertos y las dependencias del sistema operativo del desarrollador.

---

## Problema 7: Incompatibilidad de bitsandbytes con Tesla T4 (Compute 7.5)

### Contexto
Durante el despliegue del modelo cuantizado en SageMaker utilizando el contenedor TGI, se intentó utilizar instancias `ml.g4dn.xlarge` (que montan una GPU NVIDIA Tesla T4 con arquitectura Turing).

### Manifestación del problema
El contenedor arrancaba pero el modelo fallaba al cargar con un error de segmentación o un error de tipo `AttributeError: 'NoneType' object has no attribute 'cquantize_blockwise_fp16_nf4'`. La inferencia no llegaba a activarse.

### Causa raíz
TGI y las versiones recientes de `bitsandbytes` requieren kernels CUDA específicos para realizar la cuantización NF4. La arquitectura Turing (Compute Capability 7.5) presenta incompatibilidades con ciertas optimizaciones de bajo nivel de estos kernels en contenedores TGI modernos, resultando en punteros nulos durante la des-cuantización dinámica.

### Solución aplicada
Se migró el despliegue de producción a instancias de la familia **ml.g5.xlarge**, las cuales utilizan GPUs NVIDIA A10G (arquitectura Ampere, Compute Capability 8.6). Estas GPUs son totalmente compatibles con los kernels optimizados, permitiendo una ejecución estable y un 50% de aumento en la velocidad de inferencia.

### Aprendizaje
La compatibilidad a nivel de arquitectura de GPU (Compute Capability) es tan crítica como la cantidad de VRAM disponible. No todas las GPUs NVIDIA "capaces" de ejecutar CUDA son compatibles con todas las optimizaciones de vanguardia de LLMs.

---

## Problema 8: Restricción de Cuotas de AWS para Instancias de Cómputo

### Contexto
Para realizar la operación de fusionado (merge) del modelo, se requería una instancia con al menos 32GB de RAM para evitar el error SIGKILL del sistema operativo al cargar los pesos del modelo 7B en fp16.

### Manifestación del problema
Al intentar lanzar un "Processing Job" o levantar una instancia de notebook mayor, AWS devolvía el error `ResourceLimitExceeded`, indicando que la cuota para ese tipo de uso era 0.

### Causa raíz
Las cuentas de AWS institucionales suelen tener cuotas segregadas por "casos de uso": Training, Processing e Inference. En este caso, la cuota para "Processing Jobs" de nivel g4dn estaba agotada o no habilitada, pero existía cuota disponible para "Training Jobs".

### Solución aplicada
Se orquestó el script de merge como un **SageMaker Training Job**. Aunque conceptualmente no es un entrenamiento, esta estrategia permitió utilizar la cuota de cómputo de "Training" disponible en la cuenta para realizar el merge en una instancia **ml.g4dn.2xlarge** (32GB RAM).

### Aprendizaje
La flexibilidad en la nube a veces requiere "re-etiquetar" las tareas para ajustarse a las restricciones de gobernanza y cuotas de la infraestructura disponible. La capacidad de adaptar el código para que corra en distintos entornos de Amazon (Training vs Processing) es una habilidad de ingeniería cloud fundamental.

---

## Problema 9: Error de Tensores "Meta" (no data) al Guardar el Modelo Fusionado

### Contexto
Durante el script de merge ejecutado en AWS, se utilizaba la configuración `low_cpu_mem_usage=True` de la librería `transformers` para optimizar la carga del modelo base Qwen 2.5 7B en RAM.

### Manifestación del problema
Tras realizar el `merge_and_unload()` con éxito aparente, el script fallaba al intentar guardar el modelo fusionado (`save_pretrained`) con el error: `RuntimeError: Cannot copy out of meta tensor; no data!`.

### Causa raíz
Al usar `low_cpu_mem_usage=True` junto con un `device_map` explícito a "cpu", la librería `transformers` carga el modelo utilizando tensores "meta". Estos tensores reservan el espacio necesario pero no contienen los datos físicos de los pesos. PEFT y el método de merge no siempre disparan la carga real (materialización) de estos tensores antes del guardado.

### Solución aplicada
Se eliminó el parámetro `low_cpu_mem_usage=True` y se forzó una carga limpia del modelo base directamente en CPU mediante `model.cpu()` tras montar los adaptadores LoRA. Además, se aumentó la memoria swap de la instancia para soportar la carga fp16 sin recurrir a tensores meta.

### Aprendizaje
Las optimizaciones de memoria "mágicas" de los frameworks pueden ser contraproducentes cuando se realizan operaciones de escritura en disco o transformaciones de arquitectura del modelo. A veces, la carga "pesada" y explícita es necesaria para garantizar la integridad de los datos.

