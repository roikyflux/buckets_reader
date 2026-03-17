# Prompt — Bloque 4: GoogleDriveProvider

## Contexto del proyecto

Estás implementando el **ETL Bucket Service**. La especificación completa está en `context/`. Las instrucciones de trabajo están en `AGENTS.md`.

Este es el **Bloque 4 de 6**. Los bloques anteriores están completos:
- Bloque 1: infraestructura, config, excepciones, main.py ✅
- Bloque 2: modelos Pydantic ✅
- Bloque 3: BucketProvider ABC, factory, GoogleDriveProvider (stub) ✅

En este bloque implementas la lógica completa de `GoogleDriveProvider` y sus tests unitarios. Es el bloque más denso del proyecto.

---

## Documentos que debes leer ANTES de escribir código

1. `context/DOC-02_Component_Specification.md` — Sección 4.3 completa. Leer cada docstring, constante y método privado con atención.
2. `context/ADR-10_Drive_Client_SDK_vs_httpx.md` — Completo. Explica el patrón run_in_executor que toda llamada al SDK debe usar.
3. `context/DOC-04_Data_Model.md` — Sección 4.1 (FileInfo). Las reglas de mapeo de campos son obligatorias.
4. `context/DOC-01_Architecture_Decision_Records.md` — ADR-03 (Token Forwarding Pattern).

---

## Qué implementar en este bloque

### `app/providers/google_drive/provider.py`

Reemplazar el stub actual con la implementación completa. Mantener la firma exacta del stub.

#### Constantes de módulo

```python
GOOGLE_DRIVE_FOLDER_MIME = "application/vnd.google-apps.folder"
DRIVE_FILE_FIELDS = "id,name,mimeType,size,modifiedTime,webViewLink,parents"
DRIVE_PAGE_SIZE = 1000
RETRY_MAX_ATTEMPTS = 3
RETRY_WAIT_SECONDS = 2.0
```

#### `__init__(self, credentials: GoogleDriveCredentials) -> None`
- Guardar `self._credentials = credentials`
- Inicializar `self._service = None`
- No realizar llamadas de red

#### `validate_credentials(self) -> None`
- Construir el cliente con `google.oauth2.credentials.Credentials(token=access_token)`
- Construir el servicio con `googleapiclient.discovery.build('drive', 'v3', credentials=...)`
- La construcción es síncrona — ejecutar con `_execute_async`
- Si hay error al construir: lanzar `ProviderConnectionError`
- NO llamar ningún endpoint externo para verificar el token (Token Forwarding Pattern, ADR-03)

#### `list_files(self, folder_id, extensions, max_depth, *, current_depth, current_path) -> list[FileInfo]`

Estrategia:
1. Si `max_depth is not None` y `current_depth >= max_depth`: retornar `[]`
2. Query Drive: `f"'{folder_id}' in parents and trashed = false"`
3. Llamar a `drive.files().list(...)` con `_execute_async` — manejar paginación con `nextPageToken`
4. Para cada ítem:
   - `mimeType == GOOGLE_DRIVE_FOLDER_MIME` → subcarpeta → recursar con `current_depth + 1`
   - Caso contrario → archivo → `_map_to_file_info()` → agregar si no es `None`
5. Capturar `HttpError` del SDK:
   - 401 → `InvalidCredentialsError`
   - 404 → `FolderNotFoundError`
   - 429 → `ProviderRateLimitError`
   - Otros → `ProviderConnectionError`
6. Loggear inicio (folder_id, extensions, current_depth) y fin (total archivos encontrados)

#### `get_file_metadata(self, file_id: str) -> FileInfo`
- Llamar a `drive.files().get(fileId=file_id, fields=DRIVE_FILE_FIELDS)` con `_execute_async`
- Mapear con `_map_to_file_info(item, folder_path="")`
- Si retorna `None`: lanzar `FolderNotFoundError`
- `HttpError` 404 → `FolderNotFoundError`

#### `_execute_async(self, callable_) -> Any`
```python
loop = asyncio.get_event_loop()
return await loop.run_in_executor(None, callable_)
```
Usar con `functools.partial` cuando el callable necesite argumentos.

#### `_map_to_file_info(self, drive_file: dict, folder_path: str) -> FileInfo | None`
- Extraer extensión del `name` (parte después del último `.`), minúsculas
- Si no tiene extensión o no está en `ASSET_TYPES_EXTENSIONS`: retornar `None`
- Inferir `asset_type` desde `ASSET_TYPES_EXTENSIONS`
- `modifiedTime` → `datetime` timezone-aware UTC
- `webViewLink` → `preview_url` (puede ser `None`)
- `size` → `int`. Si no existe en el dict: usar `0`
- `source`: `SourceType.GOOGLE_DRIVE.value`

---

## Tests a implementar en `tests/providers/test_google_drive.py`

Reemplazar el stub con tests completos. Usar los fixtures de `conftest.py`.

Fixtures adicionales necesarios (agregar en este archivo):

```python
@pytest.fixture
def provider(valid_google_drive_credentials):
    from app.providers.google_drive.provider import GoogleDriveProvider
    return GoogleDriveProvider(credentials=valid_google_drive_credentials)

@pytest.fixture
def provider_con_servicio(provider, mocker):
    provider._service = mocker.MagicMock()
    return provider
```

Clases de tests requeridas:

```
TestValidateCredentials
  - test_construye_servicio_correctamente
  - test_lanza_provider_connection_error_si_falla_build

TestListFiles
  - test_retorna_lista_vacia_si_no_hay_coincidencias
  - test_filtra_archivos_por_extension
  - test_recursion_en_subcarpetas
  - test_respeta_max_depth
  - test_maneja_paginacion_interna
  - test_lanza_invalid_credentials_error_en_401
  - test_lanza_folder_not_found_en_404
  - test_construye_folder_path_correctamente

TestMapToFileInfo
  - test_extrae_extension_en_minusculas
  - test_retorna_none_para_extension_desconocida
  - test_infiere_asset_type_desde_extension
  - test_size_bytes_es_cero_si_drive_no_reporta_size
  - test_modified_at_es_datetime_utc
  - test_retorna_none_si_archivo_sin_extension
```

Regla crítica: ningún test puede hacer llamadas reales a Google APIs. Todo el SDK debe estar mockeado con pytest-mock.

---

## Criterio de aceptación

```bash
# 1. Init sin llamadas de red
python -c "
from app.providers.google_drive.provider import GoogleDriveProvider
from app.models.request import GoogleDriveCredentials
p = GoogleDriveProvider(credentials=GoogleDriveCredentials(access_token='ya29.test_ok'))
assert p._service is None
print('Init: OK')
"

# 2. _map_to_file_info — extensión conocida
python -c "
from app.providers.google_drive.provider import GoogleDriveProvider
from app.models.request import GoogleDriveCredentials
p = GoogleDriveProvider(credentials=GoogleDriveCredentials(access_token='ya29.test_ok'))
result = p._map_to_file_info({
    'id': '123', 'name': 'ventas.csv', 'mimeType': 'text/csv',
    'size': '1024', 'modifiedTime': '2025-03-10T14:30:00.000Z',
    'webViewLink': 'https://drive.google.com/file/d/123/view'
}, folder_path='datos/2025')
assert result is not None
assert result.extension == 'csv'
assert result.asset_type.value == 'dataset'
assert result.size_bytes == 1024
assert result.folder_path == 'datos/2025'
assert result.modified_at.tzinfo is not None
print('_map_to_file_info conocida: OK')
"

# 3. _map_to_file_info — extensión desconocida retorna None
python -c "
from app.providers.google_drive.provider import GoogleDriveProvider
from app.models.request import GoogleDriveCredentials
p = GoogleDriveProvider(credentials=GoogleDriveCredentials(access_token='ya29.test_ok'))
result = p._map_to_file_info({
    'id': '123', 'name': 'archivo.psd',
    'mimeType': 'image/vnd.adobe.photoshop',
    'modifiedTime': '2025-03-10T14:30:00.000Z'
}, folder_path='')
assert result is None
print('_map_to_file_info desconocida: OK')
"

# 4. _map_to_file_info — sin extensión retorna None
python -c "
from app.providers.google_drive.provider import GoogleDriveProvider
from app.models.request import GoogleDriveCredentials
p = GoogleDriveProvider(credentials=GoogleDriveCredentials(access_token='ya29.test_ok'))
result = p._map_to_file_info({
    'id': '123', 'name': 'README', 'mimeType': 'text/plain',
    'modifiedTime': '2025-03-10T14:30:00.000Z'
}, folder_path='')
assert result is None
print('_map_to_file_info sin extension: OK')
"

# 5. Tests unitarios del provider
pytest tests/providers/test_google_drive.py -v

# 6. Todos los tests del proyecto
pytest tests/ -v

# 7. Servidor sigue levantando
APP_ENV=development uvicorn app.main:app --host 0.0.0.0 --port 8000 &
sleep 3
curl -s http://localhost:8000/health
kill %1 2>/dev/null
```

---

## Restricciones

- `_execute_async` debe usarse para TODA llamada al SDK sin excepción.
- `validate_credentials` no llama a ningún endpoint externo.
- `modified_at` siempre timezone-aware UTC — nunca datetime naive.
- `size` ausente en respuesta Drive → usar `0`.
- Capturar `googleapiclient.errors.HttpError` específicamente — no `Exception` genérico.
- Tests sin llamadas reales a Google APIs.

---

## Entrega esperada

```
app/providers/google_drive/provider.py   ✅ Implementación completa
tests/providers/test_google_drive.py     ✅ Mínimo 16 tests
```

El resto del repositorio no se toca.
