# Prompt — Bloque 1: Esqueleto e Infraestructura

## Contexto del proyecto

Estás implementando el **ETL Bucket Service**, un microservicio Python/FastAPI que lista y transfiere archivos desde buckets externos (Google Drive, S3, Azure) para procesamiento ETL. La especificación completa está en la carpeta `context/` de este repositorio. Las instrucciones de trabajo están en `AGENTS.md`.

Este es el **Bloque 1 de 6**. Solo implementas lo que se indica aquí. No implementes lógica de providers, modelos Pydantic, ni servicios todavía — eso viene en bloques posteriores.

---

## Documentos que debes leer ANTES de escribir código

Lee estos documentos en orden. Son la fuente de verdad — el código debe ser fiel a ellos:

1. `context/DOC-02_Component_Specification.md` — Sección 2 (estructura de directorios), Sección 6 (config.py), Sección 7 (main.py), Sección 9.1 (excepciones), Sección 10 (dependencias)
2. `context/DOC-03_API_REST_Specification.md` — Sección 3 (formato de errores) y Sección 4.1 (GET /health)
3. `context/DOC-05_Infrastructure_Specification.md` — Sección 5 (variables de entorno) únicamente

---

## Qué implementar en este bloque

### 1. Estructura de directorios

Crear la estructura de carpetas y archivos vacíos exactamente como especifica DOC-02 Sección 2. Los archivos `__init__.py` deben estar presentes pero vacíos. Los archivos `.py` de lógica (providers, services, routers, models) deben crearse con solo un comentario indicando en qué bloque se implementan:

- models/ → `# TODO: Bloque 2 — Modelos y Contratos`
- providers/base.py, factory.py → `# TODO: Bloque 3 — Provider Interface + Factory`
- providers/google_drive/provider.py → `# TODO: Bloque 4 — GoogleDriveProvider`
- services/, routers/ → `# TODO: Bloque 5 — ListService + Router`

### 2. `app/exceptions.py`

Implementar la jerarquía completa de excepciones definida en DOC-02 Sección 9.1. Es el único módulo de lógica que se implementa completamente en este bloque — los demás bloques dependen de él desde el inicio.

### 3. `app/config.py`

Implementar `Settings` con `pydantic-settings` exactamente como especifica DOC-02 Sección 6. Incluir la instancia singleton `settings = Settings()` al final del archivo.

### 4. `app/main.py`

Implementar únicamente:

- Instancia de FastAPI con metadata correcta: title, version, description
- CORSMiddleware con settings.CORS_ALLOWED_ORIGINS
- Registro de todos los exception handlers definidos en DOC-02 Sección 7. Cada handler retorna un dict con la estructura ErrorResponse de DOC-03 Sección 3. Usar dicts por ahora — el modelo Pydantic se implementa en Bloque 2
- Endpoint GET /health que retorna {"status": "ok", "version": "1.0.0"}
- Documentación /docs y /redoc activas solo cuando settings.APP_ENV == "development"

No registrar routers todavía — el router de bucket se implementa en Bloque 5.

### 5. `requirements.txt`

Implementar con las dependencias exactas de DOC-02 Sección 10. Versiones fijas con ==.

### 6. `.env.example`

Implementar exactamente como especifica DOC-05 Sección 5.1 con todos los comentarios explicativos por variable.

---

## Criterio de aceptación

El bloque está completo cuando se cumple todo lo siguiente desde el entorno local con venv activo:

```bash
# 1. Instalar dependencias sin errores
pip install -r requirements.txt

# 2. Levantar el servidor en modo development
APP_ENV=development uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 3. Health check responde correctamente
curl http://localhost:8000/health
# Respuesta esperada exacta:
# {"status": "ok", "version": "1.0.0"}

# 4. Docs activas en development
curl -o /dev/null -s -w "%{http_code}" http://localhost:8000/docs
# Esperado: 200

# 5. Docs desactivadas en production
APP_ENV=production uvicorn app.main:app --host 0.0.0.0 --port 8000
curl -o /dev/null -s -w "%{http_code}" http://localhost:8000/docs
# Esperado: 404

# 6. Sin errores de importación al arrancar
# Los logs de uvicorn no deben mostrar ningún ImportError ni ModuleNotFoundError
```

---

## Restricciones

- No implementar lógica de providers, modelos Pydantic de request/response, servicios ni routers en este bloque.
- No agregar dependencias que no estén en DOC-02 Sección 10.
- Los archivos .py pendientes deben tener el comentario # TODO: Bloque N con el número correcto.
- settings debe ser un singleton importable desde cualquier módulo con: from app.config import settings
- Los exception handlers deben cubrir todas las excepciones de app/exceptions.py más el catch-all Exception → HTTP 500.

---

## Entrega esperada

Al finalizar este bloque, el repositorio debe tener exactamente esta estructura:

```
bucket-etl-service/
├── context/                           # Ya existente — no modificar
├── app/
│   ├── __init__.py                    # vacío
│   ├── main.py                        # health check + CORS + exception handlers
│   ├── config.py                      # Settings completo
│   ├── exceptions.py                  # Jerarquía completa de excepciones
│   ├── models/
│   │   ├── __init__.py                # vacío
│   │   ├── common.py                  # TODO: Bloque 2
│   │   ├── request.py                 # TODO: Bloque 2
│   │   └── response.py                # TODO: Bloque 2
│   ├── providers/
│   │   ├── __init__.py                # vacío
│   │   ├── base.py                    # TODO: Bloque 3
│   │   ├── factory.py                 # TODO: Bloque 3
│   │   └── google_drive/
│   │       ├── __init__.py            # vacío
│   │       └── provider.py            # TODO: Bloque 4
│   ├── services/
│   │   ├── __init__.py                # vacío
│   │   └── list_service.py            # TODO: Bloque 5
│   └── routers/
│       ├── __init__.py                # vacío
│       └── bucket.py                  # TODO: Bloque 5
├── tests/
│   ├── __init__.py                    # vacío
│   ├── conftest.py                    # vacío
│   ├── providers/
│   │   ├── __init__.py                # vacío
│   │   └── test_google_drive.py       # TODO: Bloque 4
│   └── services/
│       ├── __init__.py                # vacío
│       └── test_list_service.py       # TODO: Bloque 5
├── AGENTS.md
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```
