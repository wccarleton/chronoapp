# Process Lab GP IPPP

Add **+ Process** in Process Lab, choose project events (or import a CSV through
Project), and explicitly enter **Observation start · older cal BP** and
**Observation end · younger cal BP**. Both start blank and are required. Older
must exceed younger. Neither the UI nor API substitutes event extrema or
calibrated tails. At most 100 BP1950 radiocarbon, normal or uniform measurements
can be selected for this benchmark; the project database still supports 10,000.

The app calls `chronologer.models.ippp.gp` with negative-BP endpoints, existing
measurement distributions and the user's MCMC settings. The full point-process
likelihood includes empty time and the event count. It assumes complete observation
throughout the period; inferred intensity is events per year, not a demographic
estimate. A visible gloss explains these assumptions and the GP priors.

The GP models log intensity at 32 equally spaced nodes by default. Positive rates
are linearly interpolated between nodes and integrated using that same interpolation.
Grid nodes are editable (4–256); check resolution sensitivity. This approximation
is deliberately small for a first benchmark. No simulation, selection/detection
model, inferred observation boundaries or new backend is included.

Fit uses the existing isolated workers, global progress/cancellation/messages,
and shared sampling controls. The result shows four parameter marginals (baseline
log rate, amplitude, length scale and integrated intensity), a larger intensity
plot with pointwise 95% band and small height-scaled event-date posteriors, pan/zoom,
reset and SVG/PNG/vector-PDF export. The intensity is not area-normalized and its
initial plot domain is exactly the declared observation period. Changing a plot's
view does not change the scientific observation period.

MCMC diagnostics include all posterior variables, chain plots, downloadable reports
and messages. The JSON diagnostics artifact includes the resolved model specification.
Observation dates, grid size, sampling settings, inputs and the latest successful
result persist under the optional `processes` project list (`data/processes.json`).
Editing observation dates hides stale results. Load saved run restores the run's
explicit inputs; reopening a project restores plots without sampling. Removing a
saved result removes its artifacts from future saves. Existing projects remain valid.

API: `POST /api/ippp/jobs` accepts `events`, required `observation` containing
`older`/`younger` and optional `grid_size`, optional `sampling`, and optional `label`.
Job status/result/cancel/log endpoints are shared with Summary. Returned data uses
`model: "ippp_gp"`, `intensity.rate_values` (never `density.pdf_values`) and a
resolved `diagnostics` model specification. Scientific computation remains in
Chronologer; the app only validates, converts coordinates, orchestrates and renders.
