# Limpieza inicial del repositorio

**Fecha:** 2026-04-18
**Tipo:** refactor
**Componente:** backend

## Contexto

Tras el primer push a GitHub se realizo una auditoria completa del codigo para eliminar
ficheros obsoletos acumulados a lo largo de las cinco fases del proyecto. El objetivo
es que el repositorio refleje unicamente el sistema funcional descrito en la arquitectura,
sin artefactos de iteraciones anteriores que puedan confundir a un lector externo o
provocar importaciones erroneas.

## Cambio implementado

Se eliminaron seis ficheros:

| Fichero | Motivo |
|---|---|
| `backend/src/api.py` | Implementacion alternativa del backend FastAPI sin RPA, sin manejo de PDFs en respuesta y con timestamp hardcodeado. Reemplazada por `main.py`, que es el unico entry point real. |
| `backend/src/neo4j_client.py` | Clase `Neo4jGraphClient` con schema Neo4j en español (`Mensaje`, `Comunidad`, relaciones `PERTENECE_A`, `ESCRIBIO`) incompatible con el schema en ingles del sistema actual (`Post`, `Author`, `WROTE`, `IN_DISCUSSION`). No estaba importada en ningun fichero. |
| `backend/scripts/test_db.py` | Script de debug ad-hoc con ruta `.env` incorrecta hardcodeada (`../../.env`). Sin funcion en produccion. |
| `backend/scripts/ingest.py` | ETL de ingesta con schema alternativo (`BELONGS_TO`, `ABOUT`) que no coincide con las queries de `main.py`. Reemplazado por `ingest_neo4j.py`. |
| `backend/scripts/prepare_finetuning_dataset.py` | Generador de dataset para Llama 3.2 en formato multilingual (ES/EN/PT/FR). Obsoleto tras el pivote a Qwen 2.5 + ChatML en la Fase 4. |
| `backend/preparar_dataset.py` | Copia residual del generador de dataset en la raiz del backend. El pipeline vigente es `backend/training/preparar_dataset.py` (formato ChatML estricto para el Training Job de QLoRA). |

Se conservo `backend/scripts/clean_data.py` como artefacto de reproducibilidad del
pipeline de preparacion del CSV bruto (capítulo 5 de la memoria), anadiendo un docstring
que lo identifica como script de one-shot.

## Impacto

- El repositorio queda con un unico entry point de backend claro: `backend/src/main.py`.
- Se elimina la confusion entre dos schemas de Neo4j coexistentes.
- Se eliminan tres versiones paralelas de generacion de dataset, dejando una sola (`training/preparar_dataset.py`).
- Ninguna importacion quedo huerfana (verificado con grep en todo el proyecto).

## Archivos modificados

- `backend/scripts/test_db.py` — eliminado
- `backend/src/neo4j_client.py` — eliminado
- `backend/scripts/ingest.py` — eliminado
- `backend/scripts/prepare_finetuning_dataset.py` — eliminado
- `backend/src/api.py` — eliminado
- `backend/preparar_dataset.py` — eliminado
- `backend/scripts/clean_data.py` — docstring anadido
