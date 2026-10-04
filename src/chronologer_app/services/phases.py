"""Run the engine's phase model and adapt retained draws to display arrays."""
import time

import chronologer
import numpy as np
from scipy.stats import norm, uniform

from .measurements import measurements
from .posterior_plots import marginal, posterior_plots
from .mcmc_diagnostics import build_diagnostics
from ..phase_settings import anchors_for, ordered


def specification(request):
    specs = {}
    for row in request['phases']:
        p = row['parameters']
        center = p.get('prior_center')
        specs[row['label']] = chronologer.Phase(
            row['distribution'], prior_center=None if center is None else -center,
            prior_scale=p.get('prior_scale'))
    settings = request['settings']
    orders = []
    if ordered(settings):
        for a, b in zip(request['phases'], request['phases'][1:]):
            anchors = (anchors_for(a, settings)[-1], anchors_for(b, settings)[0])
            orders.append(chronologer.Order(a['label'], b['label'], anchors,
                                           settings.get('delta_scale')))
    return specs, orders


def estimate(values):
    low, high = np.quantile(values, [.025, .975])
    return dict(mean=float(np.mean(values)), lower=float(low), upper=float(high))


def phase_plots(posterior, specs):
    phases = []
    for label, spec in specs.items():
        mu = posterior['mu'].sel(phase=label).values.reshape(-1, 1)
        scale = posterior['scale'].sel(phase=label).values.reshape(-1, 1)
        radius = scale / 2 if spec.distribution == 'uniform' else 6 * scale
        grid = np.linspace(np.min(mu - radius), np.max(mu + radius), 512)
        values = (uniform.pdf(grid[None, :], loc=mu - scale / 2, scale=scale)
                  if spec.distribution == 'uniform' else norm.pdf(grid[None, :], loc=mu, scale=scale))
        low, high = np.quantile(values, [.025, .975], axis=0)
        p, q = (0., 1.) if spec.distribution == 'uniform' else (.05, .95)
        phases.append(dict(label=label, distribution=spec.distribution,
            density=dict(t_values=grid.tolist(), pdf_values=values.mean(axis=0).tolist(),
                         lower_values=low.tolist(), upper_values=high.tolist()),
            interval=dict(p=p, q=q, lower=estimate(spec.quantile(p, mu, scale)),
                          upper=estimate(spec.quantile(q, mu, scale))),
            parameters=[dict(name='mu', label='Phase center · cal BP', calendar=True, **marginal(mu)),
                        dict(name='scale', label=('Phase width' if spec.distribution == 'uniform' else 'Phase sigma') + ' · years',
                             calendar=False, **marginal(scale))]))
    return phases


def fit_in_worker(request, sampling, progress_callback=None):
    start = time.perf_counter()
    specs, orders = specification(request)
    rows = request['events']
    trace = chronologer.fit_phase(rows, specs, measurements=measurements(rows), orders=orders,
                                  **sampling, progress_callback=progress_callback)
    posterior = trace['posterior'].to_dataset()
    stats = trace['sample_stats'].to_dataset()
    divergences = int(stats['diverging'].values.sum())
    warnings = ['Inspect MCMC diagnostics before interpreting phase distributions or anchor separations.']
    if sampling['chains'] < 2:
        warnings.append('Only one chain: between-chain R-hat is unavailable.')
    if sampling['draws'] < 1000 or sampling['tune'] < 1000:
        warnings.append('Fewer than 1,000 draws or tuning iterations per chain; inspect diagnostics.')
    if divergences:
        warnings.append(f'{divergences} divergent transitions: this fit may be unreliable.')
    if 'reached_max_treedepth' in stats and stats['reached_max_treedepth'].values.any():
        warnings.append('Maximum tree depth reached for some samples.')
    if progress_callback:
        total = sampling['chains'] * (sampling['draws'] + sampling['tune'])
        progress_callback(dict(stage='Generating phase plots and MCMC diagnostics', completed=total, total=total))
    deltas = [dict(before=order.before, after=order.after, anchors=list(order.anchors),
                   **estimate(posterior['delta'].isel(order=i).values)) for i, order in enumerate(orders)]
    plots = phase_plots(posterior, specs)
    mcmc = build_diagnostics(trace, rows, sampling, model_spec=request)
    return dict(model='phase', coordinate_system='negative_bp', phases=plots,
                diagnostics=dict(deltas=deltas), marginals=posterior_plots(posterior, rows),
                posterior=dict(type='xarray.DataTree', variables=list(posterior.data_vars), sizes=dict(posterior.sizes)),
                sampling=sampling, divergences=divergences, warnings=warnings,
                elapsed_seconds=time.perf_counter() - start,
                mcmc=mcmc)
