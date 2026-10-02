"""Shared app sampling settings for current and future Bayesian model requests."""
from pydantic import BaseModel, ConfigDict, Field
import os

DEFAULT_SAMPLING = dict(draws=1000, tune=1000, chains=4)


class SamplingSettings(BaseModel):
    model_config = ConfigDict(extra='forbid')
    draws: int = Field(default=1000, strict=True, ge=1)
    tune: int = Field(default=1000, strict=True, ge=0)
    chains: int = Field(default=4, strict=True, ge=1)
    cores: int | None = Field(default=None, strict=True, ge=1)


def resolve_cores(chains, cores=None):
    available = os.cpu_count() or 1
    return min(chains, available, 4 if cores is None else cores)


def validate_saved_sampling(parameters, result=None):
    if 'sampling' not in parameters:
        return  # Older projects retain their recorded result settings.
    sampling = parameters['sampling']
    if not isinstance(sampling, dict) or set(sampling) not in (set(DEFAULT_SAMPLING), set(DEFAULT_SAMPLING) | {'cores'}):
        raise ValueError('Sampling settings require draws, tune and chains.')
    for key, value in sampling.items():
        if key == 'cores' and value is None:
            continue  # Automatic concurrency is resolved on the machine running the fit.
        if value is None and result is None:
            continue  # An unfinished editable draft can still be saved.
        if type(value) is not int or value < (0 if key == 'tune' else 1):
            raise ValueError('Sampling counts must be integers; draws/chains must be positive and tuning nonnegative.')
    if result is not None and any(result['sampling'][key] != value for key, value in sampling.items() if key != 'cores'):
        raise ValueError('Saved sampling settings do not match the result.')
