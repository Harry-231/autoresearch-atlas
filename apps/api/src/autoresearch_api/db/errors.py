class DataAccessError(RuntimeError):
    """Base error for explicit data-access failures."""


class DataNotFoundError(DataAccessError):
    """Raised when a requested durable record does not exist."""


class DataConflictError(DataAccessError):
    """Raised when a write conflicts with an existing durable record."""


class DependencyUnavailableError(DataAccessError):
    """Raised when an external datastore cannot be reached."""
