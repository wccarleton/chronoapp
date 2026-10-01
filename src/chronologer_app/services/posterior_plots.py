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


def posterior_plots(posterior, rows):
    parameters = [{"name": name, "label": label, "calendar": calendar,
                   **marginal(posterior[name].values)}
                  for name, label, calendar in [
                      ("tau_mu", "Model location (mean) · cal BP", True),
                      ("tau_sd", "Model scale (SD) · years", False)] if name in posterior]
    dates = posterior["tau"].transpose("chain", "draw", ...).values
    events = [{"id": row["id"], "index": i, **marginal(dates[..., i])}
              for i, row in enumerate(rows)]
    return {"parameters": parameters, "events": events}
