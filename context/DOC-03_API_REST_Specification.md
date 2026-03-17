# DOC-03 — Especificación de API REST

**Proyecto:** ETL Bucket Service  
**Versión:** 1.0  
**Estado:** APROBADO  
**Fecha:** Marzo 2025  
**Depende de:** DOC-01 — ADRs, DOC-02 — Especificación de Componentes  
**Siguiente documento:** DOC-04 — Modelo de Datos  

---

## Tabla de Contenidos

1. [Convenciones Generales](#1-convenciones-generales)
2. [Autenticación y Credenciales](#2-autenticación-y-credenciales)
3. [Formato de Errores](#3-formato-de-errores)
4. [Endpoints](#4-endpoints)
   - [GET /health](#41-get-health)
   - [POST /api/v1/bucket/list](#42-post-apiv1bucketlist)
5. [Códigos de Error del Dominio](#5-códigos-de-error-del-dominio)
6. [Contrato con N8N](#6-contrato-con-n8n)
7. [Consideraciones de Seguridad](#7-consideraciones-de-seguridad)
8. [Historial de Revisiones](#8-historial-de-revisiones)

---

## 1. Convenciones Generales

### 1.1 Base URL

```
http://<hostname>:8000
```

En el entorno Docker Compose de la VM GCS, N8N referencia al microservicio por nombre de servicio interno:

```
http://bucket-etl-service:8000
```

El microservicio **no expone puerto público**. Solo N8N puede alcanzarlo desde la red interna Docker (ADR-09).

---

### 1.2 Formato de Request y Response

| Aspecto | Valor |
|---|---|
| Content-Type requerido | `application/json` |
| Content-Type de respuesta | `application/json` |
| Encoding | UTF-8 |
| Formato de fechas | ISO 8601 con timezone UTC — `2025-03-10T14:30:00Z` |
| Tamaños de archivo | Siempre en bytes (`int`) |
| Extensiones | Siempre en minúsculas, sin punto — `"csv"`, `"pdf"` |

---

### 1.3 Versionado

Todos los endpoints de negocio usan el prefijo `/api/v1/`. El endpoint `/health` no está versionado.

Cambios **no breaking** (campos nuevos opcionales en response) se introducen en la versión actual.  
Cambios **breaking** (campos eliminados, tipos cambiados, semántica alterada) se introducen en `/api/v2/` manteniendo `/api/v1/` operativo por un mínimo de 30 días.

---

### 1.4 Códigos HTTP Utilizados

| Código | Significado en este sistema |
|---|---|
| `200 OK` | Operación exitosa |
| `400 Bad Request` | Request malformado o provider no soportado |
| `401 Unauthorized` | Token inválido o expirado según el provider externo |
| `404 Not Found` | Carpeta o recurso no encontrado en el provider |
| `422 Unprocessable Entity` | Error de validación Pydantic (campos faltantes o tipos inválidos) |
| `429 Too Many Requests` | Rate limit del provider externo alcanzado |
| `500 Internal Server Error` | Error inesperado en el microservicio |
| `502 Bad Gateway` | Error de red o timeout al conectar con el provider externo |

---

## 2. Autenticación y Credenciales

### 2.1 Modelo de Autenticación (Token Forwarding Pattern)

El microservicio **no gestiona autenticación propia**. No hay API keys, JWTs propios ni sesiones.

El flujo completo es:

```
Frontend
   │
   │  1. Ejecuta flujo OAuth2 con Google
   ▼
Google OAuth
   │
   │  2. Emite access_token (vigencia: ~1 hora)
   ▼
Frontend
   │
   │  3. Incluye access_token en el body del request al microservicio
   ▼
Microservicio
   │
   │  4. Usa el token como Bearer en cada llamada a Drive API
   ▼
Google Drive API
```

### 2.2 Responsabilidades por Capa

| Responsabilidad | Capa |
|---|---|
| Ejecutar flujo OAuth2 con Google | **Frontend** |
| Almacenar access_token y refresh_token | **Frontend** |
| Refrescar el token antes de que expire | **Frontend** |
| Garantizar que el token enviado está vigente | **Frontend** |
| Usar el token como Bearer hacia Drive API | **Microservicio** |
| Verificar o refrescar tokens | ~~Microservicio~~ — **nunca** |

### 2.3 Transmisión del Token

El `access_token` se transmite en el **body del request** (campo `credentials.access_token`), no en headers HTTP. Esto permite que N8N lo gestione como parte del payload JSON sin configuración adicional de headers por provider.

> ⚠️ **Implicación para el equipo de frontend:** el token no debe estar expirado en el momento del envío. Si Drive API retorna 401, el microservicio propaga `HTTP 401` con código `INVALID_TOKEN`. El frontend debe capturar este código, refrescar el token y reintentar el request.

---

## 3. Formato de Errores

Todos los errores del sistema, sin excepción, retornan el siguiente schema:

```json
{
  "error": {
    "code": "STRING_CODIGO_ERROR",
    "message": "Descripción legible del error.",
    "field": "nombre_campo_si_aplica"
  }
}
```

| Campo | Tipo | Descripción |
|---|---|---|
| `error.code` | `string` | Código de error interno. Ver sección 5 para la lista completa. |
| `error.message` | `string` | Descripción en español legible por un desarrollador. |
| `error.field` | `string \| null` | Campo del request que causó el error. `null` si el error no es de validación de campo. |

### Ejemplo de error de validación (HTTP 422)

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "El campo asset_types no puede estar vacío.",
    "field": "asset_types"
  }
}
```

### Ejemplo de error de token (HTTP 401)

```json
{
  "error": {
    "code": "INVALID_TOKEN",
    "message": "El access_token fue rechazado por Google Drive. Puede estar expirado o ser inválido.",
    "field": null
  }
}
```

---

## 4. Endpoints

---

### 4.1 GET /health

**Propósito:** Verificar que el microservicio está operativo. Usado por Docker para health checks y por N8N para validar conectividad antes de ejecutar un workflow.

**Autenticación:** Ninguna.

**Request:**

```
GET /health HTTP/1.1
```

Sin body, sin parámetros.

---

**Response exitoso — HTTP 200**

```json
{
  "status": "ok",
  "version": "1.0.0"
}
```

| Campo | Tipo | Descripción |
|---|---|---|
| `status` | `string` | Siempre `"ok"` cuando el servicio responde. |
| `version` | `string` | Versión del microservicio desplegado. |

**Response de error:** Si el servicio no responde, Docker o N8N reciben timeout o connection refused. No hay body de error definido para este endpoint.

---

### 4.2 POST /api/v1/bucket/list

**Propósito:** Listar todos los archivos disponibles en una carpeta del bucket origen (y sus subcarpetas de forma recursiva), filtrados por las categorías de activos seleccionadas por el usuario. No mueve ni copia ningún archivo.

**Autenticación:** Token OAuth2 del provider incluido en el body (ver sección 2).

---

#### Request

```
POST /api/v1/bucket/list HTTP/1.1
Content-Type: application/json
```

**Body:**

```json
{
  "source": "google_drive",
  "credentials": {
    "access_token": "ya29.a0AfB_byC..."
  },
  "folder_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs",
  "asset_types": ["dataset", "documents"],
  "max_depth": null
}
```

**Descripción de campos del request:**

| Campo | Tipo | Requerido | Descripción |
|---|---|---|---|
| `source` | `string (enum)` | ✅ | Identificador del provider. Valores válidos: `"google_drive"`. Extensible en fases futuras. |
| `credentials` | `object` | ✅ | Credenciales para el provider indicado en `source`. La estructura varía por provider (ver 4.2.1). |
| `credentials.access_token` | `string` | ✅ | Access token OAuth2 emitido por Google. Longitud mínima: 10 caracteres. |
| `folder_id` | `string` | ✅ | ID de la carpeta raíz a explorar. Para Google Drive: el ID que aparece en la URL de la carpeta. |
| `asset_types` | `array[string]` | ✅ | Categorías de activos a listar. Mínimo 1 elemento. Valores válidos: `"audio"`, `"video"`, `"dataset"`, `"documents"`, `"images"`. |
| `max_depth` | `integer \| null` | ❌ | Profundidad máxima de recursión en subcarpetas. `null` = sin límite. Rango válido: 1–20. |

**Expansión de `asset_types` a extensiones:**

El microservicio expande internamente cada categoría a sus extensiones. El frontend no necesita conocer las extensiones — solo selecciona categorías.

| `asset_type` | Extensiones buscadas |
|---|---|
| `"audio"` | `mp3`, `wav`, `flac` |
| `"video"` | `mp4`, `avi`, `mov` |
| `"dataset"` | `csv`, `xlsx`, `parquet` |
| `"documents"` | `pdf`, `docx`, `txt` |
| `"images"` | `png`, `jpeg`, `jpg`, `tiff` |

---

#### 4.2.1 Estructura de `credentials` por provider

La estructura del objeto `credentials` varía según el valor de `source`. Esta es la tabla de referencia para fases actuales y futuras:

| `source` | Campos de `credentials` | Descripción |
|---|---|---|
| `"google_drive"` | `access_token: string` | Token OAuth2 emitido por Google |
| `"aws_s3"` *(Fase 2)* | `access_key_id`, `secret_access_key`, `region` | Credenciales IAM del bucket S3 |
| `"azure_blob"` *(Fase 2)* | `connection_string` | Connection string del storage account |

> El microservicio valida que los campos de `credentials` coincidan con el `source` indicado. Si se envía un `source: "google_drive"` con campos de S3, retorna `HTTP 400` con código `INVALID_CREDENTIALS_SCHEMA`.

---

#### Response exitoso — HTTP 200

```json
{
  "source": "google_drive",
  "folder_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs",
  "total_files": 3,
  "asset_types_requested": ["dataset", "documents"],
  "extensions_searched": ["csv", "xlsx", "parquet", "pdf", "docx", "txt"],
  "files": [
    {
      "id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs",
      "name": "ventas_Q1_2025.csv",
      "extension": "csv",
      "asset_type": "dataset",
      "mime_type": "text/csv",
      "size_bytes": 204800,
      "modified_at": "2025-03-10T14:30:00Z",
      "preview_url": "https://drive.google.com/file/d/1BxiM.../view",
      "folder_path": "datos/2025/Q1",
      "source": "google_drive"
    },
    {
      "id": "2CyiNWt1YSB6oGNLwCeCaAkhnVrqumlct",
      "name": "contrato_proveedor.pdf",
      "extension": "pdf",
      "asset_type": "documents",
      "mime_type": "application/pdf",
      "size_bytes": 1048576,
      "modified_at": "2025-02-28T09:15:00Z",
      "preview_url": "https://drive.google.com/file/d/2CyiN.../view",
      "folder_path": "legal",
      "source": "google_drive"
    },
    {
      "id": "3DzjOXu2ZTC7pHOMxDfDbBlioWsrvnmdu",
      "name": "reporte_anual.docx",
      "extension": "docx",
      "asset_type": "documents",
      "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      "size_bytes": 512000,
      "modified_at": "2025-01-15T18:45:00Z",
      "preview_url": "https://drive.google.com/file/d/3DzjO.../view",
      "folder_path": "",
      "source": "google_drive"
    }
  ]
}
```

**Descripción de campos del response:**

| Campo | Tipo | Descripción |
|---|---|---|
| `source` | `string` | Provider consultado. Espeja el valor del request. |
| `folder_id` | `string` | ID de la carpeta raíz consultada. Espeja el valor del request. |
| `total_files` | `integer` | Cantidad de archivos en el array `files`. |
| `asset_types_requested` | `array[string]` | Categorías solicitadas. Espeja el valor del request. |
| `extensions_searched` | `array[string]` | Extensiones efectivamente buscadas, expandidas desde `asset_types_requested`. |
| `files` | `array[FileInfo]` | Lista plana de archivos encontrados. Puede ser `[]` si no hay coincidencias. |

**Descripción de campos de cada `FileInfo`:**

| Campo | Tipo | Descripción |
|---|---|---|
| `id` | `string` | ID único del archivo en el provider. Se usa en `TransferRequest` para seleccionar archivos. |
| `name` | `string` | Nombre del archivo incluyendo extensión. |
| `extension` | `string` | Extensión en minúsculas sin punto. |
| `asset_type` | `string` | Categoría del activo inferida desde la extensión. |
| `mime_type` | `string` | MIME type reportado por el provider. |
| `size_bytes` | `integer` | Tamaño en bytes. `0` si el provider no lo informa. |
| `modified_at` | `string (ISO 8601)` | Última modificación en UTC. |
| `preview_url` | `string \| null` | URL de vista previa en el provider. `null` si no está disponible. |
| `folder_path` | `string` | Ruta relativa desde la carpeta raíz. `""` si el archivo está en la raíz. |
| `source` | `string` | Provider de origen. Útil cuando el frontend agrega resultados de múltiples fuentes. |

---

#### Caso especial: lista vacía — HTTP 200

Si no se encuentran archivos que coincidan con los filtros, el microservicio retorna **HTTP 200** con `total_files: 0` y `files: []`. No es un error.

```json
{
  "source": "google_drive",
  "folder_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs",
  "total_files": 0,
  "asset_types_requested": ["audio"],
  "extensions_searched": ["mp3", "wav", "flac"],
  "files": []
}
```

---

#### Responses de error

**HTTP 400 — Provider no soportado**

Cuando `source` tiene un valor no registrado en la factory.

```json
{
  "error": {
    "code": "UNSUPPORTED_PROVIDER",
    "message": "El provider 'dropbox' no está soportado en esta versión.",
    "field": "source"
  }
}
```

---

**HTTP 400 — Schema de credenciales incorrecto**

Cuando los campos de `credentials` no corresponden al `source` indicado.

```json
{
  "error": {
    "code": "INVALID_CREDENTIALS_SCHEMA",
    "message": "Las credenciales enviadas no corresponden al provider 'google_drive'. Se esperaba el campo 'access_token'.",
    "field": "credentials"
  }
}
```

---

**HTTP 401 — Token inválido o expirado**

Cuando Google Drive API rechaza el token con 401.

```json
{
  "error": {
    "code": "INVALID_TOKEN",
    "message": "El access_token fue rechazado por Google Drive. Puede estar expirado o ser inválido. El frontend debe refrescar el token y reintentar.",
    "field": "credentials.access_token"
  }
}
```

---

**HTTP 404 — Carpeta no encontrada**

Cuando `folder_id` no existe o el token no tiene permisos de lectura sobre ella.

```json
{
  "error": {
    "code": "FOLDER_NOT_FOUND",
    "message": "La carpeta con ID '1BxiMVs0XRA5...' no fue encontrada o no es accesible con las credenciales proporcionadas.",
    "field": "folder_id"
  }
}
```

---

**HTTP 422 — Error de validación Pydantic**

Cuando falta un campo requerido o tiene un tipo incorrecto.

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "El campo 'asset_types' debe contener al menos un elemento.",
    "field": "asset_types"
  }
}
```

---

**HTTP 429 — Rate limit del provider**

Cuando Google Drive API rechaza por exceso de llamadas.

```json
{
  "error": {
    "code": "PROVIDER_RATE_LIMIT",
    "message": "Se alcanzó el límite de llamadas a Google Drive API. Reintentar en unos segundos.",
    "field": null
  }
}
```

---

**HTTP 502 — Error de conexión con el provider**

Cuando hay error de red o timeout al llamar a Google Drive API.

```json
{
  "error": {
    "code": "PROVIDER_CONNECTION_ERROR",
    "message": "No se pudo conectar con Google Drive. Verifique la conectividad de red del servicio.",
    "field": null
  }
}
```

---

**HTTP 500 — Error interno**

Para errores inesperados no clasificados.

```json
{
  "error": {
    "code": "INTERNAL_ERROR",
    "message": "Error interno del servidor. Contacte al equipo de desarrollo.",
    "field": null
  }
}
```

---

#### Diagrama de flujo del endpoint

```
POST /api/v1/bucket/list
         │
         ▼
  ┌─────────────────┐
  │ Validar body    │── falla ──► HTTP 422 VALIDATION_ERROR
  │ (Pydantic)      │
  └────────┬────────┘
           │ ok
           ▼
  ┌─────────────────┐
  │ get_provider()  │── source desconocido ──► HTTP 400 UNSUPPORTED_PROVIDER
  │ (factory)       │
  └────────┬────────┘
           │ ok
           ▼
  ┌──────────────────────┐
  │ validate_credentials │── error de red ──► HTTP 502 PROVIDER_CONNECTION_ERROR
  │ (init cliente Drive) │
  └────────┬─────────────┘
           │ ok
           ▼
  ┌─────────────────┐
  │  list_files()   │── token inválido (401) ──► HTTP 401 INVALID_TOKEN
  │  (recursivo)    │── carpeta no existe  ──► HTTP 404 FOLDER_NOT_FOUND
  │                 │── rate limit (429)   ──► HTTP 429 PROVIDER_RATE_LIMIT
  │                 │── error de red       ──► HTTP 502 PROVIDER_CONNECTION_ERROR
  └────────┬────────┘
           │ ok
           ▼
  ┌─────────────────┐
  │ Construir       │
  │ ListResponse    │
  └────────┬────────┘
           │
           ▼
     HTTP 200 OK
```

---

## 5. Códigos de Error del Dominio

Lista exhaustiva de todos los códigos de error que el microservicio puede retornar. El frontend y N8N deben manejar cada uno de estos códigos.

| Código | HTTP | Descripción | Acción recomendada para el frontend |
|---|---|---|---|
| `UNSUPPORTED_PROVIDER` | 400 | El valor de `source` no está registrado | Validar en frontend antes de enviar |
| `INVALID_CREDENTIALS_SCHEMA` | 400 | Campos de `credentials` no coinciden con `source` | Revisar estructura del request |
| `VALIDATION_ERROR` | 422 | Campo faltante o tipo incorrecto en el request | Mostrar el campo `error.field` al usuario |
| `INVALID_TOKEN` | 401 | Token rechazado por el provider externo | Refrescar token OAuth2 y reintentar |
| `FOLDER_NOT_FOUND` | 404 | Carpeta no encontrada o sin permisos de lectura | Informar al usuario, verificar permisos |
| `PROVIDER_RATE_LIMIT` | 429 | Rate limit del provider externo alcanzado | Esperar y reintentar con backoff |
| `PROVIDER_CONNECTION_ERROR` | 502 | Error de red con el provider externo | Reintentar, verificar conectividad |
| `INTERNAL_ERROR` | 500 | Error interno no clasificado | Reportar al equipo de desarrollo |

---

## 6. Contrato con N8N

Esta sección describe cómo N8N debe configurar sus nodos para consumir el microservicio correctamente.

### 6.1 Nodo HTTP Request — POST /api/v1/bucket/list

| Parámetro N8N | Valor |
|---|---|
| Method | `POST` |
| URL | `http://bucket-etl-service:8000/api/v1/bucket/list` |
| Authentication | None (las credenciales van en el body) |
| Content-Type | `application/json` |
| Body Type | `JSON` |
| Timeout | `60000` ms (60 segundos) |
| Response Format | `JSON` |

**Body que N8N construye desde los parámetros del webhook:**

```json
{
  "source": "{{ $json.source }}",
  "credentials": {
    "access_token": "{{ $json.access_token }}"
  },
  "folder_id": "{{ $json.folder_id }}",
  "asset_types": "{{ $json.asset_types }}",
  "max_depth": "{{ $json.max_depth ?? null }}"
}
```

### 6.2 Manejo de Errores en N8N

N8N debe configurar el nodo HTTP Request con **"Continue on Fail: true"** y agregar un nodo `IF` posterior que evalúe:

```
{{ $json.error !== undefined }}
```

- Si `true` → rama de error: retornar `error.code` y `error.message` al frontend via webhook response.
- Si `false` → rama exitosa: continuar el flujo con el array `files`.

### 6.3 Nodo de Health Check en N8N

Para verificar que el microservicio está activo antes de ejecutar operaciones:

| Parámetro N8N | Valor |
|---|---|
| Method | `GET` |
| URL | `http://bucket-etl-service:8000/health` |
| Timeout | `5000` ms |

Si el health check falla, N8N debe detener el workflow y notificar.

---

## 7. Consideraciones de Seguridad

### 7.1 Transmisión del access_token

El `access_token` viaja en el body del request entre N8N y el microservicio. Dado que ambos corren en la red interna Docker (no expuesta a internet), este canal es seguro para la arquitectura definida (ADR-09).

> ⚠️ Si en el futuro el microservicio se expone fuera de la red Docker, **se debe agregar TLS** para la comunicación entre N8N y el microservicio.

### 7.2 Logging del token

El microservicio **nunca debe loggear** el valor de `credentials.access_token`. Los logs deben registrar solo el `source` y el `folder_id`. Ver regla 9.4 de DOC-02.

### 7.3 CORS

En producción, `CORS_ALLOWED_ORIGINS` debe contener únicamente la URL exacta del frontend. El valor `"*"` solo es aceptable en entornos de desarrollo.

### 7.4 Límite de archivos

El campo `MAX_FILES_PER_LIST` (default: 5000) previene respuestas que saturen la memoria del microservicio o la red interna. Si se alcanza el límite, el microservicio retorna los primeros `MAX_FILES_PER_LIST` archivos encontrados e incluye el campo `truncated: true` en el response (campo reservado para implementación futura).

---

## 8. Historial de Revisiones

| Versión | Fecha | Cambio |
|---|---|---|
| 1.0 | Marzo 2025 | Versión inicial — endpoint LIST con Google Drive |
| 1.1 | Por definir | Agregar endpoint `POST /api/v1/bucket/transfer` |

---

*Documento generado por el equipo de Arquitectura de Sistemas.*  
*Para preguntas, referirse a DOC-01 — Architecture Decision Records y DOC-02 — Especificación de Componentes.*
