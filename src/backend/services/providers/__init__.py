"""Drive provider abstractions and factories.

Avoid importing the factory at module import time to prevent circular imports
when provider clients import shared HTTP helpers.
"""

from backend.services.providers.base import DriveProviderClient


def build_drive_client(*args, **kwargs):
    from backend.services.providers.factory import build_drive_client as _build_drive_client

    return _build_drive_client(*args, **kwargs)


__all__ = ["DriveProviderClient", "build_drive_client"]
