# Funcionamiento del RPA y transferencia del MVP a AWS

## Que hace el RPA

El modulo RPA (`backend/scripts/rpa.py`) es un scheduler autonomo (APScheduler) que se lanza como hilo daemon al arrancar la API FastAPI. Gestiona cuatro tareas automatizadas:

| Job | Trigger | Estado |
|-----|---------|--------|
| `critical_monitor` | Cada 30 minutos | **Activo** |
| `weekly_summary` | Viernes a las 18:00 | **Activo** |
| `weekly_reminder` | Viernes a las 09:00 | Pendiente — requiere decision de ProFuturo |
| `mention_monitor` | Cada 5 minutos | Pendiente — requiere validacion del flujo |

### critical_monitor (activo)
Cada 30 minutos analiza los mensajes de las ultimas 24 horas buscando patrones de incidencia tecnica o situaciones criticas. Si el LLM los clasifica como CRITICA o ALTA, genera un PDF de alerta y lo envia por email al administrador.

### weekly_summary (activo)
Cada viernes a las 18:00 genera un resumen ejecutivo en PDF para cada comunidad activa y lo envia por email. Incluye: temas principales, nivel de participacion, tendencias y recomendaciones.

### weekly_reminder (pendiente de definicion con ProFuturo)
La idea es que el agente publique automaticamente un mensaje de recordatorio semanal en cada comunidad invitando a la participacion. El contenido lo genera el LLM basandose en la actividad de la semana. **Antes de activar este job es necesario acordar con ProFuturo:** que quieren que publique exactamente, en que hilo, con que tono, y si debe identificarse como IA o como cuenta institucional. La integracion tecnica depende de que Pinchtab exponga una API de publicacion.

### mention_monitor (pendiente de validacion)
Permite que los docentes mencionen al agente directamente en los foros con `@Auditor IA` para hacerle preguntas. El job detecta esas menciones y responde automaticamente escribiendo en Neo4j. Esta pensado como una funcionalidad de usuario final (no de admin), pero todavia no se ha presentado a ProFuturo — pueden aceptarla o descartarla. El flujo de escritura de vuelta a Pinchtab (que la respuesta aparezca en el foro real) tambien necesita validarse.

---

## Como verificar que funciona (en desarrollo y en demos)

### Log del scheduler — fuente de verdad

```
backend/profuturo_rpa.log
```

Cada ejecucion queda registrada. Si solo aparece "Scheduler started" y no hay lineas de "Iniciando ..._job", el scheduler esta en espera — completamente normal hasta que llegue el siguiente trigger.

### Endpoints de verificacion (ya implementados en la API)

```bash
# Estado del scheduler: esta corriendo? cuando es la proxima ejecucion?
curl http://localhost:8000/api/rpa/status

# Ver ultimas 50 lineas del log desde la API
curl "http://localhost:8000/api/rpa/logs?lines=50"

# Disparar el monitor de criticos manualmente (no esperar 30 min)
curl -X POST http://localhost:8000/api/rpa/trigger/critical_monitor

# Disparar el resumen semanal manualmente (tarda ~60s por el LLM)
curl -X POST http://localhost:8000/api/rpa/trigger/weekly_summary
```

### AWS CloudWatch (en produccion)

Los logs de aplicacion se envian a CloudWatch Logs. El log del endpoint TGI de SageMaker esta en:
- Grupo: `/aws/sagemaker/Endpoints/profuturo-auditor-tgi`
- Region: `eu-west-1`

---

## Configuracion de emails

```env
ADMIN_EMAIL=responsable@profuturo.org    # quien recibe informes y alertas
GMAIL_ADDRESS=cuenta@gmail.com           # cuenta remitente
GMAIL_APP_PASS=xxxx xxxx xxxx xxxx       # App Password de Google (no la contrasena normal)
```

Para crear un App Password: myaccount.google.com → Seguridad → Verificacion en dos pasos → Contrasenas de aplicaciones.

Si las variables no estan configuradas el scheduler sigue funcionando (guarda los PDFs en `backend/alerts/`) pero no envia email.

| Evento | Asunto del email | Adjunto |
|--------|-----------------|---------|
| Resumen semanal | `Resumen Semanal — {comunidad} — {fecha}` | PDF ejecutivo |
| Alerta CRITICA | `ALERTA CRITICA — {comunidad}` | PDF de incidencia |
| Alerta ALTA | `ALERTA ALTA — {comunidad}` | PDF de incidencia |

---

## Arquitectura de transferencia del MVP a AWS

### Estado actual del codigo

El codigo ya tiene toda la integracion con AWS implementada y lista:

- **LLM**: el modelo fine-tuneado (Qwen 2.5 7B con QLoRA) esta desplegado como endpoint TGI en SageMaker (`profuturo-auditor-tgi`, instancia `ml.g5.xlarge`, region `eu-west-1`). El backend lo llama mediante `boto3` con las credenciales AWS del `.env`.
- **Modelo base + adaptadores LoRA**: almacenados en S3 (`s3://profuturo-tfg/model/`).
- **Neo4j**: base de datos de grafos con todos los datos de los foros. Actualmente accesible via URI configurada en `.env`.

### Que falta para el despliegue en produccion

```
[ProFuturo Foros (Pinchtab)]
        |
        | (scraping periodico — pendiente de integracion)
        v
[Neo4j — base de datos de grafos]
        |
        | (queries en tiempo real)
        v
[FastAPI Backend + RPA Scheduler]  <-->  [SageMaker TGI Endpoint — Qwen 2.5 7B]
        |
        | (REST API)
        v
[Next.js Frontend]
```

El unico componente no automatizado todavia es la ingestion de datos: los foros de Pinchtab necesitan scrapearse periodicamente y volcarse a Neo4j. Ver `docs/flujo-datos-nuevos.md` para el detalle.

### Por que EC2 y no Lambda para el backend

El backend necesita correr **continuamente** (el RPA scheduler es un hilo daemon que no puede dormir). AWS Lambda no es adecuado porque:
- Timeout maximo de 15 minutos (insuficiente para inferencia LLM + scheduler)
- No mantiene estado entre invocaciones (el scheduler se reiniciaria en cada request)

**La opcion correcta es EC2:**

```
Instancia recomendada: t3.medium (2 vCPU, 4 GB RAM) — solo corre el backend Python, el LLM esta en SageMaker
Sistema operativo: Amazon Linux 2023 o Ubuntu 22.04
```

### Pasos de despliegue en EC2

```bash
# 1. En la instancia EC2
git clone <repo> /opt/profuturo
cd /opt/profuturo/backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 2. Configurar variables de entorno
cp .env.example .env
nano .env  # rellenar NEO4J_URI, AWS credentials, GMAIL, etc.

# 3. Asignar un IAM Role a la instancia EC2 con permisos:
#    - sagemaker:InvokeEndpoint (sobre el endpoint TGI)
#    - s3:GetObject (sobre el bucket del modelo)
#    Con IAM Role no hacen falta AWS_ACCESS_KEY_ID en el .env

# 4. Levantar el backend como servicio systemd (para que arranque solo al reiniciar)
sudo nano /etc/systemd/system/profuturo.service
```

Contenido del servicio systemd:

```ini
[Unit]
Description=ProFuturo Auditor IA Backend
After=network.target

[Service]
User=ec2-user
WorkingDirectory=/opt/profuturo/backend
ExecStart=/opt/profuturo/backend/venv/bin/uvicorn src.main:app --host 0.0.0.0 --port 8000
Restart=always
EnvironmentFile=/opt/profuturo/backend/.env

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable profuturo
sudo systemctl start profuturo
sudo systemctl status profuturo
```

### Conectividad con Neo4j (VPN / red privada de ProFuturo)

Si Neo4j esta en la red interna de ProFuturo:
- Opcion A: **VPC Peering** entre la VPC de EC2 y la red de ProFuturo (si usan AWS)
- Opcion B: **VPN Site-to-Site** entre EC2 y el datacenter de ProFuturo
- Opcion C: **Neo4j AuraDB** (servicio gestionado de Neo4j en cloud) — la opcion mas simple para un MVP

En todos los casos solo hay que actualizar `NEO4J_URI` en el `.env` de la instancia EC2.

### Resumen de lo que ProFuturo recibiria

| Componente | Donde esta | Quien lo gestiona |
|------------|-----------|------------------|
| Modelo LLM (Qwen 2.5 7B) | SageMaker TGI `eu-west-1` | AWS (Javier lo despliega) |
| Adaptadores LoRA + dataset | S3 `profuturo-tfg` | AWS (Javier lo sube) |
| Backend API + RPA scheduler | EC2 `t3.medium` | ProFuturo (o Javier durante MVP) |
| Frontend Next.js | EC2 o Vercel | ProFuturo |
| Base de datos Neo4j | AuraDB o servidor propio | ProFuturo |
| Foros (datos fuente) | Pinchtab (plataforma de ProFuturo) | ProFuturo |
