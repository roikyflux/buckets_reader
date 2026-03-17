from __future__ import annotations

from abc import ABC, abstractmethod

from app.models.response import FileInfo


class BucketProvider(ABC):
    """Contrato base para todos los providers de bucket.

    Responsabilidades de una implementación:
    - Ser inicializada con las credenciales específicas del provider sin realizar llamadas de red.
    - Preparar cualquier cliente SDK necesario en `validate_credentials()` respetando el Token
      Forwarding Pattern descrito en ADR-03.
    - Ejecutar llamadas potencialmente bloqueantes usando `asyncio.get_event_loop().run_in_executor`
      cuando el SDK sea síncrono, en alineación con ADR-10.
    - Permanecer completamente stateless entre requests. No almacenar datos de usuario más allá de
      la vida de la instancia, tal como detalla DOC-07.
    - Traducir todos los errores del SDK a las excepciones definidas en `app.exceptions`.

    Para agregar un nuevo provider, sigue DOC-07 paso a paso: registra el `SourceType`, define las
    credenciales, implementa la subclase de `BucketProvider` y actualiza la factory.
    """

    @abstractmethod
    async def validate_credentials(self) -> None:
        """Inicializa el cliente del provider usando las credenciales provistas.

        No debe realizar llamadas externas para validar tokens: el microservicio confía en el
        access token recibido (Token Forwarding Pattern). Si ocurre un error de red durante la
        preparación del cliente, se debe lanzar `ProviderConnectionError`.
        """

    @abstractmethod
    async def list_files(
        self,
        folder_id: str,
        extensions: list[str],
        max_depth: int | None = None,
        *,
        current_depth: int = 0,
        current_path: str = "",
    ) -> list[FileInfo]:
        """Retorna la lista plana de archivos que coinciden con las extensiones indicadas.

        La implementación debe manejar recursión y paginación interna del provider, respetar
        `max_depth` (None = sin límite) y construir `folder_path` relativo para cada archivo.

        Excepciones esperadas:
            FolderNotFoundError: cuando `folder_id` es inválido o inaccesible.
            InvalidCredentialsError: si el provider rechaza las credenciales.
            ProviderRateLimitError: cuando el provider impone rate limiting.
            ProviderConnectionError: ante fallas de red o timeouts.
        """

    @abstractmethod
    async def get_file_metadata(self, file_id: str) -> FileInfo:
        """Obtiene la metadata de un archivo individual usando su identificador.

        Debe lanzar `FolderNotFoundError` cuando el archivo no exista o sea inaccesible.
        """


__all__ = ["BucketProvider"]
