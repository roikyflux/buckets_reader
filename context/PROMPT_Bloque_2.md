# Prompt — Bloque 2: Modelos y Contratos

## Contexto del proyecto

Estás implementando el **ETL Bucket Service**. La especificación completa está en `context/`. Las instrucciones de trabajo están en `AGENTS.md`.

Este es el **Bloque 2 de 6**. El Bloque 1 está completo — la infraestructura, configuración y excepciones ya existen y funcionan. En este bloque implementas exclusivamente la capa de modelos Pydantic.

---

## Documentos que debes leer ANTES de escribir código

1. `context/DOC-04_Data_Model.md` — fuente de verdad completa para este bloque. Leer completo.
2. `context/DOC-02_Component_Specification.md` — Sección 3 (capa de modelos), para los detalles de implementación Pydantic.
3. `context/DOC-03_API_REST_Specification.md` — Sección 4.2.1 (tabla de credentials por provider) y Sección 5 (códigos de error).

---

## Qué implementar en este bloque

### 1. `app/models/common.py`

Implementar completo según DOC-02 Sección 3.1:

- Enum `SourceType` con valor `GOOGLE_DRIVE = "google_drive"`. Dejar comentados los valores de Fase 2 (S3, Azure, Dropbox).
- Enum `AssetType` con los cinco valores: `audio`, `video`, `dataset`, `documents`, `images`.
- Diccionario `ASSET_TYPES_EXTENSIONS` — fuente de verdad canónica de extensiones. Ver DOC-04 Sección 2.2 para los valores exactos.
- Función `get_extensions_for_asset_types(asset_types: list[AssetType]) -> list[str]` — retorna lista plana sin duplicados. Ver DOC-04 Sección 2.2 para el ejemplo de comportamiento esperado.

### 2. `app/models/request.py`

Implementar completo según DOC-02 Sección 3.2 y DOC-04 Sección 3:

- Clase `GoogleDriveCredentials` con campo `access_token: str` (min_length=10). Ver nota sobre Token Forwarding Pattern en DOC-04 Sección 3.1.
- Tipo unión `ProviderCredentials = GoogleDriveCredentials`. Dejar comentados los tipos de Fase 2.
- Clase `ListRequest` con todos sus campos, validaciones y field_validators. Ver tabla completa en DOC-04 Sección 3.2.

Validaciones obligatorias en `ListRequest`:
- `source`: debe ser valor válido de `SourceType`
- `credentials.access_token`: `min_length=10`
- `folder_id`: `min_length=1`
- `asset_types`: `min_length=1`, sin duplicados (eliminar silenciosamente, no es error)
- `max_depth`: si se provee, rango `1–20`

### 3. `app/models/response.py`

Implementar completo según DOC-02 Sección 3.3 y DOC-04 Sección 4:

- Clase `FileInfo` con todos sus campos. Ver tabla completa en DOC-04 Sección 4.1 con tipos y descripción de cada campo. Prestar atención especial a:
  - `size_bytes: int` — nunca null, usar `0` si el provider no reporta
  - `modified_at: datetime` — siempre timezone-aware UTC
  - `preview_url: str | None` — puede ser null, nunca string vacío
  - `folder_path: str` — nunca null, usar `""` si el archivo está en la raíz
- Clase `ListResponse` con todos sus campos. Ver DOC-04 Sección 4.2.
- Clase `ErrorDetail` con campos `code`, `message`, `field`.
- Clase `ErrorResponse` con campo `error: ErrorDetail`.
- Clase `HealthResponse` con campos `status` y `version`.

---

## Actualizar `app/main.py`

Una vez implementado `response.py`, actualizar los exception handlers en `main.py` para que retornen instancias de `ErrorResponse` en lugar de dicts crudos. El comportamiento externo no cambia — solo se tipan correctamente.

---

## Tests a implementar en `tests/conftest.py`

Implementar los fixtures compartidos que usarán los tests de los bloques 3, 4 y 5:

```python
# Fixtures mínimos requeridos:

@pytest.fixture
def valid_google_drive_credentials():
    """Credenciales válidas de prueba para GoogleDriveCredentials."""
    ...

@pytest.fixture
def valid_list_request():
    """ListRequest válido con source=google_drive y asset_types=['dataset']."""
    ...

@pytest.fixture
def sample_file_info():
    """FileInfo de ejemplo para usar en tests de respuesta."""
    ...
```

---

## Criterio de aceptación

El bloque está completo cuando se cumple todo lo siguiente con el venv activo:

```bash
# 1. Sin errores de importación
python -c "from app.models.common import SourceType, AssetType, ASSET_TYPES_EXTENSIONS, get_extensions_for_asset_types; print('OK')"

# 2. Expansión de asset_types correcta
python -c "
from app.models.common import AssetType, get_extensions_for_asset_types
result = get_extensions_for_asset_types([AssetType.AUDIO, AssetType.IMAGES])
assert set(result) == {'mp3', 'wav', 'flac', 'png', 'jpeg', 'jpg', 'tiff'}, f'Fallo: {result}'
assert len(result) == len(set(result)), 'Hay duplicados'
print('get_extensions_for_asset_types: OK')
"

# 3. Validación de ListRequest — caso válido
python -c "
from app.models.request import ListRequest, GoogleDriveCredentials
from app.models.common import SourceType, AssetType
req = ListRequest(
    source=SourceType.GOOGLE_DRIVE,
    credentials=GoogleDriveCredentials(access_token='ya29.test_token_ok'),
    folder_id='1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs',
    asset_types=[AssetType.DATASET, AssetType.DOCUMENTS],
    max_depth=None
)
print('ListRequest válido: OK')
"

# 4. Validación de ListRequest — duplicados en asset_types se eliminan
python -c "
from app.models.request import ListRequest, GoogleDriveCredentials
from app.models.common import SourceType, AssetType
req = ListRequest(
    source=SourceType.GOOGLE_DRIVE,
    credentials=GoogleDriveCredentials(access_token='ya29.test_token_ok'),
    folder_id='abc123',
    asset_types=[AssetType.DATASET, AssetType.DATASET, AssetType.AUDIO],
    max_depth=None
)
assert len(req.asset_types) == 2, f'Esperado 2, obtenido {len(req.asset_types)}'
print('Deduplicación asset_types: OK')
"

# 5. Validación de ListRequest — token muy corto lanza error
python -c "
from pydantic import ValidationError
from app.models.request import ListRequest, GoogleDriveCredentials
from app.models.common import SourceType, AssetType
try:
    ListRequest(
        source=SourceType.GOOGLE_DRIVE,
        credentials=GoogleDriveCredentials(access_token='short'),
        folder_id='abc',
        asset_types=[AssetType.DATASET]
    )
    print('ERROR: debió fallar')
except ValidationError:
    print('Validación token corto: OK')
"

# 6. FileInfo instancia correctamente
python -c "
from app.models.response import FileInfo
from app.models.common import AssetType
from datetime import datetime, timezone
f = FileInfo(
    id='abc123',
    name='datos.csv',
    extension='csv',
    asset_type=AssetType.DATASET,
    mime_type='text/csv',
    size_bytes=1024,
    modified_at=datetime.now(timezone.utc),
    preview_url=None,
    folder_path='',
    source='google_drive'
)
print('FileInfo: OK')
"

# 7. ErrorResponse instancia correctamente
python -c "
from app.models.response import ErrorResponse, ErrorDetail
e = ErrorResponse(error=ErrorDetail(code='INVALID_TOKEN', message='Token inválido', field=None))
print('ErrorResponse: OK')
"

# 8. El servidor sigue levantando sin errores después de los cambios
APP_ENV=development uvicorn app.main:app --host 0.0.0.0 --port 8000 &
sleep 3
curl -s http://localhost:8000/health
kill %1 2>/dev/null
```

---

## Restricciones

- **No implementar** providers, servicios ni routers — eso es Bloque 3, 4 y 5.
- `modified_at` en `FileInfo` debe ser siempre `datetime` con timezone UTC. No aceptar datetimes naive (sin timezone).
- `folder_path` nunca debe ser `None`. Si el archivo está en la raíz, usar string vacío `""`.
- `preview_url` nunca debe ser string vacío `""`. Si no hay URL, usar `None`.
- La función `get_extensions_for_asset_types` no debe retornar duplicados aunque se pasen categorías solapadas.
- No modificar `app/exceptions.py` ni `app/config.py` — están completos desde el Bloque 1.

---

## Entrega esperada

Al finalizar este bloque, estos archivos deben estar completamente implementados:

```
app/models/common.py      ✅ SourceType, AssetType, ASSET_TYPES_EXTENSIONS, get_extensions_for_asset_types
app/models/request.py     ✅ GoogleDriveCredentials, ProviderCredentials, ListRequest
app/models/response.py    ✅ FileInfo, ListResponse, ErrorDetail, ErrorResponse, HealthResponse
app/main.py               ✅ exception handlers actualizados con ErrorResponse (tipado)
tests/conftest.py         ✅ fixtures base: credentials, list_request, file_info
```

El resto del repositorio no se toca.
