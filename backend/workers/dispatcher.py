"""Job dispatcher."""

import logging
from typing import Awaitable, Callable, Any

from sqlalchemy.ext.asyncio import AsyncSession


logger = logging.getLogger(__name__)

# Type alias for job handler functions
JobHandler = Callable[[dict, AsyncSession], Awaitable[Any]]

_HANDLERS: dict[str, JobHandler] = {}


def register_handler(job_type: str) -> Callable[[JobHandler], JobHandler]:
    """Decorator to register a job handler.

    Parameters
    ----------
    job_type : str
        The job type string (e.g., 'move_items').

    Returns
    -------
    Callable[[JobHandler], JobHandler]
        Decorator function.
    """

    def decorator(func: JobHandler) -> JobHandler:
        _HANDLERS[job_type] = func
        logger.info(f"Registered handler for job type: {job_type}")
        return func

    return decorator


def get_handler(job_type: str) -> JobHandler | None:
    """Get the handler for a specific job type.

    Parameters
    ----------
    job_type : str
        The job type string.

    Returns
    -------
    JobHandler | None
        The handler function or None if not found.
    """
    return _HANDLERS.get(job_type)
