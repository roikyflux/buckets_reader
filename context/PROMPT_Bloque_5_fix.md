# Prompt — Bloque 5 (continuación): ListService + Router

## Problema

Los archivos `app/services/list_service.py` y `app/routers/bucket.py` todavía contienen el stub `# TODO: Bloque 5`. Solo se actualizó `main.py` pero los dos archivos principales del bloque están vacíos.

## Qué implementar ahora

### `app/services/list_service.py`

```python
from __future__ import annotations

import logging

from app.models.common import get_extensions_for_asset_types
from app.models.request import ListRequest
from app.models.response import ListResponse
from app.providers.factory import get_provider

logger = logging.getLogger(__name__)


class ListService:
    """Orquesta el flujo de listado de archivos desde un bucket externo.

    Responsabilidades:
        1. Expandir asset_types a extensiones concretas.
        2. Obtener el provider correcto desde la factory.
        3. Validar credenciales.
        4. Invocar list_files() en el provider.
        5. Construir y retornar ListResponse.

    Lo que este servicio NO hace:
        - No importa ningún provider concreto.
        - No captura excepciones — las propaga al router.
        - No filtra ni transforma los archivos retornados por el provider.
    """

    async def execute(self, request: ListRequest) -> ListResponse:
        extensions = get_extensions_for_asset_types(request.asset_types)

        provider = get_provider(request)
        await provider.validate_credentials()

        files = await provider.list_files(
            folder_id=request.folder_id,
            extensions=extensions,
            max_depth=request.max_depth,
        )

        return ListResponse(
            source=request.source.value,
            folder_id=request.folder_id,
            total_files=len(files),
            asset_types_requested=request.asset_types,
            extensions_searched=extensions,
            files=files,
        )
```

### `app/routers/bucket.py`

```python
from __future__ import annotations

from fastapi import APIRouter

from app.models.request import ListRequest
from app.models.response import ListResponse
from app.services.list_service import ListService

router = APIRouter(prefix="/api/v1/bucket", tags=["bucket"])


@router.post("/list", response_model=ListResponse)
async def list_bucket_files(request: ListRequest) -> ListResponse:
    """Lista archivos disponibles en el bucket origen según los filtros del usuario."""
    service = ListService()
    return await service.execute(request)
```

### `tests/services/test_list_service.py`

Implementar suite completa con `MockProvider`. Ver prompt original del Bloque 5 para la especificación de `MockProvider` y los 9 tests requeridos.

---

## Criterio de verificación

```bash
# Importaciones
python -c "
from app.services.list_service import ListService
from app.routers.bucket import router
print('OK')
"

# Router en main
python -c "
from app.main import app
routes = [r.path for r in app.routes]
assert '/api/v1/bucket/list' in routes
print('Router: OK')
"

# Tests del servicio
pytest tests/services/test_list_service.py -v

# Suite completa
pytest tests/ -v
```
