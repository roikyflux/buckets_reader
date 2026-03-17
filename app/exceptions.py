from __future__ import annotations

class ETLBucketServiceError(Exception):
    """Base de todas las excepciones del sistema."""
    pass

class InvalidCredentialsError(ETLBucketServiceError):
    """Token inválido, expirado o sin permisos."""
    pass

class UnsupportedProviderError(ETLBucketServiceError):
    """El campo source no tiene un provider registrado."""
    pass

class FolderNotFoundError(ETLBucketServiceError):
    """La carpeta solicitada no existe o no es accesible."""
    pass

class ProviderRateLimitError(ETLBucketServiceError):
    """El provider rechazó la llamada por rate limiting."""
    pass

class ProviderConnectionError(ETLBucketServiceError):
    """Error de red o timeout al conectar con el provider."""
    pass
