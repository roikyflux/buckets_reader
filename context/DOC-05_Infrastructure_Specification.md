# DOC-05 — Especificación de Infraestructura

**Proyecto:** ETL Bucket Service  
**Versión:** 1.0  
**Estado:** APROBADO  
**Fecha:** Marzo 2025  
**Depende de:** DOC-01 — ADRs, DOC-02 — Especificación de Componentes  
**Siguiente documento:** DOC-06 — Flujo N8N  

---

## Tabla de Contenidos

1. [Visión General del Entorno](#1-visión-general-del-entorno)
2. [Topología de Red](#2-topología-de-red)
3. [Docker Compose](#3-docker-compose)
4. [Dockerfile del Microservicio](#4-dockerfile-del-microservicio)
5. [Variables de Entorno](#5-variables-de-entorno)
6. [Gestión de Secretos](#6-gestión-de-secretos)
7. [Health Checks](#7-health-checks)
8. [Procedimientos Operacionales](#8-procedimientos-operacionales)
9. [Consideraciones de Seguridad de Infraestructura](#9-consideraciones-de-seguridad-de-infraestructura)
10. [Historial de Revisiones](#10-historial-de-revisiones)

---

## 1. Visión General del Entorno

### 1.1 Infraestructura Base

| Componente | Valor |
|---|---|
| Proveedor cloud | Google Cloud Platform (GCP) |
| Tipo de instancia | VM (Compute Engine) |
| Sistema operativo | Linux (Ubuntu 22.04 LTS recomendado) |
| Runtime de contenedores | Docker Engine + Docker Compose v2 |
| Orquestador de workflows | N8N 2.0 (ya instalado sobre Docker) |
| Microservicio nuevo | ETL Bucket Service (Python/FastAPI) |

### 1.2 Componentes del Sistema

```
VM GCS
└── Docker Engine
    ├── Servicio: n8n
    │   ├── Puerto expuesto: 5678 (acceso externo)
    │   └── Red interna: etl-network
    │
    └── Servicio: bucket-etl-service
        ├── Puerto: 8000 (solo red interna — NO expuesto al exterior)
        └── Red interna: etl-network
```

**Principio clave (ADR-09):** El microservicio `bucket-etl-service` **nunca expone un puerto público**. Solo N8N puede alcanzarlo desde la red interna Docker. El exterior solo interactúa con N8N.

---

## 2. Topología de Red

```
Internet
    │
    │  HTTPS :443 / HTTP :5678
    ▼
┌─────────────────────────────────────────┐
│              VM GCS                     │
│                                         │
│  ┌──────────────────────────────────┐   │
│  │         etl-network (Docker)     │   │
│  │                                  │   │
│  │   ┌─────────┐    ┌────────────┐  │   │
│  │   │   n8n   │───►│ bucket-etl │  │   │
│  │   │  :5678  │    │  -service  │  │   │
│  │   │         │    │   :8000    │  │   │
│  │   └─────────┘    └────────────┘  │   │
│  │                                  │   │
│  └──────────────────────────────────┘   │
│                                         │
└─────────────────────────────────────────┘
```

### 2.1 Reglas de Comunicación

| Origen | Destino | Puerto | Permitido |
|---|---|---|---|
| Internet | `n8n` | `5678` | ✅ |
| Internet | `bucket-etl-service` | `8000` | ❌ nunca |
| `n8n` | `bucket-etl-service` | `8000` | ✅ red interna |
| `bucket-etl-service` | Google Drive API | `443` | ✅ salida |
| `bucket-etl-service` | Internet (general) | cualquiera | ⚠️ solo APIs de providers autorizados |

### 2.2 DNS Interno Docker

Dentro de la red `etl-network`, los servicios se referencian por nombre de servicio, no por IP:

```
# N8N llama al microservicio así:
http://bucket-etl-service:8000/api/v1/bucket/list

# No usar IPs — son dinámicas y cambian con cada recreación del contenedor
```

---

## 3. Docker Compose

### 3.1 Archivo `docker-compose.yml`

Este archivo extiende o reemplaza el `docker-compose.yml` existente de N8N. Si N8N ya tiene su propio archivo, el microservicio se agrega como un servicio adicional.

```yaml
version: "3.8"

services:

  # ── N8N (ya existente — no modificar su configuración actual) ──
  n8n:
    image: n8nio/n8n:2.0.0
    container_name: n8n
    restart: unless-stopped
    ports:
      - "5678:5678"         # Único servicio con puerto público
    environment:
      - N8N_HOST=${N8N_HOST}
      - N8N_PORT=5678
      - N8N_PROTOCOL=${N8N_PROTOCOL}
      - WEBHOOK_URL=${WEBHOOK_URL}
      - GENERIC_TIMEZONE=${TIMEZONE}
    volumes:
      - n8n_data:/home/node/.n8n
    networks:
      - etl-network
    depends_on:
      bucket-etl-service:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "wget", "--spider", "-q", "http://localhost:5678/healthz"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

  # ── ETL Bucket Service (nuevo) ──────────────────────────────────
  bucket-etl-service:
    build:
      context: ./bucket-etl-service   # Ruta al directorio del microservicio
      dockerfile: Dockerfile
    image: bucket-etl-service:1.0.0
    container_name: bucket-etl-service
    restart: unless-stopped
    # SIN ports: — este servicio no expone puertos al exterior
    env_file:
      - ./bucket-etl-service/.env     # Variables de entorno del microservicio
    networks:
      - etl-network
    healthcheck:
      test: ["CMD", "wget", "--spider", "-q", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 20s
    deploy:
      resources:
        limits:
          memory: 512M          # Ajustar según carga real
          cpus: "0.5"
        reservations:
          memory: 256M
          cpus: "0.25"

# ── Volúmenes ────────────────────────────────────────────────────
volumes:
  n8n_data:
    driver: local

# ── Red interna ──────────────────────────────────────────────────
networks:
  etl-network:
    driver: bridge
    name: etl-network
```

### 3.2 Notas sobre el Docker Compose

- **`bucket-etl-service` no tiene `ports:`** — es intencional. Solo accesible desde la red interna.
- **`depends_on` con `condition: service_healthy`** — N8N solo arranca cuando el microservicio está healthy. Previene que N8N intente llamar al microservicio antes de que esté listo.
- **`restart: unless-stopped`** — ambos servicios se reinician automáticamente tras un crash o reboot de la VM, excepto si se detienen manualmente.
- **`env_file`** — las variables sensibles nunca están en `docker-compose.yml`. Siempre en `.env` separado.
- **Límites de memoria** — los valores de `512M` y `0.5 CPUs` son un punto de partida. Ajustar tras observar el comportamiento real con archivos grandes.

---

## 4. Dockerfile del Microservicio

```dockerfile
# ── Stage 1: Builder ─────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /app

# Instalar dependencias del sistema necesarias para compilar paquetes Python
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copiar e instalar dependencias Python
# Se copia solo requirements.txt primero para aprovechar cache de Docker
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# ── Stage 2: Runtime ─────────────────────────────────────────────
FROM python:3.11-slim AS runtime

# Usuario no-root por seguridad
RUN groupadd -r appuser && useradd -r -g appuser appuser

WORKDIR /app

# Copiar dependencias instaladas desde el builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copiar código de la aplicación
COPY --chown=appuser:appuser app/ ./app/

# Cambiar al usuario no-root
USER appuser

# Puerto del microservicio
EXPOSE 8000

# Health check interno del contenedor
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD wget --spider -q http://localhost:8000/health || exit 1

# Comando de inicio
# --workers 1: un worker por contenedor en Fase 1
# --host y --port desde variables de entorno con fallback
CMD ["sh", "-c", "uvicorn app.main:app --host ${APP_HOST:-0.0.0.0} --port ${APP_PORT:-8000} --workers 1"]
```

### 4.1 Notas sobre el Dockerfile

- **Multi-stage build** — el stage `builder` compila dependencias. El stage `runtime` no tiene herramientas de compilación, reduciendo la superficie de ataque y el tamaño de imagen.
- **`python:3.11-slim`** — imagen base mínima. No usar `python:3.11` (incluye herramientas innecesarias).
- **Usuario no-root** — el proceso corre como `appuser`, no como `root`. Buena práctica de seguridad en contenedores.
- **`--workers 1`** — un solo worker Uvicorn en Fase 1. Si la carga aumenta, escalar con más workers o más contenedores, no modificando este archivo.

---

## 5. Variables de Entorno

### 5.1 Archivo `bucket-etl-service/.env.example`

Este archivo se sube al repositorio como documentación. El archivo `.env` real **nunca se sube** — está en `.gitignore`.

```dotenv
# ═══════════════════════════════════════════════════════════════
# ETL Bucket Service — Variables de Entorno
# Copiar este archivo como .env y completar los valores reales.
# NUNCA subir el archivo .env al repositorio.
# ═══════════════════════════════════════════════════════════════

# ── Servidor ────────────────────────────────────────────────────
# Host de binding del servidor Uvicorn.
# Siempre 0.0.0.0 dentro de Docker para aceptar conexiones de la red interna.
APP_HOST=0.0.0.0

# Puerto interno del microservicio.
# No cambiar salvo que haya conflicto con otro servicio en la red Docker.
APP_PORT=8000

# Entorno de ejecución.
# "development": activa /docs y /redoc de FastAPI.
# "production": desactiva /docs y /redoc.
APP_ENV=production

# Nivel de logging.
# Valores válidos: DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_LEVEL=INFO

# ── Seguridad ────────────────────────────────────────────────────
# Orígenes permitidos para CORS.
# En producción: URL exacta del frontend. Ejemplo: ["https://app.midominio.com"]
# En desarrollo: ["*"]
CORS_ALLOWED_ORIGINS=["*"]

# ── Límites Operacionales ────────────────────────────────────────
# Timeout en segundos para llamadas al provider externo (Google Drive API).
# Si una llamada supera este tiempo, se lanza ProviderConnectionError.
PROVIDER_REQUEST_TIMEOUT_SECONDS=30

# Número máximo de archivos que puede retornar un ListResponse.
# Previene respuestas que saturen memoria o red.
# Google Drive API tiene un límite de pageSize=1000 por página.
# Este límite es lógico sobre el total acumulado de todas las páginas.
MAX_FILES_PER_LIST=5000
```

### 5.2 Variables de N8N (referencia)

Estas variables ya existen en el entorno N8N. Se documentan aquí para referencia del equipo de DevOps al configurar el `docker-compose.yml`.

```dotenv
# ── N8N ─────────────────────────────────────────────────────────
N8N_HOST=0.0.0.0
N8N_PORT=5678
N8N_PROTOCOL=http           # http en VM interna, https si hay proxy inverso
WEBHOOK_URL=https://tu-dominio.com/  # URL pública de los webhooks
TIMEZONE=America/Bogota     # Ajustar a la zona horaria del equipo
```

### 5.3 Tabla Completa de Variables

| Variable | Servicio | Requerida | Default | Descripción |
|---|---|---|---|---|
| `APP_HOST` | microservicio | No | `0.0.0.0` | Host de binding Uvicorn |
| `APP_PORT` | microservicio | No | `8000` | Puerto interno |
| `APP_ENV` | microservicio | No | `production` | Entorno (`development` / `production`) |
| `LOG_LEVEL` | microservicio | No | `INFO` | Nivel de logging |
| `CORS_ALLOWED_ORIGINS` | microservicio | No | `["*"]` | Orígenes CORS permitidos |
| `PROVIDER_REQUEST_TIMEOUT_SECONDS` | microservicio | No | `30` | Timeout hacia provider externo |
| `MAX_FILES_PER_LIST` | microservicio | No | `5000` | Límite de archivos por respuesta |

> Nótese que el microservicio **no tiene variables de secretos propios** en Fase 1. No hay `GOOGLE_CLIENT_ID` ni `GOOGLE_CLIENT_SECRET` porque el microservicio no participa en el flujo OAuth (Token Forwarding Pattern, ADR-03).

---

## 6. Gestión de Secretos

### 6.1 Qué es un secreto en este sistema

En Fase 1, el único dato sensible que maneja el microservicio es el `access_token` del usuario, que llega en el body del request en tiempo de ejecución — no en variables de entorno.

El microservicio **no tiene secretos de configuración** en Fase 1. Todas sus variables de entorno son parámetros operacionales no sensibles.

### 6.2 Reglas de Gestión

| Regla | Descripción |
|---|---|
| `.env` nunca en git | Agregar `*.env` y `.env` al `.gitignore` del repositorio |
| `docker-compose.yml` sin valores secretos | Usar `env_file:` para referenciar el `.env`, nunca hardcodear valores en `environment:` |
| `access_token` nunca en logs | El microservicio nunca loggea el valor de `credentials.access_token` (ver DOC-02 regla 9.4) |
| Rotación | En Fase 2, si se agregan credenciales de sistema (S3 keys, etc.), documentar procedimiento de rotación aquí |

### 6.3 Futuro: Google Cloud Secret Manager

Cuando en Fase 2 se agreguen credenciales de sistema (por ejemplo, keys de S3 para un bucket destino propio), se recomienda migrar a **Google Cloud Secret Manager** en lugar de usar archivos `.env`. La VM GCS tiene acceso nativo a Secret Manager sin configuración adicional de red.

---

## 7. Health Checks

### 7.1 Health Check del Microservicio

El endpoint `GET /health` responde en menos de 1 segundo. Docker lo usa para determinar si el contenedor está listo para recibir tráfico.

```
GET http://localhost:8000/health
→ HTTP 200: { "status": "ok", "version": "1.0.0" }
```

**Configuración en Dockerfile:**
```dockerfile
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD wget --spider -q http://localhost:8000/health || exit 1
```

**Interpretación de estados Docker:**

| Estado | Significado |
|---|---|
| `starting` | Contenedor iniciando. Docker espera `start_period` (20s) antes de evaluar. |
| `healthy` | El health check pasó. N8N puede llamar al microservicio. |
| `unhealthy` | El health check falló `retries` veces consecutivas. Docker puede reiniciar el contenedor. |

### 7.2 Dependencia N8N → Microservicio

El `docker-compose.yml` define:

```yaml
n8n:
  depends_on:
    bucket-etl-service:
      condition: service_healthy
```

Esto garantiza que N8N no arranca hasta que el microservicio reporta `healthy`. Previene errores de conexión en el arranque inicial del stack.

---

## 8. Procedimientos Operacionales

### 8.1 Primer Despliegue

```bash
# 1. Clonar el repositorio en la VM
git clone <repo-url>
cd <repo-dir>

# 2. Crear el archivo .env del microservicio
cp bucket-etl-service/.env.example bucket-etl-service/.env
# Editar .env con los valores reales

# 3. Construir la imagen del microservicio
docker compose build bucket-etl-service

# 4. Levantar todo el stack
docker compose up -d

# 5. Verificar que ambos servicios están healthy
docker compose ps

# 6. Verificar logs iniciales
docker compose logs bucket-etl-service --tail=50
```

### 8.2 Actualización del Microservicio

```bash
# 1. Obtener cambios del repositorio
git pull

# 2. Reconstruir la imagen
docker compose build bucket-etl-service

# 3. Reiniciar solo el microservicio (sin afectar N8N)
docker compose up -d --no-deps bucket-etl-service

# 4. Verificar health
docker compose ps bucket-etl-service
```

### 8.3 Ver Logs

```bash
# Logs del microservicio en tiempo real
docker compose logs -f bucket-etl-service

# Últimas 100 líneas
docker compose logs bucket-etl-service --tail=100

# Logs de N8N
docker compose logs -f n8n

# Todos los servicios
docker compose logs -f
```

### 8.4 Detener y Reiniciar

```bash
# Detener todo el stack
docker compose down

# Detener y eliminar volúmenes (⚠️ elimina datos de N8N)
docker compose down -v

# Reiniciar solo el microservicio
docker compose restart bucket-etl-service

# Reiniciar todo
docker compose restart
```

### 8.5 Diagnóstico de Problemas

```bash
# Ver estado detallado de los contenedores
docker compose ps

# Inspeccionar el health check
docker inspect bucket-etl-service | grep -A 10 '"Health"'

# Entrar al contenedor para diagnóstico
docker compose exec bucket-etl-service sh

# Verificar conectividad interna desde N8N hacia el microservicio
docker compose exec n8n wget -qO- http://bucket-etl-service:8000/health

# Ver uso de recursos
docker stats bucket-etl-service n8n
```

---

## 9. Consideraciones de Seguridad de Infraestructura

### 9.1 Firewall de la VM GCS

La VM GCS debe tener configuradas reglas de firewall en GCP que permitan:

| Regla | Puerto | Fuente | Acción |
|---|---|---|---|
| Acceso a N8N | `5678` | IPs autorizadas o `0.0.0.0/0` | ✅ Permitir |
| SSH administración | `22` | IPs del equipo de DevOps | ✅ Permitir |
| Puerto microservicio | `8000` | `0.0.0.0/0` | ❌ Bloquear |
| Todo lo demás | cualquiera | `0.0.0.0/0` | ❌ Bloquear (default) |

> El puerto `8000` nunca debe aparecer en las reglas de firewall de GCP. Si alguien lo agrega por error, el microservicio quedaría expuesto directamente a internet sin autenticación.

### 9.2 Acceso a Google Drive API desde la VM

El microservicio realiza llamadas salientes a `https://www.googleapis.com` y `https://www.google.com`. La VM debe tener acceso de salida a internet habilitado (es el default en GCP Compute Engine).

No se requieren configuraciones adicionales de red para el acceso saliente.

### 9.3 TLS

En la arquitectura actual, la comunicación entre N8N y el microservicio ocurre en la red interna Docker — sin TLS. Esto es aceptable porque:
- La red `etl-network` no es accesible desde fuera de la VM.
- Ambos contenedores corren en el mismo host.

**Si en el futuro el microservicio se mueve a un host separado**, se debe agregar TLS para la comunicación entre N8N y el microservicio, o usar un proxy inverso (Nginx, Traefik) con certificado.

### 9.4 Imagen Docker

- Usar siempre `python:3.11-slim` como base — no `python:3.11-latest` ni `python:latest`.
- Fijar versiones exactas en `requirements.txt` — no usar rangos (`>=`) en producción.
- Escanear la imagen con `docker scout` o `trivy` antes de cada despliegue en producción.

---

## 10. Historial de Revisiones

| Versión | Fecha | Cambio |
|---|---|---|
| 1.0 | Marzo 2025 | Versión inicial — infraestructura Fase 1 en VM GCS con Docker Compose |
| 1.1 | Por definir | Agregar configuración de bucket destino (GCS Bucket o volumen) para Funcionalidad TRANSFER |
| 1.2 | Por definir | Evaluar migración a Cloud Run si la carga escala más allá de la VM actual |

---

*Documento generado por el equipo de Arquitectura de Sistemas.*  
*Para preguntas, referirse a DOC-01 — Architecture Decision Records.*
