"""Drive Organizer FastAPI Application.

This is the main entrypoint for the Drive Organizer backend API.
It configures the FastAPI application with all routes and middleware.
"""


import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.api.routes import accounts, auth, drive, jobs, metadata, items
from backend.core.config import get_settings
from backend.core.exceptions import DriveOrganizerError
from backend.db.session import async_session_maker
from backend.workers.handlers import move, upload, metadata as metadata_handler, sync as sync_handler  # noqa: F401
from backend.workers.runner import BackgroundWorker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    """Application lifespan handler.

    Parameters
    ----------
    app : FastAPI
        The FastAPI application instance.

    Yields
    ------
    None
        Yields control to the application.
    """
    async with async_session_maker() as _:
        # Initialize any required services or cache here
        pass
    
    # Initialize background worker
    worker = BackgroundWorker(async_session_maker)
    worker_task = asyncio.create_task(worker.start())
    
    logger.info("Starting Drive Organizer API on %s:%s", settings.host, settings.port)
    yield
    
    # Shutdown background worker
    logger.info("Stopping background worker...")
    worker.stop()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass
        
    logger.info("Shutting down Drive Organizer API")

def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns
    -------
    FastAPI
        Configured FastAPI application instance.
    """
    settings = get_settings()

    app = FastAPI(
        title="Drive Organizer API",
        description="API for managing multiple OneDrive accounts",
        version="0.1.0",
        lifespan=lifespan,
        debug=settings.debug,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth.router, prefix="/api/v1")
    app.include_router(accounts.router, prefix="/api/v1")
    app.include_router(drive.router, prefix="/api/v1")
    app.include_router(jobs.router, prefix="/api/v1")
    app.include_router(metadata.router, prefix="/api/v1")
    app.include_router(items.router, prefix="/api/v1")

    @app.exception_handler(DriveOrganizerError)
    async def handle_drive_organizer_error(_, exc: DriveOrganizerError) -> JSONResponse:
        """Convert custom application errors into consistent HTTP responses."""
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.message},
        )

    @app.get("/health")
    async def health_check() -> dict:
        """Health check endpoint.

        Returns
        -------
        dict
            Health status.
        """
        return {"status": "healthy"}

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "backend.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
