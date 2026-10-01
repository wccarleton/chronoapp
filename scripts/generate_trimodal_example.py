"""Generate demonstration data, not a Process Lab simulation interface.

Run from the app root: conda run -n chronoapp python scripts/generate_trimodal_example.py
"""
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
from chronologer import load_calcurve
from chronologer.utils import simulate_c14


def main():
    seed = 20261001
    rng = np.random.default_rng(seed)
    centres = np.array([1800., 3500., 5200.])  # conventional positive cal BP
    scales = np.array([70., 100., 90.])
    component = rng.choice(3, size=60, p=[1/3, 1/3, 1/3])
    calendar_bp = rng.normal(centres[component], scales[component])
    curve = load_calcurve('intcal20', quiet=True)
    tau = -calendar_bp  # Chronologer's increasing negative-BP coordinate
    assert np.all((tau > curve['calbp'][0]) & (tau < curve['calbp'][-1]))

    # Existing helper draws curve-level radiocarbon uncertainty. It uses the
    # legacy NumPy RNG, so seed that separately for exact script reproduction.
    np.random.seed(seed + 1)
    latent_c14 = simulate_c14(tau, curve['calbp'], curve['c14bp'], curve['c14_sigma'])
    lab_sd = rng.choice([25., 30., 35., 40.], size=len(tau))
    observed_c14 = rng.normal(latent_c14, lab_sd)
    assert np.isfinite(observed_c14).all()

    directory = Path(__file__).resolve().parents[1] / 'docs' / 'examples'
    with (directory / 'trimodal-calendar.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = csv.writer(stream)
        writer.writerow(['id', 'c14_mean', 'c14_err', 'curve'])
        for i, (age, error) in enumerate(zip(observed_c14, lab_sd), 1):
            writer.writerow([f'Trimodal {i:02d}', round(float(-age), 1), int(error), 'intcal20'])
    with (directory / 'trimodal-calendar-truth.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = csv.writer(stream)
        writer.writerow(['id', 'generating_component', 'true_cal_bp', 'curve_mean_c14_bp', 'curve_sd', 'latent_c14_bp'])
        for i, t in enumerate(tau):
            writer.writerow([f'Trimodal {i+1:02d}', int(component[i]+1), float(-t),
                             float(-np.interp(t, curve['calbp'], curve['c14bp'])),
                             float(np.interp(t, curve['calbp'], curve['c14_sigma'])), float(-latent_c14[i])])
    metadata = dict(seed=seed, curve_rng_seed=seed+1, events=len(tau),
                    calendar_means_bp=centres.tolist(), calendar_sds_years=scales.tolist(),
                    weights=[1/3]*3, realized_counts=np.bincount(component, minlength=3).tolist(),
                    curve='intcal20',
                    curve_arrays_sha256=hashlib.sha256(b''.join(np.asarray(curve[k], dtype='<f8').tobytes()
                        for k in ('calbp', 'c14bp', 'c14_sigma'))).hexdigest(),
                    helper='chronologer.utils.simulate_c14', interpolation='linear',
                    measurement_sd_years=[25, 30, 35, 40], reported_age_rounding_years=.1)
    (directory / 'trimodal-calendar-metadata.json').write_text(json.dumps(metadata, indent=2)+'\n', encoding='utf-8')
    print(f'Generated {len(tau)} observations; calendar-component counts: {metadata["realized_counts"]}')


if __name__ == '__main__':
    main()
