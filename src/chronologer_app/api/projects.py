"""Stateless project conversion endpoints; filesystem access stays with the chooser."""

import json
from fastapi import APIRouter, HTTPException, Request, Response
from ..projects import MAX_BYTES, MAX_CSV_BYTES, dump_project, import_csv, load_project, new_project

router = APIRouter(prefix="/projects")


async def body(request, limit=MAX_BYTES):
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > limit:
            raise HTTPException(413, f"File exceeds the {limit // (1024 * 1024)} MiB limit.")
        chunks.append(chunk)
    return b"".join(chunks)


@router.get("/new")
def new():
    return new_project()


@router.post("/import-csv")
async def csv_import(request: Request, filename: str = "source.csv", default_curve: str | None = None):
    try:
        return import_csv(await body(request, MAX_CSV_BYTES), filename, default_curve)
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
