# DOC-06 — Flujo N8N

**Proyecto:** ETL Bucket Service  
**Versión:** 1.0  
**Estado:** APROBADO  
**Fecha:** Marzo 2025  
**Depende de:** DOC-03 — Especificación de API REST, DOC-05 — Infraestructura  
**Siguiente documento:** DOC-07 — Guía de Extensibilidad  

---

## Tabla de Contenidos

1. [Visión General](#1-visión-general)
2. [Convenciones de este Documento](#2-convenciones-de-este-documento)
3. [Workflow 1 — LIST: Listar Archivos del Bucket](#3-workflow-1--list-listar-archivos-del-bucket)
   - [Diagrama](#31-diagrama)
   - [Nodo a Nodo](#32-nodo-a-nodo)
   - [Datos en tránsito](#33-datos-en-tránsito)
4. [Manejo de Errores Global](#4-manejo-de-errores-global)
5. [Configuración del Entorno N8N](#5-configuración-del-entorno-n8n)
6. [Notas de Implementación para el Configurador N8N](#6-notas-de-implementación-para-el-configurador-n8n)
7. [Historial de Revisiones](#7-historial-de-revisiones)

---

## 1. Visión General

N8N actúa exclusivamente como **orquestador y capa de routing** entre el frontend y el microservicio. No contiene lógica de negocio — toda la inteligencia del sistema vive en el microservicio Python.

### Responsabilidades de N8N en este sistema

| N8N hace | N8N NO hace |
|---|---|
| Recibir el webhook del frontend | Filtrar o transformar archivos |
| Validar que los campos obligatorios están presentes | Llamar a Google Drive directamente |
| Construir el body del request al microservicio | Manejar el flujo OAuth2 |
| Llamar al microservicio via HTTP | Almacenar resultados |
| Retornar la respuesta al frontend | Tomar decisiones de negocio |
| Detectar y propagar errores del microservicio | Reintentar llamadas a Drive API |

### Workflows definidos en Fase 1

| ID | Nombre | Trigger | Propósito |
|---|---|---|---|
| WF-01 | `etl-bucket-list` | Webhook POST | Listar archivos del bucket según filtros del usuario |
| WF-02 | `etl-bucket-transfer` | Webhook POST | Transferir archivos seleccionados al destino *(Fase 1.1)* |

Este documento especifica **WF-01** completo. WF-02 se especifica cuando el bucket destino esté definido.

---

## 2. Convenciones de este Documento

### Notación de nodos

Cada nodo se describe con esta estructura:

```
NODO-XX — Nombre del Nodo
Tipo N8N:   tipo exacto del nodo en N8N
Propósito:  qué hace este nodo
```

### Notación de datos

- `{{ $json.campo }}` — acceso a datos del nodo anterior
- `{{ $node["Nombre Nodo"].json.campo }}` — acceso a datos de un nodo específico
- `{{ $json.campo ?? valor_default }}` — acceso con valor por defecto si el campo es null

### Nomenclatura de campos

Los campos que llegan del frontend via webhook se documentan en la sección 3.3. El configurador N8N debe asegurarse de que el frontend envíe exactamente esos nombres de campo.

---

## 3. Workflow 1 — LIST: Listar Archivos del Bucket

**Nombre en N8N:** `etl-bucket-list`  
**Trigger:** Webhook POST  
**Tiempo máximo esperado:** 60 segundos (carpetas grandes con muchas páginas)  
**Respuesta al frontend:** JSON con lista de archivos o error estructurado  

---

### 3.1 Diagrama

```
                    ┌─────────────────────────┐
                    │  NODO-01                │
                    │  Webhook Trigger        │
                    │  POST /webhook/list     │
                    └────────────┬────────────┘
                                 │
                                 ▼
                    ┌─────────────────────────┐
                    │  NODO-02                │
                    │  Validar campos         │◄── falla ──┐
                    │  obligatorios           │            │
                    └────────────┬────────────┘            │
                                 │ ok                      │
                                 ▼                         │
                    ┌─────────────────────────┐            │
                    │  NODO-03                │            │
                    │  Construir body         │            │
                    │  para microservicio     │            │
                    └────────────┬────────────┘            │
                                 │                         │
                                 ▼                         │
                    ┌─────────────────────────┐            │
                    │  NODO-04                │            │
                    │  HTTP Request           │            │
                    │  POST /api/v1/bucket/   │            │
                    │  list                   │            │
                    └────────────┬────────────┘            │
                                 │                         │
                    ┌────────────┴────────────┐            │
                    │                         │            │
               respuesta ok             respuesta          │
               (sin error.code)         (con error.code)   │
                    │                         │            │
                    ▼                         ▼            │
          ┌──────────────────┐    ┌───────────────────┐   │
          │  NODO-05a        │    │  NODO-05b         │   │
          │  Formatear       │    │  Formatear        │   │
          │  respuesta OK    │    │  respuesta Error  │◄──┘
          └────────┬─────────┘    └─────────┬─────────┘
                   │                        │
                   └──────────┬─────────────┘
                              │
                              ▼
                 ┌────────────────────────┐
                 │  NODO-06               │
                 │  Respond to Webhook    │
                 │  (respuesta al         │
                 │   frontend)            │
                 └────────────────────────┘
```

---

### 3.2 Nodo a Nodo

---

#### NODO-01 — Webhook Trigger

```
Tipo N8N:   Webhook
Propósito:  Punto de entrada del workflow. Recibe el request del frontend.
```

**Configuración:**

| Parámetro | Valor |
|---|---|
| HTTP Method | `POST` |
| Path | `list` |
| Authentication | None *(la autenticación con Drive va en el body)* |
| Response Mode | `Using Respond to Webhook Node` |
| Binary Data | No |

**URL resultante:**
```
https://<n8n-host>/webhook/list
```

**Body esperado del frontend:**

```json
{
  "source": "google_drive",
  "access_token": "ya29.a0AfB_byC...",
  "folder_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs",
  "asset_types": ["dataset", "documents"],
  "max_depth": null
}
```

> **Nota para el equipo de frontend:** el `access_token` se envía como campo de primer nivel en el body del webhook, no en headers. N8N lo empaqueta dentro del objeto `credentials` al llamar al microservicio.

**Output de este nodo:** el body completo del request queda disponible en `$json`.

---

#### NODO-02 — Validar Campos Obligatorios

```
Tipo N8N:   IF
Propósito:  Verificar que los campos mínimos necesarios están presentes
            antes de llamar al microservicio. Evita llamadas innecesarias
            con datos incompletos.
```

**Condición (todos deben cumplirse — operador AND):**

| Campo | Condición N8N | Descripción |
|---|---|---|
| `source` | `is not empty` | Provider de bucket |
| `access_token` | `is not empty` | Token OAuth2 del usuario |
| `folder_id` | `is not empty` | ID de carpeta a explorar |
| `asset_types` | `is not empty` | Al menos una categoría seleccionada |

**Rama TRUE (todos presentes):** continúa al NODO-03.  
**Rama FALSE (alguno faltante):** va directo a NODO-05b con error de validación.

**Expresión de condición compuesta:**
```javascript
{{ 
  $json.source !== undefined && $json.source !== "" &&
  $json.access_token !== undefined && $json.access_token !== "" &&
  $json.folder_id !== undefined && $json.folder_id !== "" &&
  $json.asset_types !== undefined && $json.asset_types.length > 0
}}
```

**Data que pasa a NODO-05b si falla:**
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Faltan campos obligatorios: source, access_token, folder_id o asset_types.",
    "field": null
  }
}
```

---

#### NODO-03 — Construir Body para Microservicio

```
Tipo N8N:   Set
Propósito:  Transformar los campos del webhook al formato exacto que
            espera el microservicio (DOC-03 — contrato de API).
```

**Configuración — campos a construir:**

| Campo de salida | Tipo | Valor |
|---|---|---|
| `body.source` | String | `{{ $json.source }}` |
| `body.credentials.access_token` | String | `{{ $json.access_token }}` |
| `body.folder_id` | String | `{{ $json.folder_id }}` |
| `body.asset_types` | Array | `{{ $json.asset_types }}` |
| `body.max_depth` | Number/null | `{{ $json.max_depth ?? null }}` |

**Output de este nodo:**
```json
{
  "body": {
    "source": "google_drive",
    "credentials": {
      "access_token": "ya29.a0AfB_byC..."
    },
    "folder_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs",
    "asset_types": ["dataset", "documents"],
    "max_depth": null
  }
}
```

---

#### NODO-04 — HTTP Request al Microservicio

```
Tipo N8N:   HTTP Request
Propósito:  Llamar al endpoint /api/v1/bucket/list del microservicio
            y obtener la lista de archivos.
```

**Configuración:**

| Parámetro | Valor |
|---|---|
| Method | `POST` |
| URL | `http://bucket-etl-service:8000/api/v1/bucket/list` |
| Authentication | None |
| Content-Type | `application/json` |
| Body | JSON — usar `{{ $json.body }}` del nodo anterior |
| Response Format | `JSON` |
| Timeout | `60000` ms (60 segundos) |
| **Continue on Fail** | `true` ← **crítico** |

> **Por qué `Continue on Fail: true`:** si el microservicio retorna HTTP 4xx o 5xx, N8N por default marca el workflow como fallido y no ejecuta nodos posteriores. Con esta opción activada, N8N continúa y el NODO-05b puede capturar el error y retornar una respuesta estructurada al frontend en lugar de silencio.

**Output exitoso de este nodo** (HTTP 200):
```json
{
  "source": "google_drive",
  "folder_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs",
  "total_files": 3,
  "asset_types_requested": ["dataset", "documents"],
  "extensions_searched": ["csv", "xlsx", "parquet", "pdf", "docx", "txt"],
  "files": [...]
}
```

**Output de error de este nodo** (HTTP 4xx/5xx):
```json
{
  "error": {
    "code": "INVALID_TOKEN",
    "message": "El access_token fue rechazado por Google Drive.",
    "field": "credentials.access_token"
  }
}
```

---

#### NODO-05a / NODO-05b — IF: Detectar Error en Respuesta

```
Tipo N8N:   IF
Propósito:  Evaluar si la respuesta del microservicio contiene un error
            para enrutar hacia el formateador correcto.
```

**Condición:**
```javascript
{{ $json.error !== undefined }}
```

- **TRUE** (hay error) → **NODO-05b**: formatear respuesta de error
- **FALSE** (sin error) → **NODO-05a**: formatear respuesta exitosa

---

#### NODO-05a — Formatear Respuesta Exitosa

```
Tipo N8N:   Set
Propósito:  Construir el objeto de respuesta final para el frontend
            en caso de éxito.
```

**Campos de salida:**

| Campo | Valor |
|---|---|
| `success` | `true` |
| `data` | `{{ $json }}` *(ListResponse completo del microservicio)* |

**Output:**
```json
{
  "success": true,
  "data": {
    "source": "google_drive",
    "folder_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs",
    "total_files": 3,
    "asset_types_requested": ["dataset", "documents"],
    "extensions_searched": ["csv", "xlsx", "parquet", "pdf", "docx", "txt"],
    "files": [...]
  }
}
```

---

#### NODO-05b — Formatear Respuesta de Error

```
Tipo N8N:   Set
Propósito:  Construir el objeto de respuesta final para el frontend
            en caso de error — tanto errores del microservicio como
            errores de validación detectados por N8N (NODO-02).
```

**Campos de salida:**

| Campo | Valor |
|---|---|
| `success` | `false` |
| `error` | `{{ $json.error }}` *(ErrorDetail del microservicio o error de validación N8N)* |

**Output:**
```json
{
  "success": false,
  "error": {
    "code": "INVALID_TOKEN",
    "message": "El access_token fue rechazado por Google Drive.",
    "field": "credentials.access_token"
  }
}
```

---

#### NODO-06 — Respond to Webhook

```
Tipo N8N:   Respond to Webhook
Propósito:  Retornar la respuesta final al frontend.
            Es el único punto de salida del workflow.
```

**Configuración:**

| Parámetro | Valor |
|---|---|
| Respond With | `JSON` |
| Response Body | `{{ $json }}` *(output del NODO-05a o NODO-05b)* |
| Response Code — éxito | `200` |
| Response Code — error | `200` *(ver nota abajo)* |

> **Por qué HTTP 200 en errores:** N8N Webhook retorna siempre el mismo HTTP status al frontend. Usar siempre 200 y dejar que el campo `success: false` + `error.code` comuniquen el estado real. Esto simplifica el manejo en el frontend — una sola condición `response.success` determina el flujo, sin manejar múltiples códigos HTTP desde N8N.
>
> El microservicio sí usa códigos HTTP semánticos internamente (401, 404, 422, etc.) — esto es para la comunicación N8N → frontend exclusivamente.

---

### 3.3 Datos en Tránsito

Esta sección documenta el esquema de datos en cada punto del workflow para facilitar el debugging.

```
Frontend → NODO-01 (Webhook)
────────────────────────────
{
  "source": string,            // "google_drive"
  "access_token": string,      // token OAuth2
  "folder_id": string,         // ID carpeta Drive
  "asset_types": string[],     // ["dataset", "documents"]
  "max_depth": number | null   // opcional
}

NODO-01 → NODO-02 (Validación)
────────────────────────────────
Mismo objeto — $json contiene el body del webhook

NODO-02 (ok) → NODO-03 (Construir body)
──────────────────────────────────────────
Mismo objeto — $json contiene el body del webhook

NODO-03 → NODO-04 (HTTP Request)
──────────────────────────────────
{
  "body": {
    "source": string,
    "credentials": { "access_token": string },
    "folder_id": string,
    "asset_types": string[],
    "max_depth": number | null
  }
}

NODO-04 → NODO-05a/05b (IF)
──────────────────────────────
// Caso éxito (HTTP 200 del microservicio):
{
  "source": string,
  "folder_id": string,
  "total_files": number,
  "asset_types_requested": string[],
  "extensions_searched": string[],
  "files": FileInfo[]
}

// Caso error (HTTP 4xx/5xx del microservicio):
{
  "error": {
    "code": string,
    "message": string,
    "field": string | null
  }
}

NODO-05a → NODO-06 (Respond)
──────────────────────────────
{
  "success": true,
  "data": { ...ListResponse }
}

NODO-05b → NODO-06 (Respond)
──────────────────────────────
{
  "success": false,
  "error": { "code": string, "message": string, "field": string | null }
}

NODO-06 → Frontend
────────────────────
// Siempre HTTP 200 desde N8N
// El campo "success" indica el resultado real
{
  "success": true | false,
  "data": { ...ListResponse }   // solo si success: true
  "error": { ...ErrorDetail }   // solo si success: false
}
```

---

## 4. Manejo de Errores Global

### 4.1 Tabla de Escenarios de Error

| Escenario | Dónde se detecta | Código retornado al frontend |
|---|---|---|
| Campo obligatorio faltante en webhook | NODO-02 | `VALIDATION_ERROR` |
| Provider no soportado | Microservicio → NODO-05b | `UNSUPPORTED_PROVIDER` |
| Token OAuth2 inválido o expirado | Microservicio → NODO-05b | `INVALID_TOKEN` |
| Carpeta no encontrada | Microservicio → NODO-05b | `FOLDER_NOT_FOUND` |
| Error de validación Pydantic | Microservicio → NODO-05b | `VALIDATION_ERROR` |
| Rate limit de Google Drive | Microservicio → NODO-05b | `PROVIDER_RATE_LIMIT` |
| Error de red con Google Drive | Microservicio → NODO-05b | `PROVIDER_CONNECTION_ERROR` |
| Microservicio no disponible (timeout N8N) | NODO-04 timeout | `PROVIDER_CONNECTION_ERROR` |
| Error interno del microservicio | Microservicio → NODO-05b | `INTERNAL_ERROR` |

### 4.2 Timeout del NODO-04

Si el microservicio no responde en 60 segundos, N8N genera su propio error de timeout. Con `Continue on Fail: true`, este error llega al NODO-05b como:

```json
{
  "error": {
    "message": "Request timed out"
  }
}
```

El NODO-05b debe manejar este caso construyendo una respuesta con código `PROVIDER_CONNECTION_ERROR`:

```javascript
// Expresión en NODO-05b para el campo error.code:
{{ $json.error?.code ?? "PROVIDER_CONNECTION_ERROR" }}

// Expresión para error.message:
{{ $json.error?.message ?? "El servicio no respondió en el tiempo esperado." }}
```

---

## 5. Configuración del Entorno N8N

### 5.1 Variables de Entorno N8N relevantes

Estas variables deben estar configuradas en el entorno N8N para que el workflow funcione correctamente.

| Variable | Valor recomendado | Descripción |
|---|---|---|
| `WEBHOOK_URL` | `https://<dominio-publico>/` | Base URL pública para los webhooks. N8N la usa para construir las URLs de webhook. |
| `GENERIC_TIMEZONE` | `America/Bogota` (o la del equipo) | Timezone para logs y scheduling. |
| `N8N_DEFAULT_BINARY_DATA_MODE` | `filesystem` | Evita problemas con payloads grandes en memoria. |

### 5.2 Credenciales N8N

El workflow **no requiere credenciales configuradas en N8N** para funcionar. No hay nodos de autenticación — las credenciales del usuario viajan en el body del webhook.

### 5.3 Importar el Workflow

El workflow se distribuye como archivo JSON exportado desde N8N. Para importarlo:

1. En N8N: `Workflows → Import from file`
2. Seleccionar el archivo `etl-bucket-list.workflow.json`
3. Verificar que la URL del NODO-04 apunta a `http://bucket-etl-service:8000` (nombre de servicio Docker correcto)
4. Activar el workflow con el toggle de `Active`

---

## 6. Notas de Implementación para el Configurador N8N

Estas notas son instrucciones directas para quien configure el workflow en la interfaz de N8N.

1. **`Continue on Fail` en NODO-04 es obligatorio.** Sin esta opción, cualquier error del microservicio deja al frontend sin respuesta. Verificar que está activado antes de hacer deploy.

2. **El nombre del servicio en la URL debe coincidir exactamente con el nombre en `docker-compose.yml`.** Si el servicio se llama `bucket-etl-service` en Docker Compose, la URL en NODO-04 es `http://bucket-etl-service:8000`. Un error tipográfico aquí es la causa más común de fallo de conectividad.

3. **El webhook path `list` es sensible a mayúsculas.** N8N distingue entre `/webhook/list` y `/webhook/List`. Documentar la URL exacta para el equipo de frontend.

4. **Response Mode del NODO-01 debe ser `Using Respond to Webhook Node`.** Si se deja en `Immediately`, N8N responde antes de que el workflow termine y el frontend no recibe los datos.

5. **Timeout de 60 segundos en NODO-04.** Carpetas de Drive con cientos de archivos en múltiples subcarpetas pueden tardar entre 15 y 45 segundos. Un timeout de 30 segundos causará falsos negativos. Usar 60 segundos mínimo.

6. **No agregar lógica de negocio en N8N.** Si se necesita transformar o filtrar los archivos retornados, ese código pertenece al microservicio, no a N8N. N8N solo debe enrutar y formatear responses.

7. **Activar logging de ejecuciones en N8N.** En `Settings → Log Level: Info` para tener trazabilidad de cada ejecución del workflow en producción.

---

## 7. Historial de Revisiones

| Versión | Fecha | Cambio |
|---|---|---|
| 1.0 | Marzo 2025 | Versión inicial — WF-01 LIST completo |
| 1.1 | Por definir | Agregar WF-02 TRANSFER cuando se defina el bucket destino |

---

*Documento generado por el equipo de Arquitectura de Sistemas.*  
*Para preguntas, referirse a DOC-03 — Especificación de API REST y DOC-05 — Infraestructura.*
