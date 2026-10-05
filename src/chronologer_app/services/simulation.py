"""Adapt engine prior-predictive datasets for plots and one CSV dataset export."""
import time

import chronologer
import numpy as np

from .posterior_plots import posterior_plots


def measurement_plots(rows):
    """Display measurement PDFs for the exported dataset in negative BP."""
    from scipy.stats import norm, uniform
    plots = []
    for i, row in enumerate(rows):
        p = row['parameters']
        if row['distribution'] == 'uniform':
            distribution = uniform(-p['upper'], p['upper'] - p['lower'])
            limits = distribution.support()
        else:
            center, sd = ((-p['c14_mean'], p['c14_err']) if row['distribution'] == 'calrcarbon'
                          else (-p['mean'], p['sd']))
            distribution = norm(center, sd)
            limits = (center - 4 * sd, center + 4 * sd)
        grid = np.linspace(*limits, 257)
        plots.append(dict(id=row['id'], index=i, t_values=grid.tolist(),
                          pdf_values=distribution.pdf(grid).tolist()))
    return plots


def simulate_in_worker(request, progress_callback=None):
    start = time.perf_counter()
    spec, settings = request['simulation'], request['settings']
    curve = (chronologer.load_calcurve(spec['curve'], quiet=True)
             if spec['distribution'] == 'calrcarbon' else None)
    options = dict(distribution=spec['distribution'],
        error=spec['error'], calcurve=curve, draws=spec['draws'], random_seed=912,
        progress_callback=progress_callback)
    mixture = request.get('model') == 'mixture'
    if mixture:
        result = chronologer.simulate_gaussian_mixture(spec['n'], K_max=settings['K_max'],
            prior_center=-settings['prior_center'], prior_scale=settings['prior_scale'], **options)
    else:
        result = chronologer.simulate_single_density(spec['n'],
            lower=-settings['older'], upper=-settings['younger'], mean_prior=-settings['mean'],
            mean_prior_sd=settings['mean_sd'], sd_prior_scale=settings['sd_scale'], **options)
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
    diagnostics = {}
    if mixture:
        weights = prior['weights'].values.reshape(-1, settings['K_max'])
        diagnostics = dict(priors=result.priors, weight_mean=weights.mean(axis=0).tolist(),
            weight_below_005=(weights < .05).mean(axis=0).tolist(),
            weight_interval=np.quantile(weights, [.025, .975], axis=0).tolist())
    marginals = posterior_plots(prior, rows, include_events=False)
    marginals['events'] = measurement_plots(rows[:100])
    warnings = ['Independent prior-predictive replicates, not an inference run. Model density summarizes replicates; event measurement densities and CSV use the first complete generated dataset.']
    if len(rows) > 100:
        warnings.append(f'Showing the first 100 of {len(rows)} measurement curves; all {len(rows)} measurements are saved and exported.')
    if spec['draws'] == 1:
        warnings.append('One random parameter set: the model band collapses to one curve and does not summarize prior uncertainty.')
    return dict(model='gaussian_mixture' if mixture else 'single_density', mode='simulate', coordinate_system='negative_bp',
        density={key: value.tolist() for key, value in result.density.items()},
        marginals=marginals,
        prior=dict(type='xarray.DataTree', variables=list(prior.data_vars), sizes=dict(prior.sizes)),
        sampling=dict(draws=spec['draws'], tune=0, chains=1, cores=1, random_seed=912),
        simulation=dict(settings=spec, events=rows, exported_draw=0, event_density='measurement', plotted_events=len(marginals['events'])),
        divergences=0, diagnostics=diagnostics,
        warnings=warnings,
        elapsed_seconds=time.perf_counter() - start)
