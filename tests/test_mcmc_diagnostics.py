import base64
from copy import deepcopy
import json

import arviz as az
import numpy as np
import pytest
import xarray as xr

from chronologer_app.services.mcmc_diagnostics import build_diagnostics, geweke, spectral_variance
from chronologer_app.saved_results import validate_mcmc
from chronologer_app.projects import dump_project, load_project
from test_saved_results import saved_project


def synthetic_trace(draws=400, chains=2):
    rng = np.random.default_rng(45)
    x = rng.normal(size=(chains, draws))
    if chains > 1:
        x[1] += 3  # Deliberately unmixed chains: R-hat must expose this.
    return xr.DataTree.from_dict({
        'posterior': xr.Dataset({'location': (('chain', 'draw'), x),
                                 'constant': (('chain', 'draw'), np.ones_like(x))}),
        'sample_stats': xr.Dataset({
            'energy': (('chain', 'draw'), rng.normal(size=x.shape)),
            'diverging': (('chain', 'draw'), np.zeros_like(x, dtype=bool)),
            'tree_depth': (('chain', 'draw'), np.full_like(x, 3, dtype=int)),
            'reached_max_treedepth': (('chain', 'draw'), np.zeros_like(x, dtype=bool)),
            'acceptance_rate': (('chain', 'draw'), np.full_like(x, .9))})})


@pytest.fixture(scope='module')
def report():
    return build_diagnostics(synthetic_trace(), [], dict(draws=400, tune=50, chains=2, random_seed=45))


def test_diagnostics_match_arviz_and_detect_unmixed_chains(report):
    x = synthetic_trace()['posterior']['location'].values
    row = report['variables'][0]
    assert row['r_hat'] == pytest.approx(float(az.rhat(x)))
    assert row['r_hat'] > 1.1
    assert row['ess_bulk'] == pytest.approx(float(az.ess(x, method='bulk')))
    assert row['ess_tail'] == pytest.approx(float(az.ess(x, method='tail', prob=.05)))
    assert row['mcse_mean'] == pytest.approx(float(az.mcse(x, method='mean')))
    assert all(v is not None for v in row['geweke_z'])
    constant = report['variables'][1]
    assert constant['r_hat'] is None and constant['ess_bulk'] is None
    assert constant['geweke_z'] == [None, None]
    energy = synthetic_trace()['sample_stats']['energy'].values[0]
    assert report['chains'][0]['bfmi'] == pytest.approx(np.mean(np.diff(energy)**2) / np.var(energy, ddof=1))
    assert report['chains'][0]['max_tree_depth'] == 3
    assert report['chains'][0]['reached_max_treedepth'] == 0
    validate_mcmc(report, 2)
    json.dumps(report, allow_nan=False)


def test_geweke_uses_spectral_variance_and_flags_shift():
    rng = np.random.default_rng(321)
    x = rng.normal(size=2000)
    x[:200] += 3
    # Independent matrix expression for the Bartlett spectral estimate.
    a, b = x[:200], x[-1000:]
    def expected(segment):
        centered = segment - segment.mean()
        n = len(segment)
        bandwidth = int(n ** (1 / 3))
        distance = abs(np.arange(n)[:, None] - np.arange(n)[None, :])
        kernel = np.maximum(0, 1 - distance / (bandwidth + 1))
        return centered @ kernel @ centered / n
    assert spectral_variance(a) == pytest.approx(expected(a))
    assert geweke(x) == pytest.approx((a.mean() - b.mean()) / np.sqrt(expected(a)/len(a) + expected(b)/len(b)))
    assert geweke(x) > 10
    assert geweke(x[:100]) is None
    assert geweke(np.ones(400)) is None


def test_short_single_chain_reports_unavailable_rhat():
    report = build_diagnostics(synthetic_trace(draws=6, chains=1), [], {})
    assert all(r['r_hat'] is None and r['geweke_z'] == [None] for r in report['variables'])
    validate_mcmc(report, 1)


def test_portable_vector_artifacts_and_project_roundtrip(report):
    artifacts = {a['name']: base64.b64decode(a['data']) for a in report['artifacts']}
    assert artifacts['trace-plots.pdf'].startswith(b'%PDF')
    assert b'<svg' in artifacts['trace-001.svg'] and b'<image' not in artifacts['trace-001.svg']
    assert b'location' in artifacts['diagnostics.csv']
    assert json.loads(artifacts['diagnostics.json'])['versions']['pymc']
    project = saved_project()
    project['summaries'][0]['saved_run']['result']['mcmc'] = report
    assert load_project(dump_project(project)) == project
    del project['summaries'][0]['saved_run']
    assert b'trace-plots.pdf' not in dump_project(project)


@pytest.mark.parametrize('change', [
    lambda r: r['variables'][0].__setitem__('r_hat', float('nan')),
    lambda r: r['variables'][0].__setitem__('geweke_z', [1]),
    lambda r: r['artifacts'][0].__setitem__('name', '../unsafe.json'),
    lambda r: r['artifacts'][0].__setitem__('mime', 'text/html'),
    lambda r: r['artifacts'][0].__setitem__('data', 'not base64'),
])
def test_invalid_reports_rejected(report, change):
    bad = deepcopy(report)
    change(bad)
    with pytest.raises(ValueError, match='MCMC diagnostics'):
        validate_mcmc(bad, 2)
