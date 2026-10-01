"""Request validation and serialization around the scientific engine."""

import logging
import math
import multiprocessing
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Annotated

import chronologer
from chronologer.calcurves import CACHE_DIR, DEFAULT_CURVES
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter()
logger = logging.getLogger(__name__)


class Determination(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    id: str = Field(min_length=1, max_length=120)
    age: Annotated[float, Field(strict=True, allow_inf_nan=False)]
    error: Annotated[float, Field(strict=True, gt=0, allow_inf_nan=False)]
    curve: str | None = None


class CalibrationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    curve: str | None = None  # Legacy request-level fallback; row choices take precedence.
    determinations: list[Determination] = Field(min_length=1, max_length=100)


def require_local_curve(name: str):
    if name not in DEFAULT_CURVES:
        raise HTTPException(422, "Unsupported calibration curve.")
    if not (Path(CACHE_DIR) / f"{name}.14c").is_file():
        raise HTTPException(409, "This curve is supported by chronologer but is not installed locally.")


@router.get("/curves")
def curves():
    # The current engine has no public discovery API. Keep registry access here.
    return {
        "engine_version": chronologer.__version__,
        "curves": [
            {"id": name, "label": name, "available": (Path(CACHE_DIR) / f"{name}.14c").is_file()}
            for name in DEFAULT_CURVES
        ],
    }


@router.get("/curves/{name}")
def curve_data(name: str):
    require_local_curve(name)
    try:
        curve = chronologer.load_calcurve(name, quiet=True)
        return {"id": name, "coordinate_system": "negative_bp", **{key: values.tolist() for key, values in curve.items()}}
    except (ValueError, OSError):
        logger.exception("Could not load curve %s", name)
        raise HTTPException(503, "The engine could not load this calibration curve.") from None


def calibrate_in_worker(curve_name: str, rows: list[dict]) -> dict:
    """A fresh process isolates the engine's curve-specific global spline cache."""
    curve = chronologer.load_calcurve(curve_name, quiet=True)
    results = chronologer.calibrate(
        radiocarbon_ages=[-row["age"] for row in rows],
        radiocarbon_errors=[row["error"] for row in rows],
        calcurve=curve,
        as_pandas=False,
    )
    # Preserve returned coordinates and values exactly; omit distribution objects
    # and unreviewed standard deviations. Summary calculations belong to the engine.
    serialized = []
    for row, result in zip(rows, results, strict=True):
        t = result["t_values"]
        p = result["pdf_values"]
        if len(t) < 2 or len(t) != len(p):
            raise ValueError("Engine returned no plottable result")
        if not all(math.isfinite(float(v)) for v in (*t, *p, result["mean"])):
            raise ValueError("Engine returned non-finite values")
        serialized.append({**row, "curve": curve_name, "t_values": t.tolist(), "pdf_values": p.tolist(),
                           "posterior_mean": float(result["mean"]),
                           "hdi_probability": 0.95,
                           "hdi_intervals": [[float(a), float(b)] for a, b in result["hdi_intervals"]]})
    return {
        "curve": curve_name,
        "coordinate_system": "negative_bp",
        "value_label": "Calibration output",
        "results": serialized,
    }


@router.post("/calibrate")
def calibrate(request: CalibrationRequest):
    groups = {}
    for index, row in enumerate(request.determinations):
        curve = row.curve or request.curve
        if not curve:
            raise HTTPException(422, f"Row {index + 1} ({row.id}): choose a calibration curve.")
        require_local_curve(curve)
        groups.setdefault(curve, []).append((index, row.model_dump()))
    try:
        ordered = [None] * len(request.determinations)
        for curve, indexed_rows in groups.items():
            # A distinct process per curve preserves the existing engine's cache
            # isolation. Never evaluate two different curves in the same worker.
            with ProcessPoolExecutor(max_workers=1, mp_context=multiprocessing.get_context("spawn")) as worker:
                batch = worker.submit(calibrate_in_worker, curve, [row for _, row in indexed_rows]).result()
            for (index, _), result in zip(indexed_rows, batch["results"], strict=True):
                ordered[index] = result
        return {"curve": next(iter(groups)) if len(groups) == 1 else None,
                "curves": list(groups), "coordinate_system": "negative_bp",
                "value_label": "Calibration output", "results": ordered}
    except (ValueError, IndexError, FloatingPointError):
        raise HTTPException(422, "The engine could not calibrate these values. Check ages and errors; a determination may lie outside the curve's usable range.") from None
    except Exception:
        logger.exception("Calibration worker failed")
        raise HTTPException(503, "Calibration could not finish. Check the local server log and try again.") from None
