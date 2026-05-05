# Despliegue en EC2 — Auditor IA ProFuturo

## Datos de conexion

| Campo       | Valor                  |
|-------------|------------------------|
| Instance ID | [rellenar]             |
| IP / DNS    | [rellenar]             |
| Key pair    | [rellenar].pem         |
| OS          | Ubuntu 22.04           |

```bash
ssh -i "[rellenar].pem" ubuntu@[IP_EC2]
```

---

## Modelo fine-tuned (SageMaker TGI)

| Campo     | Valor                                        |
|-----------|----------------------------------------------|
| Endpoint  | profuturo-auditor-tgi (SageMaker)            |
| Variable  | `PROFUTURO_ENDPOINT=profuturo-auditor-tgi`   |
| Región    | eu-west-1                                    |

El backend llama al endpoint vía boto3/sagemaker-runtime. No se expone directamente.

---

## Despliegue del backend

```bash
# 1. Clonar repo
git clone https://github.com/javierpozogonzalez/tfg-auditor-ia-profuturo.git /opt/auditor-ia
cd /opt/auditor-ia/backend

# 2. Entorno virtual
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 3. Variables de entorno
cp .env.example .env
nano .env   # rellenar todos los campos

# 4. Carga inicial de datos en Neo4j (solo primera vez)
python scripts/ingest_neo4j.py

# 5. Servicio systemd
sudo cp deploy/auditor-ia.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable auditor-ia
sudo systemctl start auditor-ia

# 6. Frontend (Next.js estático o servidor)
cd /opt/auditor-ia
npm install && npm run build
# Servir con nginx o: npm start
```

---

## Variables .env necesarias

```env
# Neo4j
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=

# AWS / SageMaker
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_REGION=eu-west-1
PROFUTURO_ENDPOINT=profuturo-auditor-tgi
LLM_TEMPERATURE=0.1
LLM_MAX_TOKENS=2048

# Moodle
MOODLE_URL=https://profuturo.moodlecloud.com
MOODLE_API_TOKEN=          # token del usuario "auditor_ia"
MOODLE_DEFAULT_FORUM_ID=1
MOODLE_SIMULATION_MODE=true

# Agente autonomo
AUTONOMOUS_AGENT_ENABLED=false
MAX_REACTIVATIONS_PER_RUN=5
MAX_WELCOMES_PER_RUN=10
MAX_MENTIONS_PER_RUN=10

# Sincronizacion Moodle → Neo4j
MOODLE_SYNC_COURSE_IDS=1,2,3     # IDs de cursos ProFuturo a sincronizar
MOODLE_SYNC_INTERVAL_HOURS=6     # cada cuantas horas sincronizar

# Email alertas (RPA)
ADMIN_EMAIL=
GMAIL_ADDRESS=
GMAIL_APP_PASS=

# API
API_HOST=0.0.0.0
API_PORT=8000
CORS_ORIGINS=https://[dominio-frontend]

# Frontend
NEXT_PUBLIC_API_URL=https://[dominio-backend]
```

---

## Pipeline de datos en tiempo real: Moodle → Neo4j

El script `backend/scripts/moodle_sync.py` mantiene Neo4j actualizado automáticamente.

**Flujo:**
```
ProFuturo Moodle API
       │  (REST wstoken)
       ▼
moodle_sync.py  ──▶  filtra posts nuevos desde last_sync
       │
       ▼
Neo4j  ──▶  MERGE Author, Discussion, Community, Post
       │
       ▼
Agente IA  ──▶  consulta siempre datos frescos
```

**Activación:**
- El scheduler del backend ejecuta `moodle_sync_job()` cada `MOODLE_SYNC_INTERVAL_HOURS` horas
- Requiere `MOODLE_API_TOKEN` real (solicitarlo a ProFuturo junto con IDs de cursos)
- Primer sync: descarga los últimos 90 días. Syncs posteriores: solo incrementales

**Para activar:**
```env
MOODLE_API_TOKEN=wsxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
MOODLE_SYNC_COURSE_IDS=101,102,103
AUTONOMOUS_AGENT_ENABLED=true
MOODLE_SIMULATION_MODE=false
```

---

## Nginx (proxy inverso)

```nginx
server {
    listen 443 ssl;
    server_name [dominio];

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
    }

    location / {
        proxy_pass http://127.0.0.1:3000;
    }
}
```

---

## Comandos utiles

```bash
# Estado del servicio
sudo systemctl status auditor-ia

# Logs en tiempo real
sudo journalctl -u auditor-ia -f

# Reiniciar
sudo systemctl restart auditor-ia

# Logs del agente autonomo
tail -f /opt/auditor-ia/backend/autonomous_agent.log

# Forzar sync manual de Moodle → Neo4j
cd /opt/auditor-ia/backend && python scripts/moodle_sync.py --once
```
