"""Worker adaptation checks with deterministic posterior fixtures; no sampling."""
import base64
import json
from types import SimpleNamespace
import numpy as np
import pytest
import xarray as xr
from chronologer_app.api import density


@pytest.mark.parametrize('model', ['single', 'mixture', 'process'])
def test_worker_attaches_score_and_download(monkeypatch, model):
    ds = xr.Dataset({
        'tau_mu': (('chain', 'draw'), [[-5., -4.]]),
        'tau_sd': (('chain', 'draw'), [[2., 3.]]),
        'tau': (('chain', 'draw', 'event'), [[[-5.], [-4.]]]),
        **{k: (('chain', 'draw', 'component'), np.array(v).reshape(1, 2, 1))
           for k, v in dict(means=[-5., -4.], scales=[2., 3.], weights=[1., 1.]).items()},
    })
    if model == 'process':
        ds['intensity'] = (('chain', 'draw', 'grid'), [[[1.] * 4, [2.] * 4]])
    stats = xr.Dataset({'diverging': (('chain', 'draw'), [[False, False]])})
    tree = xr.DataTree.from_dict({'posterior': ds, 'sample_stats': stats})
    curve = {k: np.array(v) for k, v in dict(t_values=[-10., 0.], pdf_values=[.1, .1],
                                            lower_values=[.05, .05], upper_values=[.2, .2]).items()}
    fit = SimpleNamespace(posterior=tree, density=curve, priors={}, specification={},
        intensity={k: np.array(v) for k, v in dict(t_values=[-10., -7., -3., 0.],
            rate_values=[1.] * 4, lower_values=[.5] * 4, upper_values=[2.] * 4).items()})
    target = density.chronologer.models.ippp if model == 'process' else density.chronologer.models.density
    monkeypatch.setattr(target, 'gp' if model == 'process' else 'gmixture' if model == 'mixture' else 'single_density',
                        lambda *args, **kwargs: fit)
    monkeypatch.setattr(density, 'build_diagnostics', lambda *args, **kwargs: {'artifacts': []})
    request = {'events': [dict(id='event', distribution='normal', parameters={'mean': 5., 'sd': 1.})]}
    if model == 'single':
        request['settings'] = dict(older=10., younger=0., mean=5., mean_sd=2., sd_scale=3.)
    elif model == 'mixture':
        request['K_max'] = 1
    else:
        request['observation'] = dict(older=10., younger=0., grid_size=4)
    result = density.fit_in_worker(request, dict(chains=1, draws=2, tune=0))
    score = result['model_diagnostics']
    assert np.isfinite(score['waic'])
    assert score['likelihood'] == ('observation_window' if model == 'process' else 'event_marginal')
    artifact = result['mcmc']['artifacts'][0]
    assert artifact['name'] == 'model-diagnostics.json'
    assert json.loads(base64.b64decode(artifact['data'])) == score
