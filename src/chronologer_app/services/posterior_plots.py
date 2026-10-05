"""Display-only marginal histograms of retained posterior draws."""
import numpy as np


def marginal(values):
    values = np.asarray(values, dtype=float).reshape(-1)
    if not values.size or not np.isfinite(values).all():
        raise ValueError("Posterior draws must be finite and nonempty.")
    # Histograms avoid adding smoothing assumptions or leaking past bounds.
    heights, edges = np.histogram(values, bins=min(40, max(1, int(np.sqrt(values.size)))), density=True)
    return {"t_values": np.repeat(edges, 2)[1:-1].tolist(),
            "pdf_values": np.repeat(heights, 2).tolist()}


def posterior_plots(posterior, rows, *, include_events=True):
    if 'intensity' in posterior:
        definitions = [('log_rate', 'Baseline log intensity', False),
                       ('amplitude', 'GP log-intensity amplitude', False),
                       ('length_scale', 'GP length scale · years', False),
                       ('integrated_intensity', 'Expected event count in observation period', False)]
    else:
        definitions = [('tau_mu', 'Model location (mean) · cal BP', True),
                       ('tau_sd', 'Model scale (SD) · years', False)]
    parameters = [{"name": name, "label": label, "calendar": calendar,
                   **marginal(posterior[name].values)}
                  for name, label, calendar in definitions if name in posterior]
    events = []
    if include_events:
        dates = posterior["tau"].transpose("chain", "draw", ...).values
        events = [{"id": row["id"], "index": i, **marginal(dates[..., i])}
                  for i, row in enumerate(rows)]
    return {"parameters": parameters, "events": events}
