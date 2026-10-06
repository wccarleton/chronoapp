"""Validate labelled phase fits and submit isolated engine workers."""
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .density import MixtureEvent, Finite, Positive, sampling_for
from .calibration import require_local_curve
from ..sampling import SamplingSettings
from ..services.jobs import get_jobs
from ..services.phases import fit_in_worker
from ..phase_settings import validate_anchors, connections

router = APIRouter()


class PhaseEvent(MixtureEvent):
    label: str = Field(min_length=1, max_length=120)


class Priors(BaseModel):
    model_config = ConfigDict(extra='forbid')
    prior_center: Finite | None = None  # BP1950 in the app, negative BP in the engine.
    prior_scale: Positive | None = None
    delta_scale: Positive | None = None


class PhaseSpec(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str = Field(min_length=1, max_length=120)
    label: str = Field(min_length=1, max_length=120)
    distribution: Literal['uniform', 'normal']
    order: int = Field(strict=True, ge=0)
    parameters: Priors = Field(default_factory=Priors)
    anchors: list[Finite] | None = Field(default=None, min_length=1, max_length=2)

    @model_validator(mode='after')
    def valid_anchors(self):
        validate_anchors(self.model_dump())
        return self


class Edge(BaseModel):
    model_config = ConfigDict(extra='forbid')
    source: str = Field(min_length=1, max_length=120)
    target: str = Field(min_length=1, max_length=120)


class PhaseSettings(BaseModel):
    model_config = ConfigDict(extra='forbid')
    anchors: Literal['center', 'end_start', 'none'] | None = None  # Legacy preset only.
    ordered: bool | None = Field(default=None, strict=True)
    delta_scale: Positive | None = None
    edges: list[Edge] | None = Field(default=None, max_length=100)


class PhaseRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    events: list[PhaseEvent] = Field(min_length=1, max_length=100)
    phases: list[PhaseSpec] = Field(min_length=1, max_length=100)
    settings: PhaseSettings = Field(default_factory=PhaseSettings)
    sampling: SamplingSettings | None = None
    label: str = Field(default='Phase model', min_length=1, max_length=250)

    @model_validator(mode='after')
    def membership(self):
        labels = [p.label for p in self.phases]
        if any(not label.strip() for label in labels) or len(set(labels)) != len(labels):
            raise ValueError('Phase names must be nonempty and unique.')
        if len({p.id for p in self.phases}) != len(self.phases):
            raise ValueError('Phase IDs must be unique.')
        if [p.order for p in self.phases] != list(range(len(self.phases))):
            raise ValueError('Phase order must match its list index; explicit connections define chronology.')
        if set(labels) != {e.label for e in self.events}:
            raise ValueError('Each phase currently needs matching labelled events; unobserved-phase fitting is deferred. All submitted labels must have a phase.')
        connections([p.model_dump() for p in self.phases], self.settings.model_dump())
        return self


@router.post('/phases/jobs', status_code=202)
def start_phase(request: PhaseRequest):
    for curve in {e.parameters['curve'] for e in request.events if e.distribution == 'calrcarbon'}:
        require_local_curve(curve)
    try:
        return get_jobs().submit(fit_in_worker, (request.model_dump(), sampling_for(request)), request.label)
    except ValueError as error:
        raise HTTPException(429, str(error)) from None
    except OSError:
        raise HTTPException(503, 'Cannot write inference logs. Check the local log directory permissions.') from None
