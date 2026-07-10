import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from another_atom.api.routes import router
from another_atom.build.worker import worker_loop
from another_atom.config import get_settings
from another_atom.domain.errors import AppError
from another_atom.storage.database import init_database


def create_app(*, initialize_database: bool = True) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if initialize_database:
            init_database()
            stop_worker = asyncio.Event()
            worker_task = asyncio.create_task(worker_loop(stop_worker))
        try:
            yield
        finally:
            if initialize_database:
                stop_worker.set()
                await worker_task

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


def _mount_studio(app: FastAPI, dist_path: Path) -> None:
    assets = dist_path / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{path:path}", include_in_schema=False, response_model=None)
    async def studio_fallback(path: str) -> FileResponse | JSONResponse:
        index = dist_path / "index.html"
        candidate = (dist_path / path).resolve()
        if candidate.is_relative_to(dist_path.resolve()) and candidate.is_file():
            return FileResponse(candidate)
        if index.exists() and not path.startswith("api/"):
            return FileResponse(index)
        return JSONResponse(
            status_code=404,
            content={"code": "NOT_FOUND", "message": "Resource not found", "details": {}},
        )


app = create_app()
