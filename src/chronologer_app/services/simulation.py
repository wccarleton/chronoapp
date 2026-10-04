"""Adapt engine prior-predictive datasets for plots and one CSV dataset export."""
import time

import chronologer
import numpy as np

from .posterior_plots import posterior_plots


def simulate_in_worker(request, progress_callback=None):
    start = time.perf_counter()
    spec, settings = request['simulation'], request['settings']
    curve = (chronologer.load_calcurve(spec['curve'], quiet=True)
             if spec['distribution'] == 'calrcarbon' else None)
    result = chronologer.simulate_single_density(spec['n'], distribution=spec['distribution'],
        error=spec['error'], calcurve=curve, draws=spec['draws'], random_seed=912,
        lower=-settings['older'], upper=-settings['younger'], mean_prior=-settings['mean'],
        mean_prior_sd=settings['mean_sd'], sd_prior_scale=settings['sd_scale'],
        progress_callback=progress_callback)
    prior = result.prior['prior'].to_dataset()
    # One complete replicate, rather than averages over unrelated datasets.
    values = -prior['measured'].isel(chain=0, draw=0).values
    rows = []
    for i, value in enumerate(values):
        if spec['distribution'] == 'calrcarbon':
            parameters = dict(c14_mean=float(value), c14_err=spec['error'], curve=spec['curve'])
        elif spec['distribution'] == 'normal':
            parameters = dict(mean=float(value), sd=spec['error'])
        else:
            radius = np.sqrt(3) * spec['error']
            parameters = dict(lower=float(value - radius), upper=float(value + radius))
        rows.append(dict(id=f'Sim-{i + 1}', distribution=spec['distribution'],
                         parameters=parameters, datum='BP1950'))
    return dict(model='single_density', mode='simulate', coordinate_system='negative_bp',
        density={key: value.tolist() for key, value in result.density.items()},
        marginals=posterior_plots(prior, rows),
        prior=dict(type='xarray.DataTree', variables=list(prior.data_vars), sizes=dict(prior.sizes)),
        sampling=dict(draws=spec['draws'], tune=0, chains=1, cores=1, random_seed=912),
        simulation=dict(settings=spec, events=rows, exported_draw=0),
        divergences=0, diagnostics={},
        warnings=['Independent prior-predictive replicates, not an inference run. Plots summarize replicates; CSV exports the first complete generated dataset. Event indices are exchangeable simulation slots, not observed events.'],
        elapsed_seconds=time.perf_counter() - start)
