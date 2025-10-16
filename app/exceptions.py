"""Exceptions personnalisées pour l'application."""


class CaveVinException(Exception):
    """Exception de base pour l'application Cave à Vin."""
    pass


class WineNotAvailableError(CaveVinException):
    """Exception levée quand un vin n'est plus disponible."""
    pass


class CellarNotFoundError(CaveVinException):
    """Exception levée quand une cave n'est pas trouvée."""
    pass


class CategoryNotFoundError(CaveVinException):
    """Exception levée quand une catégorie n'est pas trouvée."""
    pass


class ValidationError(CaveVinException):
    """Exception levée lors d'une erreur de validation."""
    pass