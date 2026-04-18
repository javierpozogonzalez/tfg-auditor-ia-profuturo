# Evolución del Proyecto (Timeline y Fases)

La progresión real que ha confluido en el estado final óptimo del modelo se define en las siguientes 5 fases iterativas de prueba de concepto e implementación.

## Fase 1: Prototipo Transaccional Inicial
Arrancó como una integración preliminar mediante algoritmos de Recuperación QA Extractiva.
- Se instauró el modelo **BETO** desde Hugging Face.
- Se experimentó en un Google Colab con limpieza rápida de CVS en forma manual.
- Las respuestas resultantes eran literales y faltas de nivel discursivo fluido.

## Fase 2: Salto Cognitivo y "Amnesia de Base"
Primera iteración por ampliar el comportamiento generativo puro a gran escala.
- Ejecución completa de entrenamiento tradicional (Full Fine-Tuning) probando con modelos como Qwen 7B.
- Formato de datos primario: Listados en JSONL no adaptativo.
- Resultado: Choque severo de sobreajuste y un "Olvido Catastrófico". El NLP perdía la sintaxis externa ganando latencia en los cálculos masivos de matrices.

## Fase 3: Pivotaje hacia la Modularidad (Agencia de Tareas Computacionales)
Ante la carga monolítica de un único gran cerebro que hacía mal tareas dispares, el paradigma pivotó con LangGraph.
- Establecimiento de dos subsistemas lógicos asíncronos: El "Operario" ligero de enrutamiento temprano y "Cerebro", un agente profundo e intensivo.
- Creación de cuellos de botella RAM en infraestructuras y escalados locales de bajo VRAM.

## Fase 4: Especialización de Precisión y Escalado AWS
La convergencia arquitectónica final de modelo, entrenamiento y cloud.
- Adopción completa del esquema algorítmico **QLoRA 4-bit** y reformulación integral de limpieza a **ChatML**. Permitió entrenar sin alterar los pesos intrínsecos de la base neuro-lingüística.
- Despliegue en red Amazon Web Services (SageMaker para entrenamientos cortos intensivos bajo máquinas EC2 estables `g4dn.xlarge`).

## Fase 5: Consolidación Producción End-to-End
Solución y refinamiento de interfaces agnósticas a nivel empresarial (Ready para un despliegue).
- Empalme e inyecciones de conectividad en Next.js.
- Refactorización de FastAPI con StopTokens nativos solucionando timeouts de LangChain.
- Resolución asíncrona de los AccessDenied y las trabas en CloudWatch hasta obtener luz verde sistemática, habilitando al modelo a responder directamente sobre los dominios forales.
