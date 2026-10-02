"""Post-fit diagnostics and portable vector artifacts; never changes inference."""
import base64
import csv
import io
import json
import warnings
from importlib.metadata import version

import arviz as az
import numpy as np


def finite(value):
    return float(value) if np.isfinite(value) else None


def spectral_variance(values):
    """Bartlett/Newey-West estimate of spectral density at frequency zero.

    Biased autocovariances and bandwidth floor(n**(1/3)); unlike coda's AR fit.
    """
    x = np.asarray(values, dtype=float)
    x = x - x.mean()
    n = len(x)
    bandwidth = max(1, int(n ** (1 / 3)))
    return (x @ x + 2 * sum((1 - lag / (bandwidth + 1)) * (x[lag:] @ x[:-lag])
                           for lag in range(1, bandwidth + 1))) / n


def geweke(values):
    """First 10% vs last 50%, separately per chain; None when not estimable."""
    n = len(values)
    first, last = values[:int(.1 * n)], values[n - int(.5 * n):]
    if min(len(first), len(last)) < 20:
        return None
    variance = spectral_variance(first) / len(first) + spectral_variance(last) / len(last)
    return finite((first.mean() - last.mean()) / np.sqrt(variance)) if variance > 0 else None


def artifact(name, mime, content):
    return dict(name=name, mime=mime, data=base64.b64encode(content).decode('ascii'))


def build_diagnostics(trace, events, sampling):
    posterior = trace['posterior'].to_dataset()
    stats = trace['sample_stats'].to_dataset()
    notes = [
        'Retained draws only; warmup is excluded. Short development runs cannot establish convergence.',
        'Rank-normalized split R-hat, bulk/tail ESS and MCSE use ArviZ. Inspect R-hat > 1.01, low ESS and trace mixing; no single diagnostic proves convergence.',
        'Geweke Z (Python): first 10% versus last 50% of each chain, Bartlett/Newey-West spectral variance, bandwidth floor(n^(1/3)). This is not coda::geweke.diag (which fits an AR spectrum).',
        'Geweke needs at least 20 draws in each segment (200 retained draws per chain). Large |Z| suggests a shift; many simultaneous comparisons can flag chance differences.',
        'Unavailable values are null/NA, including constant variables, insufficient draws and single-chain R-hat. Trace coordinates are native negative BP; scale variables are years.',
        'Vector plots retain every draw visually; raw numerical chain matrices are not saved. Event indices are zero-based in the input snapshot.',
    ]
    variables, series = [], []
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        for name, variable in posterior.data_vars.items():
            values = variable.transpose('chain', 'draw', ...).values
            for index in np.ndindex(values.shape[2:]):
                x = values[(slice(None), slice(None), *index)]
                label = name + ('[' + ','.join(map(str, index)) + ']' if index else '')
                if name in ('tau', 'r_latent') and len(index) == 1 and index[0] < len(events):
                    label += ' - ' + events[index[0]]['id']
                row = dict(variable=label, r_hat=None, ess_bulk=None, ess_tail=None,
                           mcse_mean=None, mcse_sd=None, geweke_z=[geweke(chain) for chain in x])
                # A chain stuck at a constant is not evidence of convergence.
                if x.shape[1] >= 4 and np.all(np.ptp(x, axis=1) > 0):
                    if x.shape[0] >= 2:
                        row['r_hat'] = finite(az.rhat(x, method='rank'))
                    for method in ('bulk', 'tail'):
                        row['ess_' + method] = finite(az.ess(x, method=method, **({'prob': .05} if method == 'tail' else {})))
                    for method in ('mean', 'sd'):
                        row['mcse_' + method] = finite(az.mcse(x, method=method))
                variables.append(row)
                series.append((label, x))
    notes.extend(sorted({str(w.message) for w in caught})[:20])
    chains = []
    for chain in range(posterior.sizes['chain']):
        s = stats.isel(chain=chain)
        energy = s['energy'].values if 'energy' in s else None
        bfmi = None
        if energy is not None and len(energy) > 1 and np.var(energy, ddof=1) > 0:
            bfmi = finite(np.mean(np.diff(energy) ** 2) / np.var(energy, ddof=1))
        chains.append(dict(chain=chain + 1, divergences=int(s['diverging'].sum()) if 'diverging' in s else None,
                           bfmi=bfmi,
                           max_tree_depth=int(s['tree_depth'].max()) if 'tree_depth' in s else None,
                           reached_max_treedepth=int(s['reached_max_treedepth'].sum()) if 'reached_max_treedepth' in s else None,
                           acceptance_mean=finite(s['acceptance_rate'].mean()) if 'acceptance_rate' in s else None))
    notes.append('E-BFMI below 0.3, divergences or transitions reaching the depth limit warrant investigation. Maximum observed depth alone does not establish that the limit was reached.')
    report = dict(version=1, variables=variables, chains=chains, notes=notes,
                  versions={package: version(package) for package in ('pymc', 'pytensor', 'arviz', 'chronologer', 'chronologer-app')})
    artifacts = [artifact('diagnostics.json', 'application/json', json.dumps(
        {**report, 'sampling': sampling, 'events': events}, allow_nan=False, indent=2).encode('utf-8'))]
    output = io.StringIO(newline='')
    fields = ['variable', 'r_hat', 'ess_bulk', 'ess_tail', 'mcse_mean', 'mcse_sd']
    writer = csv.writer(output)
    writer.writerow(fields + [f'geweke_z_chain_{i + 1}' for i in range(len(chains))])
    for row in variables:
        writer.writerow([row[k] for k in fields] + row['geweke_z'])
    artifacts.append(artifact('diagnostics.csv', 'text/csv', output.getvalue().encode('utf-8')))
    artifacts.extend(trace_artifacts(series))
    report['artifacts'] = artifacts
    return report


def trace_artifacts(series):
    # Object API and Agg avoid GUI state in spawned workers.
    import matplotlib as mpl
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.backends.backend_pdf import PdfPages
    artifacts, pdf = [], io.BytesIO()
    with mpl.rc_context({'svg.fonttype': 'none', 'pdf.fonttype': 42, 'path.simplify': False,
                         'text.parse_math': False}), PdfPages(pdf) as pages:
        for start in range(0, len(series), 4):
            chunk = series[start:start + 4]
            fig = Figure(figsize=(11, 2.5 * len(chunk) + .65), layout='constrained')
            FigureCanvasAgg(fig)
            axes = fig.subplots(len(chunk), 2, squeeze=False)
            fig.suptitle('MCMC retained draws (warmup excluded) - native model coordinates', fontsize=11)
            for (label, values), (trace_ax, hist_ax) in zip(chunk, axes):
                for chain, draws in enumerate(values):
                    color = ['#176e73', '#bc7031', '#6a51a3', '#527b30'][chain % 4]
                    trace_ax.plot(np.arange(1, len(draws) + 1), draws, lw=.7, alpha=.8,
                                  color=color, label=f'Chain {chain + 1}')
                    hist_ax.hist(draws, bins=min(30, max(1, int(np.sqrt(len(draws))))), density=True,
                                 histtype='step', color=color, lw=1, label=f'Chain {chain + 1}')
                trace_ax.set(title=label, xlabel='Retained draw', ylabel='Value')
                hist_ax.set(xlabel='Value', ylabel='Density')
                trace_ax.legend(fontsize=7, loc='best')
                for ax in (trace_ax, hist_ax):
                    ax.tick_params(labelsize=8)
                    ax.grid(alpha=.15)
            svg = io.BytesIO()
            fig.savefig(svg, format='svg')
            artifacts.append(artifact(f'trace-{start // 4 + 1:03}.svg', 'image/svg+xml', svg.getvalue()))
            pages.savefig(fig)
            fig.clear()
    artifacts.append(artifact('trace-plots.pdf', 'application/pdf', pdf.getvalue()))
    return artifacts
