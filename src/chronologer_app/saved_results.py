"""Validation for plot-ready saved runs; no executable models or chain matrices."""
import math
from datetime import datetime
from .sampling import validate_saved_sampling


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
    require(run['model'] in ('density', 'mixture', 'ippp_gp', 'phase') and isinstance(run['parameters'], dict), 'model/settings')
    process = run['model'] == 'ippp_gp'
    phase = run['model'] == 'phase'
    require(isinstance(run['events'], list) and 1 <= len(run['events']) <= 100, 'events')
    require(all(isinstance(e, dict) for e in run['events']), 'event records')
    r = run['result']
    curve_key = 'phases' if phase else 'intensity' if process else 'density'
    fields = {'model', 'coordinate_system', curve_key, 'marginals', 'posterior', 'sampling', 'divergences', 'warnings', 'elapsed_seconds'}
    require(isinstance(r, dict) and fields <= set(r) and not set(r) - fields - {'diagnostics', 'mcmc', 'model_diagnostics'}, 'result fields (raw samples are not supported)')
    if 'model_diagnostics' in r:
        score = r['model_diagnostics']
        require(phase and isinstance(score, dict), 'model diagnostics')
        if set(score) == {'unavailable'}:
            require(isinstance(score['unavailable'], str) and 0 < len(score['unavailable']) <= 2000, 'WAIC unavailable reason')
        else:
            require(set(score) == {'waic', 'se', 'elpd_waic', 'p_waic', 'n_events', 'n_samples', 'warning', 'notes', 'likelihood'}, 'WAIC fields')
            require(all(number(score[k]) for k in ('waic', 'se', 'elpd_waic', 'p_waic'))
                    and score['se'] >= 0 and score['p_waic'] >= 0, 'WAIC estimates')
            require(math.isclose(score['waic'], -2 * score['elpd_waic'], rel_tol=1e-9, abs_tol=1e-9), 'WAIC scale')
            require(type(score['n_events']) is int and score['n_events'] == len(run['events'])
                    and type(score['n_samples']) is int and score['n_samples'] >= 2, 'WAIC counts')
            require(type(score['warning']) is bool and score['likelihood'] == 'event_marginal'
                    and isinstance(score['notes'], list) and len(score['notes']) <= 20
                    and all(isinstance(note, str) and len(note) <= 4000 for note in score['notes']), 'WAIC metadata')
    require(r['model'] == ('phase' if phase else 'ippp_gp' if process else 'gaussian_mixture' if run['model'] == 'mixture' else 'truncated_normal_hierarchy') and r['coordinate_system'] == 'negative_bp', 'model/coordinates')
    require(isinstance(r[curve_key], list if phase else dict), 'curve arrays')
    curve = r[curve_key]
    if phase:
        from .api.phases import PhaseRequest
        params = run['parameters']
        require({'phases', 'delta_scale', 'sampling'} <= set(params)
                and bool({'anchors', 'ordered'} & set(params))
                and not set(params) - {'phases', 'anchors', 'ordered', 'delta_scale', 'sampling'}, 'phase settings')
        try:
            request = PhaseRequest(events=run['events'], phases=params['phases'],
                                   settings={k: params[k] for k in ('anchors', 'ordered', 'delta_scale') if k in params},
                                   sampling=params['sampling'])
        except ValueError:
            require(False, 'phase input snapshot')
        require(len(curve) == len(request.phases), 'phase count')
        for item, spec in zip(curve, request.phases):
            require(isinstance(item, dict) and set(item) == {'label', 'distribution', 'density', 'interval', 'parameters'}, 'phase plot fields')
            require(item['label'] == spec.label and item['distribution'] == spec.distribution, 'phase identity')
            require(isinstance(item['density'], dict) and set(item['density']) == {'t_values', 'pdf_values', 'lower_values', 'upper_values'}, 'phase density fields')
            arrays(item['density'], band=True, strict=True)
            interval = item['interval']
            p, q = (0., 1.) if spec.distribution == 'uniform' else (.05, .95)
            require(isinstance(interval, dict) and set(interval) == {'p', 'q', 'lower', 'upper'} and interval['p'] == p and interval['q'] == q, 'phase interval')
            for estimate in (interval['lower'], interval['upper']):
                require(isinstance(estimate, dict) and set(estimate) == {'mean', 'lower', 'upper'} and all(number(v) for v in estimate.values()) and estimate['lower'] <= estimate['upper'], 'phase quantile estimate')
            require(interval['lower']['mean'] <= interval['upper']['mean'], 'phase interval order')
            require(isinstance(item['parameters'], list) and len(item['parameters']) == 2, 'phase marginals')
            for j, parameter in enumerate(item['parameters']):
                require(isinstance(parameter, dict) and set(parameter) == {'name', 'label', 'calendar', 't_values', 'pdf_values'} and parameter['name'] == ('mu' if j == 0 else 'scale') and parameter['calendar'] is (j == 0) and isinstance(parameter['label'], str), 'phase parameter')
                arrays(parameter)
    elif process:
        require(set(curve) == {'t_values', 'rate_values', 'lower_values', 'upper_values'}, 'intensity fields')
        arrays({**curve, 'pdf_values': curve['rate_values']}, band=True, strict=True)
    else:
        arrays(curve, band=True, strict=True)
        require(set(curve) == {'t_values', 'pdf_values', 'lower_values', 'upper_values'}, 'density fields')
    require(number(r['elapsed_seconds']) and r['elapsed_seconds'] >= 0, 'elapsed time')
    require(type(r['divergences']) is int and r['divergences'] >= 0, 'divergences')
    require(isinstance(r['warnings'], list) and len(r['warnings']) <= 100 and all(isinstance(w, str) and len(w) <= 4000 for w in r['warnings']), 'warnings')
    sampling = r['sampling']
    require(isinstance(sampling, dict) and set(sampling) in ({'draws', 'tune', 'chains', 'random_seed'}, {'draws', 'tune', 'chains', 'random_seed', 'cores'}), 'sampling metadata')
    require(type(sampling.get('cores', 1)) is int and 1 <= sampling.get('cores', 1) <= sampling['chains'], 'sampling cores')
    require(all(type(v) is int for v in sampling.values()) and sampling['draws'] > 0 and sampling['tune'] >= 0 and sampling['chains'] > 0, 'sampling values')
    validate_saved_sampling(run['parameters'], r)
    posterior = r['posterior']
    require(isinstance(posterior, dict) and set(posterior) == {'type', 'variables', 'sizes'}, 'posterior metadata only')
    require(posterior['type'] == 'xarray.DataTree' and isinstance(posterior['variables'], list)
            and all(isinstance(v, str) for v in posterior['variables']) and isinstance(posterior['sizes'], dict)
            and all(type(v) is int and v > 0 for v in posterior['sizes'].values()), 'posterior structure')
    marginals = r['marginals']
    require(isinstance(marginals, dict) and set(marginals) == {'parameters', 'events'}, 'marginals')
    names = ['log_rate', 'amplitude', 'length_scale', 'integrated_intensity'] if process else [] if phase or run['model'] == 'mixture' else ['tau_mu', 'tau_sd']
    require(isinstance(marginals['parameters'], list) and len(marginals['parameters']) == len(names), 'parameter marginals')
    for i, p in enumerate(marginals['parameters']):
        require(isinstance(p, dict) and set(p) == {'name', 'label', 'calendar', 't_values', 'pdf_values'}, 'parameter fields')
        require(p['name'] == names[i] and isinstance(p['label'], str) and p['calendar'] is (not process and i == 0), 'parameter identity')
        arrays(p)
    require(isinstance(marginals['events'], list) and len(marginals['events']) == len(run['events']), 'event marginals')
    for i, e in enumerate(marginals['events']):
        require(isinstance(e, dict) and set(e) == {'id', 'index', 't_values', 'pdf_values'}, 'event fields')
        require(e['index'] == i and e['id'] == run['events'][i].get('id'), 'event identity')
        arrays(e)
    diagnostics = r.get('diagnostics', {})
    require(isinstance(diagnostics, dict), 'diagnostics')
    if phase:
        from .services.phases import specification
        _, orders = specification(request.model_dump())
        require(set(diagnostics) == {'deltas'} and isinstance(diagnostics['deltas'], list) and len(diagnostics['deltas']) == len(orders), 'phase delta count')
        for item, order in zip(diagnostics['deltas'], orders):
            require(isinstance(item, dict) and set(item) == {'before', 'after', 'anchors', 'mean', 'lower', 'upper'}, 'phase delta fields')
            require(item['before'] == order.before and item['after'] == order.after and item['anchors'] == list(order.anchors), 'phase delta identity')
            require(all(number(item[k]) and item[k] > 0 for k in ('mean', 'lower', 'upper')) and item['lower'] <= item['upper'], 'phase delta estimates')
    elif process:
        require(set(diagnostics) == {'start', 'end', 'grid_size', 'baseline_count', 'log_rate_sd', 'amplitude_scale', 'length_scale_median', 'length_scale_log_sd'}, 'GP specification')
        require(all(number(v) for v in diagnostics.values()), 'finite GP specification')
        require(diagnostics['start'] < diagnostics['end'], 'observation period')
        require(type(diagnostics['grid_size']) is int and 4 <= diagnostics['grid_size'] <= 256, 'GP grid size')
        require(all(diagnostics[k] > 0 for k in ('baseline_count', 'log_rate_sd', 'amplitude_scale', 'length_scale_median', 'length_scale_log_sd')), 'GP priors')
        params = run['parameters']
        require(number(params.get('older')) and number(params.get('younger')), 'explicit observation endpoints')
        require(-params['older'] == diagnostics['start'] and -params['younger'] == diagnostics['end'], 'saved observation period')
        require(params.get('grid_size') == diagnostics['grid_size'] == len(curve['t_values']), 'saved GP grid')
        require(curve['t_values'][0] == diagnostics['start'] and curve['t_values'][-1] == diagnostics['end'], 'intensity observation domain')
    elif run['model'] == 'mixture':
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
    if 'mcmc' in r:
        validate_mcmc(r['mcmc'], sampling['chains'])


def validate_mcmc(mcmc, chains):
    """Bounded, data-only reports. SVGs are displayed as images, never HTML."""
    import base64
    import binascii
    import re
    def require(condition):
        if not condition:
            raise ValueError('Invalid saved Summary result: MCMC diagnostics')
    def scalar(v):
        return v is None or (type(v) in (float, int) and math.isfinite(v))
    require(isinstance(mcmc, dict) and set(mcmc) == {'version', 'variables', 'chains', 'notes', 'versions', 'artifacts'} and mcmc['version'] == 1)
    require(isinstance(mcmc['variables'], list) and 1 <= len(mcmc['variables']) <= 1000)
    metrics = {'r_hat', 'ess_bulk', 'ess_tail', 'mcse_mean', 'mcse_sd'}
    for row in mcmc['variables']:
        require(isinstance(row, dict) and set(row) == metrics | {'variable', 'geweke_z'})
        require(isinstance(row['variable'], str) and len(row['variable']) <= 500)
        require(all(scalar(row[k]) and (row[k] is None or row[k] >= 0) for k in metrics))
        require(isinstance(row['geweke_z'], list) and len(row['geweke_z']) == chains and all(scalar(v) for v in row['geweke_z']))
    require(isinstance(mcmc['chains'], list) and len(mcmc['chains']) == chains)
    for i, row in enumerate(mcmc['chains']):
        require(isinstance(row, dict) and set(row) == {'chain', 'divergences', 'bfmi', 'max_tree_depth', 'reached_max_treedepth', 'acceptance_mean'})
        require(row['chain'] == i + 1 and all(scalar(v) and (v is None or v >= 0) for v in row.values()))
    require(isinstance(mcmc['notes'], list) and len(mcmc['notes']) <= 100 and all(isinstance(v, str) and len(v) <= 4000 for v in mcmc['notes']))
    require(isinstance(mcmc['versions'], dict) and len(mcmc['versions']) <= 20 and all(isinstance(k, str) and isinstance(v, str) and len(k + v) <= 200 for k, v in mcmc['versions'].items()))
    require(isinstance(mcmc['artifacts'], list) and len(mcmc['artifacts']) <= 260)
    names = set()
    types = {'diagnostics.json': 'application/json', 'diagnostics.csv': 'text/csv',
             'trace-plots.pdf': 'application/pdf', 'messages.txt': 'text/plain'}
    for item in mcmc['artifacts']:
        require(isinstance(item, dict) and set(item) == {'name', 'mime', 'data'})
        name = item['name']
        require(isinstance(name, str) and name not in names)
        names.add(name)
        expected = 'image/svg+xml' if re.fullmatch(r'trace-\d{3}\.svg', name) else types.get(name)
        require(expected is not None and item['mime'] == expected and isinstance(item['data'], str) and len(item['data']) <= 32 * 1024 * 1024)
        try:
            base64.b64decode(item['data'], validate=True)
        except (ValueError, binascii.Error):
            require(False)
