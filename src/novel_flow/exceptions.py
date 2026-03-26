class NovelFlowError(Exception):
    """Base exception for the project."""


class StorageError(NovelFlowError):
    """Raised when persistence fails."""


class PatchExecutionError(NovelFlowError):
    """Raised when a patch instruction cannot be executed."""


class AgentExecutionError(NovelFlowError):
    """Raised when an agent fails to complete its task."""
