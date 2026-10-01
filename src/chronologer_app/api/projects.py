"""Stateless project conversion endpoints; filesystem access stays with the chooser."""

import json
from fastapi import APIRouter, HTTPException, Request, Response
from ..projects import MAX_BYTES, dump_project, import_csv, load_project, new_project

router = APIRouter(prefix="/projects")


async def body(request):
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_BYTES:
            raise HTTPException(413, "Project or CSV exceeds the 5 MiB limit.")
        chunks.append(chunk)
    return b"".join(chunks)


@router.get("/new")
def new():
    return new_project()


@router.post("/import-csv")
async def csv_import(request: Request, filename: str = "source.csv", default_curve: str | None = None):
    try:
        return import_csv(await body(request), filename, default_curve)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None


@router.post("/encode")
async def encode(request: Request):
    try:
        project = json.loads(await body(request))
        return Response(dump_project(project), media_type="application/zip")
    except (ValueError, UnicodeDecodeError, RecursionError) as exc:
        raise HTTPException(422, str(exc)) from None


@router.post("/decode")
async def decode(request: Request):
    try:
        return load_project(await body(request))
    except (ValueError, RecursionError) as exc:
        raise HTTPException(422, str(exc)) from None
