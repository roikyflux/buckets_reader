# DOC-04 — Modelo de Datos

**Proyecto:** ETL Bucket Service  
**Versión:** 1.0  
**Estado:** APROBADO  
**Fecha:** Marzo 2025  
**Depende de:** DOC-02 — Especificación de Componentes, DOC-03 — Especificación de API REST  
**Siguiente documento:** DOC-05 — Especificación de Infraestructura  

---

## Tabla de Contenidos

1. [Visión General](#1-visión-general)
2. [Tipos Enumerados](#2-tipos-enumerados)
3. [Modelos de Request](#3-modelos-de-request)
4. [Modelos de Response](#4-modelos-de-response)
5. [Modelo de Errores](#5-modelo-de-errores)
6. [Mapa de Relaciones entre Modelos](#6-mapa-de-relaciones-entre-modelos)
7. [Reglas de Validación](#7-reglas-de-validación)
8. [Ejemplos Completos](#8-ejemplos-completos)
9. [Historial de Revisiones](#9-historial-de-revisiones)

---

## 1. Visión General

Este documento define todos los modelos de datos que fluyen a través del sistema: desde el request que llega del frontend (vía N8N), hasta el response que retorna con la lista de archivos.

### 1.1 Principios del Modelo de Datos

- **Un solo schema por concepto.** No hay modelos duplicados para entrada y salida del mismo concepto. `FileInfo` es el mismo objeto en el response de cualquier endpoint que retorne archivos.
- **Sin tipos implícitos.** Todo campo tiene tipo explícito, descripción y ejemplo. No hay campos `data: object` sin definir.
- **Extensible por diseño.** Los tipos enumerados (`SourceType`, `AssetType`) son el único punto de cambio al agregar nuevos providers o categorías de activos.
- **Pydantic v2 es la fuente de verdad.** Los schemas de esta documentación se corresponden 1:1 con los modelos Pydantic definidos en `app/models/`. Si hay discrepancia, el código Pydantic prevalece y este documento debe actualizarse.

### 1.2 Flujo de Datos

```
Frontend / N8N
      │
      │  ListRequest (JSON)
      ▼
Microservicio
      │
      │  Expande asset_types → extensions[]
      │  Instancia provider
      │  Llama a Drive API
      │  Construye FileInfo[] 
      │
      │  ListResponse (JSON)
      ▼
Frontend / N8N
```

---

## 2. Tipos Enumerados

### 2.1 `SourceType`

Identifica el provider de bucket origen. Es el discriminador que la factory usa para instanciar el provider correcto.

| Valor | Provider | Estado |
|---|---|---|
| `"google_drive"` | Google Drive | ✅ Fase 1 |
| `"aws_s3"` | Amazon S3 | 🔲 Fase 2 |
| `"azure_blob"` | Azure Blob Storage | 🔲 Fase 2 |
| `"dropbox"` | Dropbox | 🔲 Fase 2 |

**Regla:** Enviar un valor no listado en esta tabla retorna `HTTP 400 UNSUPPORTED_PROVIDER`.

---

### 2.2 `AssetType`

Categoría de activo digital. Cada valor se expande a un conjunto fijo de extensiones de archivo.

| Valor | Extensiones cubiertas |
|---|---|
| `"audio"` | `mp3`, `wav`, `flac` |
| `"video"` | `mp4`, `avi`, `mov` |
| `"dataset"` | `csv`, `xlsx`, `parquet` |
| `"documents"` | `pdf`, `docx`, `txt` |
| `"images"` | `png`, `jpeg`, `jpg`, `tiff` |

**Regla:** El frontend envía categorías (`asset_types`), nunca extensiones individuales. La expansión es responsabilidad exclusiva del microservicio. Esto permite agregar nuevas extensiones a una categoría sin cambiar el contrato de API.

---

## 3. Modelos de Request

### 3.1 `GoogleDriveCredentials`

Credenciales para el provider `"google_drive"`. Estructura del objeto `credentials` cuando `source == "google_drive"`.

| Campo | Tipo | Requerido | Validaciones | Descripción |
|---|---|---|---|---|
| `access_token` | `string` | ✅ | `min_length: 10` | Access token OAuth2 emitido por Google tras el flujo de autorización en el frontend. Vigencia típica: 1 hora. |

**Notas:**
- No se incluye `refresh_token`. El frontend es el único responsable del ciclo de vida del token (ADR-03, Modelo 1).
- No se incluye `token_type`. Siempre es `"Bearer"` para Google OAuth2.
- El microservicio usa el token directamente como header `Authorization: Bearer <access_token>` en cada llamada a Drive API. No verifica el token antes de usarlo (Token Forwarding Pattern).

**JSON:**
```json
{
  "access_token": "ya29.a0AfB_byC..."
}
```

---

### 3.2 `ListRequest`

Body completo del endpoint `POST /api/v1/bucket/list`.

| Campo | Tipo | Requerido | Validaciones | Descripción |
|---|---|---|---|---|
| `source` | `SourceType` | ✅ | Valor válido en `SourceType` | Provider de bucket a consultar. |
| `credentials` | `GoogleDriveCredentials` | ✅ | Estructura válida para el `source` indicado | Credenciales de autenticación. La estructura varía por provider. |
| `folder_id` | `string` | ✅ | `min_length: 1` | ID de la carpeta raíz a explorar en el provider. |
| `asset_types` | `array[AssetType]` | ✅ | `min_length: 1`, sin duplicados | Categorías de activos a listar. El microservicio expande cada categoría a sus extensiones. |
| `max_depth` | `integer \| null` | ❌ | `ge: 1`, `le: 20` | Profundidad máxima de recursión en subcarpetas. `null` = sin límite. Default: `null`. |

**Notas:**
- `asset_types` con duplicados: el microservicio los elimina silenciosamente antes de procesar.
- `folder_id` para Google Drive: es el identificador que aparece en la URL de la carpeta — `https://drive.google.com/drive/folders/{folder_id}`.
- `max_depth: 1` significa solo la carpeta raíz, sin explorar subcarpetas.

**JSON:**
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

---

### 3.3 Tabla de `credentials` por `SourceType`

La estructura del objeto `credentials` es específica por provider. Esta tabla es la referencia para la implementación de providers futuros.

| `source` | Modelo de `credentials` | Campos requeridos |
|---|---|---|
| `"google_drive"` | `GoogleDriveCredentials` | `access_token` |
| `"aws_s3"` *(Fase 2)* | `S3Credentials` (por definir) | `access_key_id`, `secret_access_key`, `region` |
| `"azure_blob"` *(Fase 2)* | `AzureCredentials` (por definir) | `connection_string` |
| `"dropbox"` *(Fase 2)* | `DropboxCredentials` (por definir) | `access_token` |

**Regla de validación:** Si los campos de `credentials` no corresponden al `source` indicado, retornar `HTTP 400 INVALID_CREDENTIALS_SCHEMA`.

---

## 4. Modelos de Response

### 4.1 `FileInfo`

Representa un archivo individual encontrado en el bucket origen. Es el objeto atómico del sistema — aparece en el array `files` del `ListResponse` y será el input del `TransferRequest` en Fase 1.1.

| Campo | Tipo | Nullable | Descripción |
|---|---|---|---|
| `id` | `string` | No | ID único del archivo en el provider de origen. Para Google Drive: el fileId de la Drive API. Se usa en `TransferRequest` para identificar qué archivos transferir. |
| `name` | `string` | No | Nombre completo del archivo incluyendo extensión. Ejemplo: `"ventas_Q1_2025.csv"`. |
| `extension` | `string` | No | Extensión del archivo en minúsculas sin punto. Extraída del campo `name`. Ejemplo: `"csv"`. |
| `asset_type` | `AssetType` | No | Categoría del activo inferida desde la extensión usando `ASSET_TYPES_EXTENSIONS`. |
| `mime_type` | `string` | No | MIME type reportado por el provider. Para Google Drive: campo `mimeType` de la API. |
| `size_bytes` | `integer` | No | Tamaño del archivo en bytes. `0` si el provider no reporta tamaño (e.g. Google Docs nativos). |
| `modified_at` | `datetime` | No | Fecha y hora de la última modificación. Siempre en UTC, formato ISO 8601. Ejemplo: `"2025-03-10T14:30:00Z"`. |
| `preview_url` | `string` | Sí | URL de vista previa o acceso al archivo en el provider de origen. Para Google Drive: campo `webViewLink`. `null` si el provider no la provee. |
| `folder_path` | `string` | No | Ruta relativa de la carpeta contenedora desde la carpeta raíz solicitada. `""` (string vacío) si el archivo está directamente en la carpeta raíz. Separador: `/`. Ejemplo: `"datos/2025/Q1"`. |
| `source` | `string` | No | Identificador del provider de origen. Espeja el `source` del request. Útil cuando el frontend agrega resultados de múltiples fuentes en el futuro. |

**Notas sobre `folder_path`:**

```
Carpeta raíz solicitada: /Mi Drive/Proyecto
├── ventas.csv          → folder_path: ""
├── legal/
│   └── contrato.pdf    → folder_path: "legal"
└── datos/
    └── 2025/
        └── Q1/
            └── reporte.xlsx  → folder_path: "datos/2025/Q1"
```

**Notas sobre `size_bytes`:**
- Google Drive no reporta tamaño para archivos nativos (Google Docs, Sheets, Slides). En esos casos `size_bytes: 0`. Sin embargo, estos archivos tampoco tienen extensiones reconocidas por `ASSET_TYPES_EXTENSIONS`, por lo que no deberían aparecer en el resultado.
- Archivos binarios (csv, pdf, mp4, etc.) siempre tienen `size_bytes > 0`.

**JSON:**
```json
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
}
```

---

### 4.2 `ListResponse`

Response completo del endpoint `POST /api/v1/bucket/list`.

| Campo | Tipo | Nullable | Descripción |
|---|---|---|---|
| `source` | `string` | No | Provider consultado. Espeja `source` del request. |
| `folder_id` | `string` | No | ID de la carpeta raíz consultada. Espeja `folder_id` del request. |
| `total_files` | `integer` | No | Cantidad de archivos en el array `files`. Siempre `>= 0`. |
| `asset_types_requested` | `array[AssetType]` | No | Categorías solicitadas. Espeja `asset_types` del request (sin duplicados). |
| `extensions_searched` | `array[string]` | No | Extensiones efectivamente buscadas, resultado de expandir `asset_types_requested`. |
| `files` | `array[FileInfo]` | No | Lista plana de archivos encontrados. `[]` si no hay coincidencias — nunca `null`. |

**Notas:**
- `total_files` siempre es igual a `len(files)`. No es un conteo del total en el servidor — es el total retornado.
- `files: []` con `total_files: 0` es una respuesta válida y exitosa (`HTTP 200`). No indica error.
- El orden de los archivos en `files` no está garantizado. El frontend no debe asumir ningún orden específico.

**JSON:**
```json
{
  "source": "google_drive",
  "folder_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs",
  "total_files": 2,
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
    }
  ]
}
```

---

## 5. Modelo de Errores

### 5.1 `ErrorDetail`

Detalle estructurado de un error individual.

| Campo | Tipo | Nullable | Descripción |
|---|---|---|---|
| `code` | `string` | No | Código de error interno en `SCREAMING_SNAKE_CASE`. Ver tabla completa en DOC-03 sección 5. |
| `message` | `string` | No | Descripción en español legible por un desarrollador. No está pensado para mostrar al usuario final sin procesar. |
| `field` | `string \| null` | Sí | Nombre del campo del request que causó el error. `null` si el error no está asociado a un campo específico. |

---

### 5.2 `ErrorResponse`

Envelope de error. Todos los errores del sistema, sin excepción, usan este schema.

| Campo | Tipo | Nullable | Descripción |
|---|---|---|---|
| `error` | `ErrorDetail` | No | Detalle del error. |

**JSON:**
```json
{
  "error": {
    "code": "FOLDER_NOT_FOUND",
    "message": "La carpeta con ID '1BxiMVs0XRA5...' no fue encontrada o no es accesible con las credenciales proporcionadas.",
    "field": "folder_id"
  }
}
```

**Regla:** El campo `error` siempre está presente en respuestas de error. Nunca hay respuestas de error sin este envelope. Esto permite al frontend y a N8N detectar errores con una sola condición: `response.error !== undefined`.

---

### 5.3 `HealthResponse`

Response del endpoint `GET /health`.

| Campo | Tipo | Nullable | Descripción |
|---|---|---|---|
| `status` | `string` | No | Siempre `"ok"` cuando el servicio responde. |
| `version` | `string` | No | Versión semántica del microservicio desplegado. Ejemplo: `"1.0.0"`. |

**JSON:**
```json
{
  "status": "ok",
  "version": "1.0.0"
}
```

---

## 6. Mapa de Relaciones entre Modelos

```
ListRequest
├── source: SourceType ──────────────────────────────► factory.get_provider()
├── credentials: GoogleDriveCredentials
│   └── access_token: string ────────────────────────► Bearer token → Drive API
├── folder_id: string ───────────────────────────────► BucketProvider.list_files()
├── asset_types: AssetType[] ────────────────────────► get_extensions_for_asset_types()
│                                                           │
│                                                           ▼
│                                                      extensions: string[]
│                                                           │
│                                                           ▼
│                                                      BucketProvider.list_files()
│                                                           │
│                                                           ▼
│                                                      FileInfo[] ◄─────────────────┐
└── max_depth: int | null ────────────────────────────► recursión                   │
                                                                                    │
ListResponse ◄──────────────────────────────────────────────────────────────────────┘
├── source: string
├── folder_id: string
├── total_files: int
├── asset_types_requested: AssetType[]
├── extensions_searched: string[]
└── files: FileInfo[]
    └── id ──────────────────────────────────────────► TransferRequest.file_ids[] (Fase 1.1)
```

---

## 7. Reglas de Validación

Esta sección consolida todas las reglas de validación que Pydantic debe aplicar. Son la fuente de verdad para el agente de programación al implementar los modelos.

### 7.1 Reglas de `ListRequest`

| Campo | Regla | Error si falla |
|---|---|---|
| `source` | Debe ser un valor válido de `SourceType` | `HTTP 400 UNSUPPORTED_PROVIDER` |
| `credentials` | Debe tener la estructura correspondiente al `source` | `HTTP 400 INVALID_CREDENTIALS_SCHEMA` |
| `credentials.access_token` | `len >= 10` | `HTTP 422 VALIDATION_ERROR` |
| `folder_id` | `len >= 1` (no puede ser string vacío) | `HTTP 422 VALIDATION_ERROR` |
| `asset_types` | `len >= 1` (al menos una categoría) | `HTTP 422 VALIDATION_ERROR` |
| `asset_types` | Cada elemento debe ser un valor válido de `AssetType` | `HTTP 422 VALIDATION_ERROR` |
| `asset_types` | Duplicados se eliminan silenciosamente, no es error | — |
| `max_depth` | Si se provee: `1 <= max_depth <= 20` | `HTTP 422 VALIDATION_ERROR` |
| `max_depth` | Si se omite: default `null` | — |

### 7.2 Reglas de `FileInfo`

| Campo | Regla |
|---|---|
| `extension` | Siempre minúsculas, sin punto. Extraída del campo `name` (parte después del último `.`). |
| `asset_type` | Inferida desde `extension` usando `ASSET_TYPES_EXTENSIONS`. Si la extensión no está en el mapa, el archivo no debe incluirse en el resultado. |
| `size_bytes` | Siempre `>= 0`. Si el provider retorna `null` o string vacío, usar `0`. |
| `modified_at` | Siempre con timezone UTC. Si el provider retorna sin timezone, asumir UTC. |
| `folder_path` | Nunca `null`. Si el archivo está en la raíz, usar `""` (string vacío). |
| `preview_url` | `null` si el provider no provee URL de vista previa. Nunca string vacío. |

### 7.3 Reglas de `ListResponse`

| Campo | Regla |
|---|---|
| `total_files` | Siempre igual a `len(files)`. Calculado por el microservicio, no por el provider. |
| `files` | Nunca `null`. Lista vacía `[]` si no hay resultados. |
| `extensions_searched` | Resultado de expandir `asset_types_requested`. Sin duplicados. |

---

## 8. Ejemplos Completos

### 8.1 Request con todas las categorías y profundidad limitada

```json
{
  "source": "google_drive",
  "credentials": {
    "access_token": "ya29.a0AfB_byC_example_token"
  },
  "folder_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs",
  "asset_types": ["audio", "video", "dataset", "documents", "images"],
  "max_depth": 3
}
```

### 8.2 Response con archivos de múltiples categorías

```json
{
  "source": "google_drive",
  "folder_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs",
  "total_files": 5,
  "asset_types_requested": ["audio", "video", "dataset", "documents", "images"],
  "extensions_searched": ["mp3", "wav", "flac", "mp4", "avi", "mov", "csv", "xlsx", "parquet", "pdf", "docx", "txt", "png", "jpeg", "jpg", "tiff"],
  "files": [
    {
      "id": "1AAA",
      "name": "podcast_ep01.mp3",
      "extension": "mp3",
      "asset_type": "audio",
      "mime_type": "audio/mpeg",
      "size_bytes": 10485760,
      "modified_at": "2025-03-01T10:00:00Z",
      "preview_url": "https://drive.google.com/file/d/1AAA/view",
      "folder_path": "media/audio",
      "source": "google_drive"
    },
    {
      "id": "2BBB",
      "name": "demo_producto.mp4",
      "extension": "mp4",
      "asset_type": "video",
      "mime_type": "video/mp4",
      "size_bytes": 52428800,
      "modified_at": "2025-02-15T16:30:00Z",
      "preview_url": "https://drive.google.com/file/d/2BBB/view",
      "folder_path": "media/video",
      "source": "google_drive"
    },
    {
      "id": "3CCC",
      "name": "clientes.csv",
      "extension": "csv",
      "asset_type": "dataset",
      "mime_type": "text/csv",
      "size_bytes": 204800,
      "modified_at": "2025-03-10T14:30:00Z",
      "preview_url": "https://drive.google.com/file/d/3CCC/view",
      "folder_path": "",
      "source": "google_drive"
    },
    {
      "id": "4DDD",
      "name": "manual_usuario.pdf",
      "extension": "pdf",
      "asset_type": "documents",
      "mime_type": "application/pdf",
      "size_bytes": 2097152,
      "modified_at": "2025-01-20T09:00:00Z",
      "preview_url": "https://drive.google.com/file/d/4DDD/view",
      "folder_path": "docs",
      "source": "google_drive"
    },
    {
      "id": "5EEE",
      "name": "banner_principal.png",
      "extension": "png",
      "asset_type": "images",
      "mime_type": "image/png",
      "size_bytes": 1048576,
      "modified_at": "2025-03-05T12:00:00Z",
      "preview_url": "https://drive.google.com/file/d/5EEE/view",
      "folder_path": "assets/images",
      "source": "google_drive"
    }
  ]
}
```

### 8.3 Response vacío — sin archivos que coincidan

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

### 8.4 Error — token inválido

**HTTP 401**
```json
{
  "error": {
    "code": "INVALID_TOKEN",
    "message": "El access_token fue rechazado por Google Drive. Puede estar expirado o ser inválido. El frontend debe refrescar el token y reintentar.",
    "field": "credentials.access_token"
  }
}
```

### 8.5 Error — validación de campo faltante

**HTTP 422**
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "El campo 'folder_id' es requerido.",
    "field": "folder_id"
  }
}
```

---

## 9. Historial de Revisiones

| Versión | Fecha | Cambio |
|---|---|---|
| 1.0 | Marzo 2025 | Versión inicial — modelos para Funcionalidad LIST con Google Drive |
| 1.1 | Por definir | Agregar `TransferRequest` y modelos para Funcionalidad TRANSFER |
| 1.2 | Por definir | Agregar `S3Credentials`, `AzureCredentials` al agregar providers Fase 2 |

---

*Documento generado por el equipo de Arquitectura de Sistemas.*  
*Para preguntas, referirse a DOC-02 — Especificación de Componentes y DOC-03 — Especificación de API REST.*
