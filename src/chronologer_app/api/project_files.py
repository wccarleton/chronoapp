"""User-selected local file operations, protected from cross-origin browser calls."""
import json
import logging
import secrets
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from .projects import body
from ..services.project_files import project_files, DialogUnavailable, FileConflict

router = APIRouter(prefix="/projects/files")
_token = secrets.token_urlsafe(32)
logger = logging.getLogger(__name__)


def authorize(request, token=True):
    if request.url.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise HTTPException(403, "Local file access requires the local application address.")
    origin = request.headers.get("origin")
    if origin:
        supplied = urlsplit(origin)
        if (supplied.scheme, supplied.netloc) != (request.url.scheme, request.url.netloc):
            raise HTTPException(403, "Cross-origin file access is not allowed.")
    if request.headers.get("sec-fetch-site") == "cross-site":
        raise HTTPException(403, "Cross-site file access is not allowed.")
    if token and not secrets.compare_digest(request.headers.get("x-chronoapp-token", "").encode(), _token.encode()):
        raise HTTPException(403, "File operation session expired. Retry the operation.")


@router.get("/session")
def session(request: Request):
    authorize(request, token=False)
    from fastapi.responses import JSONResponse
    return JSONResponse({"token": _token}, headers={"Cache-Control": "no-store"})


async def perform(function, *args):
    try:
        return await run_in_threadpool(function, *args)
    except FileConflict as error:
        raise HTTPException(409, str(error)) from None
    except DialogUnavailable as error:
        raise HTTPException(503, str(error)) from None
    except (ValueError, RecursionError) as error:
        raise HTTPException(422, str(error)) from None
    except OSError as error:
        logger.exception("Local project file operation failed")
        raise HTTPException(409, f"The local app could not access the selected file: {error.strerror or str(error)}. Your in-app changes are retained.") from None


@router.post("/open")
async def open_project(request: Request):
    authorize(request)
    return await perform(project_files.open)


@router.post("/save")
async def save_project(request: Request):
    authorize(request)
    try:
        payload = json.loads(await body(request))
        if not isinstance(payload, dict) or set(payload) - {"project", "file_id", "save_as"} or "project" not in payload:
            raise ValueError("Save requires a project and optional file_id/save_as fields.")
        identifier, save_as = payload.get("file_id"), payload.get("save_as", False)
        if identifier is not None and (not isinstance(identifier, str) or len(identifier) > 100):
            raise ValueError("Invalid file reference.")
        if type(save_as) is not bool:
            raise ValueError("save_as must be a boolean.")
    except (ValueError, RecursionError) as error:
        raise HTTPException(422, str(error)) from None
    return await perform(project_files.save, payload["project"], identifier, save_as)
