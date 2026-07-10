import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from another_atom.agent.orchestrator import execute_run_background
from another_atom.api.routes import router
from another_atom.config import get_settings
from another_atom.domain.errors import AppError
from another_atom.storage.database import SessionLocal, init_database
from another_atom.storage.models import BuildJob


def create_app(*, initialize_database: bool = True) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if initialize_database:
            init_database()
            await asyncio.to_thread(_recover_interrupted_jobs)
        yield

    app = FastAPI(title="Another Atom API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(AppError)
    async def handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.code, "message": exc.message, "details": {}},
        )

    app.include_router(router)
    _mount_studio(app, get_settings().studio_dist)
    return app


def _recover_interrupted_jobs() -> None:
    """Resume persisted jobs after the single-instance V1 service restarts."""
    with SessionLocal() as db:
        run_ids = db.scalars(
            select(BuildJob.run_id).where(BuildJob.status.in_(["queued", "building", "validating"]))
        ).all()
    for run_id in run_ids:
        execute_run_background(run_id)


def _mount_studio(app: FastAPI, dist_path: Path) -> None:
    assets = dist_path / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{path:path}", include_in_schema=False, response_model=None)
    async def studio_fallback(path: str) -> FileResponse | JSONResponse:
        index = dist_path / "index.html"
        if index.exists() and not path.startswith("api/"):
            return FileResponse(index)
        return JSONResponse(
            status_code=404,
            content={"code": "NOT_FOUND", "message": "Resource not found", "details": {}},
        )


app = create_app()
