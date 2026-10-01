# Local density benchmark

## Model and boundary

The existing common-bound truncated-normal radiocarbon hierarchy from
Chronologer's `tests/test_pymc_models.py` is now exposed by
`chronologer.build_radiocarbon_density(...)` and
`chronologer.fit_radiocarbon_density(...)`. There was no pre-existing callable
density-fit API: the model lived in tests/notebooks. This small engine module
packages the tested structure rather than constructing a model in ChronoApp.
A regression compares its logp and gradient numerically with the existing test
model at the same point. No pre-existing functions or interpolation code changed.

The hierarchy is:

- `tau_mu ~ TruncatedNormal(mean_prior, mean_prior_sd, lower, upper)`
- `tau_sd ~ HalfNormal(sd_prior_scale)`
- `tau[i] ~ TruncatedNormal(tau_mu, tau_sd, lower, upper)`
- `r_latent[i] ~ Normal(interpolated calibration mean, calibration error)`
- observed `r_measured[i] ~ Normal(r_latent[i], measurement error)`

This is the **shared-bound variant covered by the PyMC 6 tests**, not the
notebook's optional event-specific, calibration-derived truncation. Bounds and
prior parameters are explicit scientific inputs. UI starting suggestions are
5000–1 cal BP, centre prior 2500 cal BP with SD 500 years, population-SD
half-normal scale 400 years. Review them for each dataset. ChronoApp negates BP
ages/bounds/centre for the engine's negative-BP convention; scales are unchanged.
The endpoint rejects mixed curves. The engine validates bounds inside the curve
and excludes its final grid point, where the existing interpolator divides by
zero. It does not repair or extrapolate that helper.

The browser submits to `POST /api/density/jobs` and receives a run ID immediately.
The bounded local job service starts up to **two** isolated worker processes;
additional runs queue, with at most eight pending/running jobs. A full queue
returns 429. `POST /api/density` remains a synchronous compatibility endpoint
using the same service. Sampling settings and model semantics are unchanged.

Progress appears above the tabs, independent of the active workspace. Compilation
is indeterminate; sampling counts actual PyMC tuning + posterior draws across
both chains. It is a count of iterations, not a time-remaining estimate. Each
run offers Cancel, Messages and Download log. Only its own summary is locked;
other summaries, calibration, saving and tab navigation remain available. Changing
projects detaches the old result from the new document but does not silently
cancel the server job. CSV changes to the same project do not invalidate a
summary's independent input snapshot.

Cancel stops a queued job or terminates/reaps its spawned process. Orderly server
shutdown cancels jobs and joins workers. Closing a browser does not stop server
work; reloading reconnects the monitor, but does not reattach unsaved plots
to newly opened summaries. Saved projects now restore the latest plot-ready run
per summary without raw chains (see project-format.md). Job history/results are held in memory (up to 20
finished runs); server restart loses them. This is a single-server local queue,
not a durable or multi-server job system.

Python stdout/stderr, warnings, PyMC logging and tracebacks from each worker are
saved in `%LOCALAPPDATA%\ChronoApp\logs\density-<run-id>.log` on Windows. The app
shows the exact file path under Messages. The inline viewer displays the most
recent 64 KiB; Download log retrieves the whole file. `CHRONOAPP_LOG_DIR` can
override the directory. Logs persist after restart and are not automatically
deleted. Server/access logs and output emitted before the worker wrapper still
go to the launch terminal; browser JavaScript errors go to its developer console.

## Result and plot

`DensityFit.posterior` is PyMC 6's `xarray.DataTree`, with `posterior`,
`sample_stats`, and `observed_data` groups. Posterior variables include
`tau_mu`, `tau_sd`, `tau`, and `r_latent`; chain/draw dimensions are retained.
The raw object stays inside the worker. `DensityFit.density` evaluates the
truncated-normal population PDF for each posterior draw on 512 grid points;
it contains `t_values`, `pdf_values` (posterior mean), `lower_values` and
`upper_values` (pointwise 2.5/97.5 percentiles). This is not a KDE of event dates,
an event-date HDI, or a simultaneous credible band.

ChronoApp serializes the engine arrays unchanged, plus posterior structure,
sampling counts, timing, divergences and warnings. The frontend checks finite,
ordered arrays and draws them using the existing `InteractivePlot` and
`exportPlot` code. SVG/PDF retain paths and text; PNG uses the existing 3× scale.
No frontend statistical approximation or raw Python-object persistence is used.
Project files save the specification only. Changed inputs invalidate displayed
results; responses from a replaced project are discarded.

## Environment, defaults and validation

Validated in Conda `chronoapp`: Python 3.12.13, PyMC 6.3.2, PyTensor 3.3.2.
App metadata now explicitly requires Python >=3.12 and PyMC >=6.3.2,<7, with
PyTensor's compatible constraint supplied by PyMC (>=3.2.2,<3.4 here).
Reinstalled editable app metadata without changing the installed scientific stack.

Application sampling defaults are centralized in `api/density.py:SAMPLING`:
250 draws, 250 tuning steps, 2 chains, seed 912. The engine uses 1 core,
ordinary PyMC NUTS and `adapt_diag`, with progress display and automatic
convergence checks disabled. These are development execution defaults, not
scientifically validated sampling recommendations. UI and exports say so.

Actual Windows browser benchmark: CSV ages 2500, 2550, 2600 BP, errors 30 years,
IntCal20; calendar bounds 3500–1500 BP and the displayed default prior settings.
Worker fit/derivation timings were **8.269 s** on the first browser fit and
**4.741 s** on repetition. Both used existing compiler caches, so a clean cold
installation timing was not measured. Both short runs had **9 divergences**;
the UI and exports report them. No convergence claim is made or model/sampler
retuning performed to hide this diagnostic.

- Engine API targeted tests: **3 passed, 3 loop-fusion warnings, 6.55 s**.
- App endpoint targeted tests: **2 passed, 1 warning, 12.12 s**.
- Full Chronologer suite: **35 passed, 8 loop-fusion warnings, 22.31 s**.
- Full ChronoApp suite: **62 passed, 1 Starlette warning, 21.49 s**.
- `pip check`: **No broken requirements found**.
- `scripts/check_density_browser.py`: real CSV → UI → real inference → finite
  density/band → downloaded SVG, PNG and PDF passed. Verified SVG paths/no
  images, PNG signature, PDF signature/no image objects. Settings codec roundtrip
  and input-change invalidation also passed. Downloads are tested in a temporary
  directory; the screenshot is `docs/screenshots/density-benchmark.png`.

After background progress/logging and saving recovery were added: **64 app tests
passed, 1 existing warning in 23.89 s**; **35 engine tests passed, 8 existing
warnings in 21.00 s**. Real spawned-process tests cover two concurrent workers,
queuing, queue limits, running/queued cancellation, failures, log capture and
worker reuse. The real PyMC endpoint test covers callback progress and log
retrieval. Browser checks verify progress continuing on the Phase tab, live
messages and the existing vector/raster exports. Saving checks cover granted
permission without a redundant prompt, denied permission preserving old bytes
and dirty state, and a valid downloaded project archive. Native pickers and
permission responses are substituted in that check; the user's specific folder
restriction has not been reproduced.

Sampling tests use 8 draws/8 tune/1 chain. They check execution and structure,
not stochastic values or convergence. Existing missing-g++ and short-chain
notices remain; PyTensor loop-fusion warnings are nonfatal. The app suite's
Starlette warning concerns the older HTTPX TestClient integration.

## Distributable preparation: concrete remaining work

The Windows build script is a placeholder; no freezer configuration exists.
No packaging framework, compiler, nutpie, JAX or alternate sampler was added.

- Bundle the updated Chronologer source/API, Python runtime, PyMC, PyTensor,
  NumPy/SciPy/Pandas and their native libraries, ArviZ and its installed
  dependencies (including xarray's DataTree support), FastAPI/Uvicorn and their
  dependencies. Also retain PyMC's runtime dependencies such as cloudpickle,
  cachetools, rich and threadpoolctl. The installed PyMC metadata is authoritative.
- `pymc`, `pytensor.tensor`, and `chronologer.pymccarbon` are imported inside engine
  functions; Uvicorn resolves the app from a string and Windows workers import
  `chronologer_app.api.density`. A freezer must collect these modules, metadata,
  package resources, PyTensor compiled extensions/runtime source resources and
  scientific-library DLLs, then test the ordinary PyMC path in an isolated build.
  Dynamic imports do not imply a need to ship unused optional sampler backends.
- PyTensor's actual writable cache is under `%LOCALAPPDATA%\PyTensor\compiledir_*`.
  `pytensor.config.cxx` is empty on this machine. Ordinary PyMC succeeds anyway;
  do not add GCC based solely on its startup notice. Verify cache creation and
  compilation behavior without developer caches in a future packaged build.
- Chronologer's curve loader currently uses `calibration_curves` inside its
  installed package, creates that directory on import, and downloads missing
  curves there. Ship validated curve files and resolve that writable-path
  assumption for a read-only/frozen installation. The app currently requires a
  locally installed curve before fitting; it does not trigger a download.
- Windows spawned workers need a freezer-compatible executable entry point
  and `multiprocessing.freeze_support()` when an executable is introduced.
  Browser assets, bundled export fonts, jsPDF and svg2pdf must also ship.
- Today both packages are editable installs in `chronoapp`; the new density API
  is not available in an older released Chronologer merely bearing version 0.2.0.
  A distributable must bundle this updated engine revision. No global Python
  installation is used. Chrome and `websockets` are browser-test tools, not
  density inference dependencies; a packaged browser/webview remains future work.
