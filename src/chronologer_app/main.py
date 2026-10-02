"""Local development server for the Chronologer interface."""

from pathlib import Path
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .api.calibration import router
from .api.projects import router as projects_router
from .api.density import router as density_router
from .api.project_files import router as project_files_router
from .services.jobs import shutdown_jobs

@asynccontextmanager
async def lifespan(app):
    yield
    shutdown_jobs()


app = FastAPI(title="Chronologer", version="0.1.0", lifespan=lifespan)


@app.middleware("http")
async def revalidate_frontend(request, call_next):
    response = await call_next(request)
    if not request.url.path.startswith("/api/"):
        # Unversioned ES module imports must refresh when the local app changes.
        response.headers["Cache-Control"] = "no-cache"
    return response


app.include_router(router, prefix="/api")
app.include_router(projects_router, prefix="/api")
app.include_router(density_router, prefix="/api")
app.include_router(project_files_router, prefix="/api")

# Development layout: assets stay independent of the Python API package.
frontend = (Path(sys._MEIPASS) if getattr(sys, "frozen", False)
            else Path(__file__).resolve().parents[2]) / "frontend"
app.mount("/", StaticFiles(directory=frontend, html=True), name="frontend")


def run():
    import sys
    if "--chrono-file-dialog" in sys.argv:
        from .native_dialog import main
        main()
        return
    import uvicorn

    uvicorn.run("chronologer_app.main:app", host="127.0.0.1", port=8000)


if __name__ == "__main__":
    run()
