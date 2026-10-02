# Chronologer App

Local browser interface for the sibling `chronologer` scientific package.

Density fits show the posterior mean model density with its pointwise 95%
credible band, plus model-conditioned event-date marginal histograms on the same
calendar axis. Each event is transparently peak-scaled to 20% of the model
curve peak for display only. Separate compact, exportable panels show the
posterior marginals of the normal location and scale parameters. These are not
necessarily the actual mean and SD after truncation. Marginals use retained-draw
histograms; the scientific model, priors, and sampling settings are unchanged.
The **Phase** tab is an interactive UI prototype: add named Uniform or Gaussian
phases and drag their grips vertically to reorder them (or use arrow keys on a
focused grip). Older phases appear at the bottom; saved semantic order remains
oldest-first. **Depth** is a preview tab for future age–depth modelling.
Density graphics are schematic;
block height and spacing do not define durations or gaps. Phase specifications
are saved with the project; no phase inference or event membership is applied.

The **Project** tab manages single-file `.chrono` documents: New, Open, Save,
Save As, and Import CSV. **Load CSV** in Calibration fills the determination
table from `id,c14_mean,c14_err` and optional `curve` columns. The local Python app
provides native Open/Save dialogs and file access, independently of browser file
permissions (including embedded browsers). Save reuses the selected path;
Save As chooses a new one. See
[project format and workflow](docs/project-format.md) for the schema, API,
provenance, supported limits, and round-trip benchmark.

Under **Import / export a copy**, **Download copy** exports a `.chrono` archive through
the browser's download mechanism. It leaves the linked file and dirty indicator
unchanged because download completion cannot be confirmed by the app. Save As
can choose a different writable location; denied writes preserve current edits.
**Open copy** reads a `.chrono` file using a standard file-upload control, without
requesting File System Access handles or write permissions. These are optional
copy tools; ordinary Open/Save work through the local app in every browser.
Opening validates the complete archive before replacing the current project;
failed reads leave current data intact. Copies have no linked save-back file.

Native dialogs require Python's Tk support (included in the `chronoapp` environment).
A future packaged browser-UI distribution must bundle Tk/Tcl and run the local
service in the user's interactive desktop session. No custom desktop UI is needed.
Project saves use a temporary file beside the destination followed by an atomic
replace; detected external edits are not overwritten. File references live for
the local server session; after restarting it, use Save As to select the file again.

Each determination has its own **Curve** selector, stored as that event's
`parameters.curve` in the project. Mixed-curve CSVs and projects populate those
selectors without replacing individual choices. **Curve preview / default for
new rows** controls the standalone curve preview and fills missing CSV curves
or new rows only. Uninstalled curve choices are preserved on import/open, but
cannot be calibrated until available. Custom curve imports and calibration-curve
mixtures are not implemented; Summary's Gaussian mixture is a separate event-time model.

Project contains the editable master event table: Event ID, Label, Datum,
Distribution, p1/p2/p3, and Curve. Parameter slots show their actual names;
saved data retains those names. Edits to radiocarbon dates or curves in Project
and Calibration update both views immediately. Calibration filters out other
event distributions and its independent round checkboxes select which dates to
calibrate (on by default). Excluded dates remain saved in the project.

Datum choices are **BP1950** (default) and **BCAD**. This is stored metadata;
changing it does not convert parameter values or change current radiocarbon
measurement/plot conventions. Normal and Uniform records can be entered for
future modelling; they are not sent to the calibration engine. Optional labels
are saved for future grouping/phase work. CSV imports also accept `label`, `datum`,
and `include_in_calibration` (`true`/`false`) alongside the existing columns.

Calibrate one or many radiocarbon determinations, inspect separate result plots,
and view the selected calibration curve. **Process Lab** now runs the basic
[GP IPPP benchmark](docs/ippp-gp-benchmark.md): choose events and explicitly declare
observation start/end (cal BP). Both dates are required and start blank. The model
returns event intensity, not a normalized density, with parameter/event posteriors,
MCMC diagnostics, vector exports and saved results. Simulation remains future work.
The determination table has a bounded height and scrolls internally, with sticky
column headings. Adding rows keeps the controls below the table in place and
scrolls the new row into view.

## Structure

- `src/chronologer_app/`: Python application, API, and services.
- `frontend/`: HTML, CSS, and JavaScript frontend.
- `tests/`: API/engine parity, validation, and application tests.
- `scripts/build_windows.ps1`: Placeholder for the Windows build script.

## Development

Requires Python 3.12 or newer. Use the existing Conda development environment.
From the project root, install the sibling engine and the application:

```powershell
conda activate chronoapp
python -m pip install -e ../chronologer
python -m pip install -e ".[dev]"
python -m chronologer_app.main
```

Open **http://127.0.0.1:8000**. Stop the server with Ctrl+C.
The module launch also works without reinstalling the editable application after
source changes. The `chronologer-app` command is available after installation.

## Plot navigation

The **Summarize** tab can fit the tested single truncated-normal radiocarbon
hierarchy through `chronologer.models.density.single`. Mixtures call
`chronologer.models.density.gmixture` directly. Both pass scientific `params`
separately from `mcmc_config`; the app does not use the optional `chronologer.fit`
delegator. This API organization leaves the models and result structures unchanged.
Add project events,
choose Density, review the calendar bounds and prior settings, and select
**Fit density**. This benchmark requires one shared, locally installed curve.
It runs ordinary PyMC NUTS in a Windows-compatible worker and displays the
posterior mean model density and pointwise 95% credible band. The same
pan/zoom/reset and SVG/PNG/vector-PDF exports are available. Both Summary models
have an expandable **MCMC sampling** section: retained draws per chain,
burn-in/tuning per chain, and number of chains. New summaries start at
1,000 draws + 1,000 tuning iterations per chain, with 4 chains. Only change these
if you understand MCMC sampling; the controls explain reliability, runtime,
memory and report-size consequences. Tuning adapts the sampler and is discarded;
it is not an additional trim of retained draws. Counts must be whole numbers
(draws/chains positive, tuning nonnegative). One chain cannot provide between-chain
R-hat. **Parallel chains / CPU cores** accepts a positive integer or blank for Auto
(up to four, limited by chains and available CPUs). Set 1 for sequential chains.
The limit is per fit; concurrent fits share CPU and memory. Settings persist with the
summary and each run, and edits invalidate the displayed result. Legacy saved
runs retain their recorded counts. Seed and other engine settings are unchanged.
Short-run warnings
are displayed. Expand **MCMC diagnostics & chain plots** for rank-normalized
R-hat, bulk/tail ESS, MCSE, Python Geweke Z, divergences, E-BFMI, tree depth,
acceptance rates and trace/histogram pages for every retained variable.
Download CSV/JSON reports, vector SVG/PDF plots and the run's messages.
Geweke uses Bartlett spectral variance, not coda's AR estimator; its method and
limitations appear in the report. These diagnostics do not certify convergence.
Save the project to retain the latest
successful plot-ready result per summary, including its input snapshot, warnings,
and diagnostics. Reopening restores matching plots without inference. **Load saved
run** restores a retained run's inputs after edits; **Remove saved result** removes
its arrays while keeping current settings/events. Successful reruns replace the
retained result. New runs embed their reports, vector plots and worker message
snapshot in the project, so downloads still work after reopening or server restart.
Raw numerical PyMC chains are not embedded. Older runs must be rerun to obtain
diagnostics. Projects support up to 10,000 events and 64 MiB expanded (CSV import
is limited to 16 MiB). Project and Calibration tables and the Summary picker show
100 events per page, with all events retained in project state. Calibration
Include all / Exclude all applies across pages; selected events on other pages
remain included. Analysis runs still support 100 selected events: rendering all
calibration plots and generating Bayesian per-event diagnostics have separate
scaling costs. This does not restrict database import, editing or saving.
An app-wide monitor above the tabs shows real tuning/sampling progress and
indeterminate compilation. Up to two isolated fits run concurrently; further
runs queue. Other workspaces remain usable. Cancel, Messages and Download log
are available per run. Worker logs live in `%LOCALAPPDATA%\ChronoApp\logs`;
ordinary server logs remain in the launch terminal.
Mixture fitting is available with **Maximum modes** as its only setting; see
[mixture workflow and priors](docs/mixture-benchmark.md). See [density benchmark](docs/density-benchmark.md)
for defaults, validation results and distributable requirements.

The results block has **Individual plots** and **Stacked plot** tabs. The
individual sample headings can be clicked or activated with Enter/Space to
collapse or expand their plots. **Collapse all / Expand all** in **Shared calendar
domain** controls every individual plot without resetting its view or layers.
Collapsed headings show the sample name,
uncalibrated mean ± SD, calibrated mean, and every 95% HDI interval. Expanded
plots show the calibrated summary below the controls and above the chart.
Summaries remain fixed when navigating the plot and are included in exports.
Radiocarbon measurements and related labels use ochre in both themes.

The individual list scrolls within a bounded height. The stacked view orders results
by the engine's weighted posterior mean, oldest at the top, with a vertical
offset and equal peak height for every density. This scaling is for display
only; it does not modify engine arrays or compare probability masses.

The stack initially spans the oldest to youngest returned tails (after the
engine's density cutoff), independently of the shared individual domain. It has
its own domain controls, pan/zoom, reset, and SVG/PNG/vector PDF export.
**Expand rows** increases vertical spacing without changing the calendar domain;
drag vertically to inspect other rows. **Fit all data** restores all tails and
rows. Labels thin out when crowded; zoom vertically to reveal them.

- Drag a plot to pan both axes. Scroll over it to zoom around the pointer, or use
  two fingers to pinch and pan on a touch surface. The +/− buttons also zoom.
- Set **Older cal BP** and **Younger cal BP** in **Shared calendar domain**, then
  **Apply to all**, to set every determination's starting view. Older must be
  greater than Younger. This also replaces existing per-sample domain overrides.
  A global setting entered before calibration is used for the results.
- Each determination has its own domain inputs. **Apply** sets that plot's
  domain; **Use global** returns it to the shared setting.
- **Reset view** restores the plot's configured domain and initial vertical
  range. **Reset all views** does this for all determinations and the curve.
  **Auto domain** fits all returned determination data and clears overrides.
- The curve can be navigated independently and has its own domain inputs.
- Focus a plot with Tab: arrow keys pan, +/− zoom, and Home resets. Views survive
  resizing and switching tabs. A new calibration starts new views using the
  current global domain; per-sample overrides are cleared.

These are display limits only: they do not change engine grids, probabilities,
normalization, or calibration requests. Zooming cannot add detail beyond the
returned data. Plot gestures capture touch movement inside the plot; scroll the
page from outside the plot area.

## Curve overlay and figure export

Individual plots also offer **Density + uncalibrated** and
**Density + curve + uncalibrated**. The uncalibrated Gaussian uses the submitted
radiocarbon age and laboratory error (1σ). It extends leftward from the right
axis, with radiocarbon age increasing upwards, and shares the curve's ochre
styling and radiocarbon scale. Its horizontal width is scaled for visibility;
it does not represent calendar time. Initial limits include ±4.5σ, plus the
curve when selected. Vertical pan/zoom moves both layers on the shared right
axis; the Gaussian stays attached to that axis when panning horizontally.
SVG, PNG, and vector PDF exports include the selected layers and legend.
These options apply only to individual plots.

Each determination offers **Density only / Density + curve**. The overlay shows
the matching calibration curve's mean and ±1σ ribbon behind the calibration
output. Calendar age is shared; the left axis shows calibration output and the
right axis shows radiocarbon age BP. Their vertical units are independent. Both
axes follow pan/zoom gestures; reset restores their initial view. Each result
keeps the curve associated with its calibration, even if the workspace selector
is subsequently changed.

Select a format and press **Export** beside a determination or the curve plot:

- **SVG** preserves paths, clipping, groups, and editable text, with embedded
  DejaVu Sans fonts.
- **PDF** preserves vector paths and text, with embedded font subsets. It is
  generated directly from the SVG scene, not from a screenshot.
- **PNG** rasterizes the figure at three times its displayed SVG dimensions.

Exports capture the current plot limits and selected layers, including sample
ID, measurement, curve name, axis labels, and an overlay legend where applicable.
They use a white background independently of the application theme. Editing text
in another application may require installing DejaVu Sans if that editor does
not support embedded fonts; text is not converted into outlines.

Export happens locally in the browser. PDF libraries and fonts are bundled in
`frontend/vendor/` with licenses and a provenance manifest; no CDN, Node tooling,
or additional Python packages are needed. See `frontend/vendor/README.md`.

FastAPI and Uvicorn are runtime dependencies. The `dev` extra adds pytest and
HTTPX for API tests. No Node, frontend build, or internet-hosted assets are needed.
Conda is only the development environment; application packaging is out of scope.

```powershell
python -m pytest -q
```

## Scientific boundary and current limitations

- All calibration is performed by the existing `chronologer.calibrate` function.
  The API converts conventional BP input to the engine's negative-BP convention.
  Returned calendar and calibration arrays are serialized unchanged.
- The browser displays positive cal BP labels, older at left, with AD 1950 as the
  reference. Individual plots preserve engine values. Stacked plots scale each
  density to its maximum for shape comparison. The engine mean uses
  `sum(t * weights) / sum(weights)` and is passed through as `posterior_mean`
  for ordering. The engine also supplies the 95% HDI, computed from relative
  retained grid weights with the original grid spacing used to identify gaps.
  The cutoff includes its crossing cell and density ties; discrete coverage
  can therefore exceed 95%. Interval endpoints are inclusive grid-node ages,
  displayed to one decimal year. Calibrated standard deviation remains omitted
  pending scientific review.
- Single and multiple dates use the same endpoint and engine batch call. Plots
  initially share calendar and vertical scales, and break at gaps trimmed by the
  engine. Plot controls can subsequently change each view independently.
- Calibration requests are grouped by each determination's curve. Each group
  continues to run in its own fresh Python worker process. Engine distributions
  now retain their own references to shared, per-curve splines. Results retain
  input order and their curve identity; overlays and exports use that curve.
  Worker startup adds overhead for each distinct curve.
- The curve catalog is read from the engine registry. Only locally installed
  curves are enabled; the application does not download or modify engine data.
  This checkout currently includes IntCal20. Other recognized curves appear as
  unavailable until installed through the engine. Registry/cache access is
  isolated in `api/calibration.py` because the engine has no public discovery API.
- The curve panel shows supplied curve points and ±1σ uncertainty, zoomed to the
  result range after calibration. It does not reproduce the engine's spline.
- Edits mark results as stale; requests whose inputs changed while running are
  discarded. Requests support up to 100 determinations.

The API exposes `GET /api/curves`, `GET /api/curves/{name}`, and
`POST /api/calibrate`. A calibration request has this shape:

```json
{"determinations":[{"id":"Sample 1","age":3240,"error":25,"curve":"intcal20"}]}
```

The previous request-level `curve` remains an optional fallback for API clients;
an explicit determination-level `curve` takes precedence. Responses contain
each result's `curve`, a distinct `curves` list, and the legacy top-level `curve`
(the shared name for a single curve, otherwise `null`).

## License

A license has not yet been selected. See `LICENSE`.
