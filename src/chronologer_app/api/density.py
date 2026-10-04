"""Thin boundary to Chronologer's density API; no statistical model here."""

import logging
import time
from pathlib import Path
from typing import Annotated
from typing import Literal
import math

import chronologer
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .calibration import Determination, require_local_curve
from ..services.jobs import get_jobs, TERMINAL
from ..services.posterior_plots import posterior_plots
from ..services.mcmc_diagnostics import build_diagnostics
from ..sampling import DEFAULT_SAMPLING, SamplingSettings, resolve_cores

router = APIRouter()
logger = logging.getLogger(__name__)
# Only these counts are editable; seed and all other engine settings are unchanged.
SAMPLING = dict(**DEFAULT_SAMPLING, random_seed=912)


def sampling_for(request):
    settings = {**SAMPLING, **(request.sampling.model_dump() if request.sampling is not None else {})}
    settings['cores'] = resolve_cores(settings['chains'], settings.get('cores'))
    return settings
Finite = Annotated[float, Field(strict=True, allow_inf_nan=False)]
Positive = Annotated[float, Field(strict=True, gt=0, allow_inf_nan=False)]


class DensitySettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    older: Finite
    younger: Finite
    mean: Finite
    mean_sd: Positive
    sd_scale: Positive

    @model_validator(mode="after")
    def ordered(self):
        if self.older <= self.younger:
            raise ValueError("Older cal BP must exceed Younger cal BP.")
        return self


class DensityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    determinations: list[Determination] = Field(min_length=1, max_length=100)
    settings: DensitySettings
    sampling: SamplingSettings | None = None


def fit_in_worker(request: dict, sampling: dict, progress_callback=None):
    start = time.perf_counter()
    process = 'observation' in request
    mixture = "events" in request
    if mixture:
        from ..services.measurements import measurements
        rows = request['events']
        observations = measurements(rows)
        if process:
            window = request['observation']
            result = chronologer.models.ippp.gp(
                observations, params=dict(start=-window['older'], end=-window['younger'],
                                          grid_size=window['grid_size']),
                mcmc_config=sampling, progress_callback=progress_callback)
        else:
            result = chronologer.models.density.gmixture(
                observations, params={'K_max': request['K_max']},
                mcmc_config=sampling, progress_callback=progress_callback)
    else:
        rows, settings = request["determinations"], request["settings"]
        curve = chronologer.load_calcurve(rows[0]["curve"], quiet=True)
        result = chronologer.models.density.single(
            dict(radiocarbon_ages=[-row['age'] for row in rows],
                 radiocarbon_errors=[row['error'] for row in rows], calcurve=curve),
            params=dict(lower=-settings['older'], upper=-settings['younger'],
                        mean_prior=-settings['mean'], mean_prior_sd=settings['mean_sd'],
                        sd_prior_scale=settings['sd_scale']),
            mcmc_config=sampling, progress_callback=progress_callback)
    posterior = result.posterior["posterior"].to_dataset()
    stats = result.posterior["sample_stats"].to_dataset()
    divergences = int(stats["diverging"].values.sum())
    warnings = ["Inspect MCMC diagnostics before interpreting this fit; sampling counts alone do not establish convergence."]
    if sampling['chains'] < 2:
        warnings.append('Only one chain: between-chain R-hat is unavailable.')
    if sampling['draws'] < 1000 or sampling['tune'] < 1000:
        warnings.append('Fewer than 1,000 retained draws or tuning iterations per chain: this may be insufficient. Inspect diagnostics.')
    if process:
        warnings.append('Assumes complete observation throughout the declared period. Intensity is events per year, not a normalized density or a demographic estimate. Check sensitivity to GP priors, window and grid resolution.')
    if divergences:
        warnings.append(f"{divergences} divergent transitions: this fit may be unreliable.")
    if "reached_max_treedepth" in stats and stats["reached_max_treedepth"].values.any():
        warnings.append("Maximum tree depth reached for some samples.")
    diagnostics = {}
    if process:
        diagnostics = result.specification
    elif mixture:
        import numpy as np
        weights = posterior['weights'].values.reshape(-1, request['K_max'])
        diagnostics = dict(priors=result.priors, weight_mean=weights.mean(axis=0).tolist(),
                           weight_below_005=(weights < .05).mean(axis=0).tolist(),
                           weight_interval=np.quantile(weights, [.025, .975], axis=0).tolist())
    if progress_callback:
        total = (sampling['draws'] + sampling['tune']) * sampling['chains']
        progress_callback(dict(stage='Generating MCMC diagnostics', completed=total, total=total))
    mcmc = build_diagnostics(result.posterior, rows, sampling, model_spec=diagnostics if process else None)
    curve = ({'intensity': {key: values.tolist() for key, values in result.intensity.items()}} if process
             else {'density': {key: values.tolist() for key, values in result.density.items()}})
    return {"model": 'ippp_gp' if process else "gaussian_mixture" if mixture else "truncated_normal_hierarchy", "coordinate_system": "negative_bp",
            "mcmc": mcmc,
            "diagnostics": diagnostics,
            **curve,
            "marginals": posterior_plots(posterior, rows),
            "posterior": {"type": "xarray.DataTree", "variables": list(posterior.data_vars),
                          "sizes": dict(posterior.sizes)},
            "sampling": sampling, "divergences": divergences, "warnings": warnings,
            "elapsed_seconds": time.perf_counter() - start}


class DensityJobRequest(DensityRequest):
    label: str = Field(default="Density fit", min_length=1, max_length=250)


class MixtureEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=120)
    distribution: Literal['calrcarbon', 'normal', 'uniform']
    parameters: dict
    datum: Literal['BP1950'] = 'BP1950'

    @model_validator(mode='after')
    def valid_measurement(self):
        p = self.parameters
        keys = {'calrcarbon': ('c14_mean', 'c14_err'), 'normal': ('mean', 'sd'), 'uniform': ('lower', 'upper')}[self.distribution]
        if any(type(p.get(key)) not in (int, float) or not math.isfinite(p[key]) for key in keys):
            raise ValueError('Measurement parameters must be finite numbers.')
        if self.distribution == 'uniform':
            if p['lower'] >= p['upper']:
                raise ValueError('Uniform upper must exceed lower.')
        elif p[keys[1]] <= 0:
            raise ValueError('Measurement error/SD must be positive.')
        if self.distribution == 'calrcarbon' and not isinstance(p.get('curve'), str):
            raise ValueError('Radiocarbon events require a curve.')
        return self


class MixtureJobRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    events: list[MixtureEvent] = Field(min_length=1, max_length=100)
    K_max: int = Field(default=5, strict=True, ge=1, le=20)
    label: str = Field(default='Mixture fit', min_length=1, max_length=250)
    sampling: SamplingSettings | None = None


class ObservationWindow(BaseModel):
    model_config = ConfigDict(extra='forbid')
    older: Finite  # Required: never substitute calibrated tails or event extrema.
    younger: Finite
    grid_size: int = Field(default=32, strict=True, ge=4, le=256)

    @model_validator(mode='after')
    def ordered(self):
        if self.older <= self.younger:
            raise ValueError('Declare observation start (older cal BP) greater than end (younger cal BP).')
        return self


class GPJobRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    events: list[MixtureEvent] = Field(min_length=1, max_length=100)
    observation: ObservationWindow
    sampling: SamplingSettings | None = None
    label: str = Field(default='GP IPPP fit', min_length=1, max_length=250)


@router.post('/ippp/jobs', status_code=202)
def start_gp(request: GPJobRequest):
    for event in request.events:
        if event.distribution == 'calrcarbon':
            require_local_curve(event.parameters['curve'])
    try:
        return get_jobs().submit(fit_in_worker, (request.model_dump(), sampling_for(request)), request.label)
    except ValueError as error:
        raise HTTPException(429, str(error)) from None
    except OSError:
        raise HTTPException(503, 'Cannot write inference logs. Check the local log directory permissions.') from None


@router.post('/mixture/jobs', status_code=202)
def start_mixture(request: MixtureJobRequest):
    curves = {e.parameters['curve'] for e in request.events if e.distribution == 'calrcarbon'}
    # Each measurement carries its own curve's shared spline references.
    for curve in curves:
        require_local_curve(curve)
    try:
        return get_jobs().submit(fit_in_worker, (request.model_dump(), sampling_for(request)), request.label)
    except ValueError as error:
        raise HTTPException(429, str(error)) from None
    except OSError:
        raise HTTPException(503, 'Cannot write inference logs. Check the local log directory permissions.') from None


def submit_density(request: DensityRequest, label="Density fit"):
    curves = {row.curve for row in request.determinations}
    if len(curves) != 1 or None in curves:
        raise HTTPException(422, "This density benchmark requires one shared calibration curve for all events.")
    require_local_curve(next(iter(curves)))
    try:
        return get_jobs().submit(fit_in_worker, (request.model_dump(), sampling_for(request)), label)
    except ValueError as error:
        raise HTTPException(429, str(error)) from None
    except OSError:
        logger.exception("Could not create inference log")
        raise HTTPException(503, "Cannot write inference logs. Check the local log directory permissions.") from None


def job_or_404(identifier, result=False):
    try:
        return get_jobs().get(identifier, result=result)
    except KeyError:
        raise HTTPException(404, "Run not found. The server may have restarted or its history expired.") from None


@router.post("/density/jobs", status_code=202)
def start_density(request: DensityJobRequest):
    return submit_density(request, request.label)


@router.get("/jobs")
def list_jobs():
    manager = get_jobs()
    return {"jobs": manager.list(), "max_workers": manager.workers, "log_directory": str(manager.log_dir)}


@router.get("/jobs/{identifier}")
def get_job(identifier: str):
    return job_or_404(identifier)


@router.get("/jobs/{identifier}/result")
def job_result(identifier: str):
    job = job_or_404(identifier, result=True)
    if job["status"] == "completed":
        return job["result"]
    if job["status"] == "failed":
        raise HTTPException(422 if job["error_type"] == "ValueError" else 500,
                            f"{job['error']} See this run's log for details.")
    raise HTTPException(409, "Run cancelled." if job["status"] == "cancelled" else "Run has not finished.")


@router.post("/jobs/{identifier}/cancel")
def cancel_job(identifier: str):
    job_or_404(identifier)
    return get_jobs().cancel(identifier)


@router.get("/jobs/{identifier}/log")
def job_log(identifier: str, download: bool = False):
    job = job_or_404(identifier)
    path = Path(job["log_path"])
    if download:
        return FileResponse(path, media_type="text/plain", filename=path.name)
    # Bound each live log fetch; the download endpoint returns the whole file.
    with path.open("rb") as stream:
        stream.seek(max(0, path.stat().st_size - 65536))
        text = stream.read().decode("utf-8", errors="replace")
    return PlainTextResponse(text)


@router.post("/density")
def fit_density(request: DensityRequest):
    """Compatibility endpoint; the browser uses the nonblocking jobs API."""
    job = submit_density(request)
    while job["status"] not in TERMINAL:
        time.sleep(.1)
        job = job_or_404(job["id"])
    return job_result(job["id"])
