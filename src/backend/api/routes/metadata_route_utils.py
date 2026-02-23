"""Helpers for composing split metadata routers from the implementation router."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter

from backend.api.routes import metadata_impl

PathPredicate = Callable[[str], bool]


def build_metadata_router(*predicates: PathPredicate) -> APIRouter:
    """Build a router with routes selected from metadata implementation router."""
    router = APIRouter()
    for route in metadata_impl.router.routes:
        path = getattr(route, "path", "")
        if any(predicate(path) for predicate in predicates):
            router.routes.append(route)
    return router
