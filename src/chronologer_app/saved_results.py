"""Validation for plot-ready saved runs; no executable models or chain matrices."""
import math
from datetime import datetime


def validate_saved_run(run):
    def require(condition, message):
        if not condition:
            raise ValueError(f"Invalid saved Summary result: {message}")
    def number(value):
        return type(value) in (int, float) and math.isfinite(value)
    def arrays(data, band=False, strict=False):
        keys = ['t_values', 'pdf_values'] + (['lower_values', 'upper_values'] if band else [])
        require(isinstance(data, dict) and all(k in data for k in keys), 'missing density arrays')
        t = data['t_values']
        require(isinstance(t, list) and 2 <= len(t) <= 20000, 'invalid grid size')
        require(all(number(v) for v in t), 'nonfinite grid')
        require(all(b > a if strict else b >= a for a, b in zip(t, t[1:])) and t[-1] > t[0], 'unordered grid')
        for key in keys[1:]:
            a = data[key]
            require(isinstance(a, list) and len(a) == len(t) and all(number(v) and v >= 0 for v in a), 'invalid density values')
        require(max(data['pdf_values']) > 0, 'empty density')
        if band:
            require(all(a <= b for a, b in zip(data['lower_values'], data['upper_values'])), 'reversed band')
    require(isinstance(run, dict) and set(run) == {'id', 'created_at', 'model', 'events', 'parameters', 'result'}, 'run fields')
    require(isinstance(run['id'], str) and 0 < len(run['id']) <= 120, 'run ID')
    try:
        timestamp = datetime.fromisoformat(run['created_at'].replace('Z', '+00:00'))
        require(timestamp.tzinfo is not None, 'timestamp timezone')
    except (AttributeError, TypeError, ValueError):
        raise ValueError('Invalid saved Summary result: timestamp') from None
    require(run['model'] in ('density', 'mixture') and isinstance(run['parameters'], dict), 'model/settings')
    require(isinstance(run['events'], list) and 1 <= len(run['events']) <= 100, 'events')
    require(all(isinstance(e, dict) for e in run['events']), 'event records')
    r = run['result']
    fields = {'model', 'coordinate_system', 'density', 'marginals', 'posterior', 'sampling', 'divergences', 'warnings', 'elapsed_seconds'}
    require(isinstance(r, dict) and fields <= set(r) and not set(r) - fields - {'diagnostics'}, 'result fields (raw samples are not supported)')
    require(r['model'] == ('gaussian_mixture' if run['model'] == 'mixture' else 'truncated_normal_hierarchy') and r['coordinate_system'] == 'negative_bp', 'model/coordinates')
    arrays(r['density'], band=True, strict=True)
    require(set(r['density']) == {'t_values', 'pdf_values', 'lower_values', 'upper_values'}, 'density fields')
    require(number(r['elapsed_seconds']) and r['elapsed_seconds'] >= 0, 'elapsed time')
    require(type(r['divergences']) is int and r['divergences'] >= 0, 'divergences')
    require(isinstance(r['warnings'], list) and len(r['warnings']) <= 100 and all(isinstance(w, str) and len(w) <= 4000 for w in r['warnings']), 'warnings')
    sampling = r['sampling']
    require(isinstance(sampling, dict) and set(sampling) == {'draws', 'tune', 'chains', 'random_seed'}, 'sampling metadata')
    require(all(type(v) is int for v in sampling.values()) and sampling['draws'] > 0 and sampling['tune'] >= 0 and sampling['chains'] > 0, 'sampling values')
    posterior = r['posterior']
    require(isinstance(posterior, dict) and set(posterior) == {'type', 'variables', 'sizes'}, 'posterior metadata only')
    require(posterior['type'] == 'xarray.DataTree' and isinstance(posterior['variables'], list)
            and all(isinstance(v, str) for v in posterior['variables']) and isinstance(posterior['sizes'], dict)
            and all(type(v) is int and v > 0 for v in posterior['sizes'].values()), 'posterior structure')
    marginals = r['marginals']
    require(isinstance(marginals, dict) and set(marginals) == {'parameters', 'events'}, 'marginals')
    require(isinstance(marginals['parameters'], list) and len(marginals['parameters']) == (0 if run['model'] == 'mixture' else 2), 'parameter marginals')
    for i, p in enumerate(marginals['parameters']):
        require(isinstance(p, dict) and set(p) == {'name', 'label', 'calendar', 't_values', 'pdf_values'}, 'parameter fields')
        require(p['name'] == ['tau_mu', 'tau_sd'][i] and isinstance(p['label'], str) and p['calendar'] is (i == 0), 'parameter identity')
        arrays(p)
    require(isinstance(marginals['events'], list) and len(marginals['events']) == len(run['events']), 'event marginals')
    for i, e in enumerate(marginals['events']):
        require(isinstance(e, dict) and set(e) == {'id', 'index', 't_values', 'pdf_values'}, 'event fields')
        require(e['index'] == i and e['id'] == run['events'][i].get('id'), 'event identity')
        arrays(e)
    diagnostics = r.get('diagnostics', {})
    require(isinstance(diagnostics, dict), 'diagnostics')
    if run['model'] == 'mixture':
        require(set(diagnostics) == {'priors', 'weight_mean', 'weight_below_005', 'weight_interval'}, 'mixture diagnostics')
        k = run['parameters'].get('K_max')
        require(type(k) is int and 1 <= k <= 20, 'maximum modes')
        require(isinstance(diagnostics['weight_interval'], list) and len(diagnostics['weight_interval']) == 2, 'weight intervals')
        for values in [diagnostics['weight_mean'], diagnostics['weight_below_005'], *diagnostics['weight_interval']]:
            require(isinstance(values, list) and len(values) == k and all(number(v) and 0 <= v <= 1 for v in values), 'weight diagnostics')
        require(abs(sum(diagnostics['weight_mean']) - 1) < 1e-6, 'weight normalization')
        require(isinstance(diagnostics['priors'], dict) and all(number(v) for v in diagnostics['priors'].values()), 'priors')
    else:
        require(not diagnostics, 'unexpected diagnostics')
