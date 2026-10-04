# Project files (format version 1)

The **Project** tab provides New Project, Open, Save, Save As, and Import CSV.
**Load CSV** in Calibration imports the same shared dataset. Open/Save uses
native OS dialogs launched by the local Python app, independently of browser
file permissions. Users choose the location; Save reuses it and the UI displays
the path. CSV import uses a standard HTML file chooser.
The optional **Open copy** / **Download copy** pair under **Import / export a copy**
remains available. Open copy reads a standard file-input `File`, submits its
bytes to the same archive decoder, and replaces the project only after validation.
It does not retain a writable handle. Download copy remains a user-initiated
download, with no assumption that the browser completed saving it.

## Contents

A `.chrono` file is one ZIP archive containing:

```text
project.json
data/events.json
data/phases.json      # optional ordered phase specifications (UI prototype)
data/summaries.json   # optional summary specifications and input snapshots
data/source.csv       # optional original UTF-8 CSV, including BOM/newlines
data/source.json      # optional original source filename, paired with source.csv
```

`project.json` contains `format_version: 1`, `project_name`,
`chronoapp_version`, `chronologer_version`, `created_at`, `modified_at`, and
`active_dataset: "events"`. Timestamps include their timezone. Metadata and
event records round-trip without being reconstructed from the source CSV.

`data/events.json` is a list of event-time observations, for example:

```json
[
  {
    "id": "A1",
    "label": "Context A",
    "datum": "BP1950",
    "include_in_calibration": true,
    "distribution": "calrcarbon",
    "parameters": {
      "c14_mean": 1045,
      "c14_err": 25,
      "curve": "intcal20"
    }
  }
]
```

Radiocarbon means use the UI's conventional BP sign convention, not the
engine's negative-BP coordinates. The existing calibration API converts signs
when evaluating the engine. No distribution objects are instantiated on load.
Other distribution identifiers with JSON parameter objects are preserved as
data; this pass supplies no evaluator or CSV parser for those types.

Event metadata fields `label`, `datum`, and `include_in_calibration` are optional
for backward compatibility. Missing fields mean an empty label, BP1950, and
inclusion enabled. Labels allow up to 120 characters including an empty string;
datum is BP1950 or BCAD; inclusion is a JSON boolean. Old records roundtrip
without injecting new fields. New UI events explicitly store BP1950.

The master table edits the shared event list; Calibration displays only
`calrcarbon` rows and preserves all other events and metadata when editing or
removing a displayed row. Array position identifies a row internally, so editable
or duplicate IDs do not cause another event to be overwritten. Calibration
requests include only checked radiocarbon events; unchecking changes neither
the measurement nor the independent Summary input snapshots.

p1–p3 are presentation slots, not new serialized parameter keys: radiocarbon
uses `c14_mean`, `c14_err`, with `curve` in its own column. New Normal records
use `mean`/`sd`; Uniform uses `lower`/`upper`. Other imported records retain
their existing key order and names. Extra parameters beyond the first three
are preserved and noted; structured/string values are shown read-only. Changing
a distribution explicitly clears its parameters after confirmation. Datum
changes only metadata and labels, never numeric values; current calibration
still uses conventional radiocarbon BP and calendar BP1950. Other input-model
evaluators and BCAD conversions are outside this change.

Unknown project versions, malformed archives, extra/duplicate archive entries,
invalid event fields, and oversized input are rejected. Limits are 10,000 project events
and 64 MiB for a project request/document or the archive's expanded contents;
CSV import is limited to 16 MiB. Archives
are read in memory, never extracted. Only JSON and CSV are used: no pickle,
executable model objects, compiler caches, or application-installation writes.

## Phase prototype

The optional `phases` list is stored in `data/phases.json` without changing
format version 1. Existing files without this entry load unchanged. Each spec
contains a stable UUID-based `id`, editable `label`, `distribution` (`uniform`
or `normal`), contiguous zero-based `order`, and a reserved JSON `parameters`
object. IDs must be unique. Up to 100 phases are supported. List position and
order must agree; pixel positions are never serialized.

`frontend/js/phase.js` renders schematic vertical density profiles and handles
drag ordering. The profile registry is the renderer extension point;
`projectState.setPhases()` is the semantic state boundary for a future
Chronologer translation layer. It does not invoke the engine. Saved order remains
oldest-first; the canvas displays it bottom-to-top so older is deeper. This also
preserves the meaning of existing saved phases. There are no inferred boundaries, durations, overlap
constraints, or event membership. Escape cancels dragging, and focused grips
support arrow-key ordering. Project New/Open replaces phases; CSV imports keep
them. Saving and reopening preserves IDs, names, distributions, and order.

Verification: **55 app tests passed, 1 existing Starlette warning in 13.84s**.
The browser acceptance check added three phases, renamed them Early/Late/Middle,
changed Middle to Normal and verified its graphic, dragged the third block
between the first and second using actual pointer events, verified visual and
semantic order, and saved/reopened with identical specs. The current check also
verifies the reversed canvas, up/down keyboard movement, and the Depth preview tab.
Existing project/calibration checks and mobile/dark layout checks also passed.

## CSV schema

UTF-8, comma-separated, one header row; exact accepted columns:

| Column | Meaning |
|---|---|
| `id` | Nonempty sample/event label, at most 120 characters |
| `c14_mean` | Finite conventional radiocarbon age BP |
| `c14_err` | Finite laboratory standard deviation greater than zero |
| `curve` | Optional engine-recognized curve identifier |
| `label` | Optional grouping label, up to 120 characters; may be blank |
| `datum` | Optional BP1950 or BCAD; missing/blank defaults to BP1950 |
| `include_in_calibration` | Optional true/false; missing/blank defaults to true |

Column order may vary; quoting and UTF-8 BOM are supported. Duplicate headers,
extra columns, wrong column counts, invalid numbers, and empty datasets fail
with useful errors. If `curve` is absent or blank, the caller must supply the
current Calibration curve selection. There is no hard-coded fallback curve.
IDs are preserved, including duplicate labels supported by the current UI.

Import replaces the current dataset after confirmation, retains project name
and file location, stores the original CSV for provenance, and marks the project
dirty. Editing the table changes the canonical events, not the embedded source.

## State, API, and saving

`frontend/js/project-state.js` owns metadata, events, provenance, the current
file handle, modification state, and revision. It is independent of tabs.
Calibration edits update this state; project replacement repopulates Calibration
and clears old results. Incomplete table edits stay dirty and cannot be saved
until their event values validate. Plot views and derived calibration results
are not persisted; recalibrate after opening. Theme remains a user preference.

Python serialization functions in `chronologer_app.projects`:

- `new_project()`
- `import_csv(content, filename, default_curve=None)`
- `validate_project(project)`
- `dump_project(project) -> bytes`
- `load_project(content) -> project`

Stateless API endpoints:

- `GET /api/projects/new`
- `POST /api/projects/import-csv?filename=...&default_curve=...` (raw CSV)
- `POST /api/projects/encode` (JSON document -> ZIP bytes)
- `POST /api/projects/decode` (ZIP bytes -> JSON document)

Native file access uses `GET /api/projects/files/session`, `POST
/api/projects/files/open`, and `POST /api/projects/files/save`. Local-host and
same-origin checks plus a per-process request token protect these operations.
Paths come only from the native chooser; clients send opaque issued references,
never arbitrary filesystem paths. Dialogs run in a separate Tk helper process.
Tk/Tcl must be included when packaging the local app, which must run in an
interactive desktop session. A custom desktop UI is not required.

Save validates before opening a dialog, stages a temporary file beside the
destination, flushes it, checks for external modifications, and uses `os.replace`.
Failed writes retain dirty state; temporary files are cleaned up. This detects
ordinary external edits but does not lock out other programs during replacement.
Save without a reference invokes Save As. References last for the server session;
after a restart Save As selects the file again. Discard
prompts protect New/Open, and closing a dirty page triggers the browser's normal
unsaved-changes prompt. No autosave or persistent handle registry is added.

## Verification and current boundary

The integration test `test_csv_save_clear_reopen_benchmark` launches the app
through TestClient, imports three observations, saves `example.chrono` in a
temporary user-style directory outside the app, ends the session, then opens
the file through a fresh session. All metadata, event records, and provenance
must match exactly. Other tests cover malformed CSV, unsupported versions,
archive entries, generic event records, and incomplete drafts.

A browser check additionally exercises CSV -> table -> calibration -> Save ->
New -> Open, table edits followed by Save to the same file, Save As, cancelled
discard, external modification protection, invalid import, and a fresh page
reopening the file. It substitutes native picker selection only and exercises
real local API and disk IO with browser filesystem pickers deliberately blocked.
`scripts/check_native_dialog.py` separately automates actual Windows Open, Save,
and Cancel dialogs. Mobile layout and dark mode are also checked.

Current validation: **76 passed, 1 warning in 22.18 seconds** with
`conda run --no-capture-output -n chronoapp python -B -m pytest -q`.
The warning is the pre-existing Starlette HTTPX deprecation. The optional
Windows/Chrome browser check is retained in `scripts/check_project_browser.py`;
run it from the repository root with `websockets` available. It starts an isolated
local test server. `tests/test_project_files.py` additionally checks failed atomic
replacement, cancellation, stale references, and access protection. A sample CSV
is in `docs/examples/radiocarbon.csv`.

Implementation files: `src/chronologer_app/projects.py`,
`src/chronologer_app/api/projects.py`, `src/chronologer_app/main.py`,
`frontend/js/project-state.js`, `frontend/js/project.js`,
`frontend/js/app.js`, `frontend/js/calibrate.js`, `frontend/js/plots.js`,
`frontend/index.html`, `frontend/css/app.css`, `tests/test_projects.py`,
`tests/test_app.py`, and `scripts/check_project_browser.py`. Documentation and
examples are in this file, `README.md`, `docs/examples/radiocarbon.csv`, and
`docs/screenshots/project-dark-mobile.png`. No Chronologer engine files changed.

Each radiocarbon event now has its own Curve selector in Calibration. Mixed-curve
CSV imports and projects populate those selectors directly; `parameters.curve`
already carries this information, so no file-format migration is needed.
The preview/default selector changes only new rows and CSV rows with a missing
curve. Known but uninstalled curves remain selected on imported events and
produce a useful validation error if calibration is requested. App-side batches
use a separate fresh engine worker per curve, preserving input order and binding
each plot/export to its matching curve.

Summary uses saved copies from shared project state, rather than Calibration's
DOM or derived plot arrays. Single-density and Gaussian mixture inference accept BP1950 normal,
uniform, and radiocarbon events; each radiocarbon input uses its selected installed
curve through the distribution's spline references. New single-density fits use
the same measurement adapter as mixtures, with common explicit calendar bounds
and the existing location/scale hyperpriors. The legacy `/density` endpoints
remain radiocarbon-only and retain their original likelihood and shared-curve requirement.
Other distributions remain preserved in projects but cannot yet be fitted.
Arbitrary curves and calibration-curve mixtures are not implemented.

The Summarize prototype saves an optional `data/summaries.json` entry (root
`summaries` in the API document). Each specification has `id`, `label`, `model`
(`single_density` or `mixture`), `events`, and a reserved `parameters` object. Legacy
`density` specifications and their saved runs remain readable without rewriting
historical results; rerunning uses the new single-density adapter. These are
model-family intentions, not executable configurations or implicit priors.
The UI supports up to 100 summaries with up to 100 events each. Selected events
are independent copies of project event records, including their per-event curve;
dataset replacement or editing does not change existing summary inputs. Remove
and re-add events to refresh them. The picker searches the current dataset;
CSV loading uses the existing Project import flow. Density fitting now consumes
the snapshot through Chronologer's public API. Mixture fitting stores `K_max` in
the same parameters object and runs the engine's Gaussian mixture API.
Density `parameters` hold explicit conventional-cal-BP `older`, `younger`, and
`mean` values, plus `mean_sd` and `sd_scale` in years. Empty parameters show editable
starting suggestions; fitting records those visible settings before submitting.
Both models store sampling controls in `parameters.sampling` as
`{"draws":1000,"tune":1000,"chains":4,"cores":null}` by default for new summaries.
Null cores means Auto (minimum of chains, available CPUs and four); explicit positive
cores are capped by chains and available CPUs. Results record the resolved integer.
Legacy three-field sampling settings remain valid and appear with one core in the UI.
The run
snapshot records the same object and its result records the effective counts
plus the existing fixed seed. Saved run counts must match result metadata.
Editing counts hides stale results; Load saved run restores the recorded counts.
Older saved runs without this nested object use `result.sampling`; unsampled
legacy drafts use the new defaults. Null fields may be saved in unfinished drafts,
but execution requires integer counts (positive draws/chains, nonnegative tuning).
Each summary may also have `saved_run` with `id`, `created_at`, `model`, `events`,
`parameters`, and `result`. One latest successful run is retained per summary;
successful refits replace it. `result` is the existing plot response: density and
credible-band arrays, marginal histograms, warnings, diagnostics, timing, sampling
settings, and posterior structure metadata. New results also have optional `mcmc`
reports: schema version 1, scalar-variable metrics, per-chain sampler metrics,
method notes, package versions, and artifacts (`name`, `mime`, base64 `data`).
Artifacts include CSV/JSON diagnostics, paginated SVG traces with per-chain
histograms, a multipage vector PDF, and `messages.txt` captured before worker exit.
They are embedded in the saved result and compressed with the project archive;
no temporary paths or machine-local file references are needed on save/open.
No raw numerical chains or executable models are included. Reports preserve the
diagnostics calculated at fit time, not arbitrary future posterior calculations.
SVG previews use isolated image elements; saved markup is never inserted as HTML.
Old results without `mcmc` remain valid and show an explicit unavailable message.

Matching results load automatically when opening a project. Editing inputs hides
stale plots but retains the run; **Load saved run** restores its input snapshot
after confirmation. **Remove saved result** deletes its plot arrays from project
state; save again to persist deletion. New results mark the project dirty. Saving
while inference is running captures only the current retained result, so save
again after completion. The 64 MiB expanded-project limit applies;
the UI shows each result's uncompressed size. Archives use compact JSON arrays.

Original logs remain in `%LOCALAPPDATA%\\ChronoApp\\logs` (or `CHRONOAPP_LOG_DIR`).
They persist after closing, but the server's in-memory job index
does not survive restart. New saved runs also contain a portable messages snapshot.
The server
retains only bounded recent plot responses in memory; raw PyMC objects live only
in the worker and disappear when it exits. Existing unsaved session-only results
are not automatically migrated into saved runs.
Old projects without summaries continue to roundtrip unchanged.

Per-event curve validation: **48 app tests passed, 1 existing warning in
14.56 seconds**. A mixed-curve integration test uses two synthetic curves in
temporary, isolated worker caches and checks numerical differences, independent
single-curve parity, duplicate IDs, and restored row order. Browser checks pass
for mixed CSV import, per-row selection, unavailable-curve preservation, Save /
Open, default-preview independence, and calibration after changing a row's curve.

Project Open/Save no longer depend on browser File System Access APIs.

Process Lab stores an optional `processes` list in `data/processes.json`, using
the same input/saved-run structure with model `ippp_gp`. `parameters.older` and
`parameters.younger` are explicit observation dates in cal BP; incomplete drafts
can omit them but fitting and saved results require both. `grid_size` defaults
to 32 in the UI. Saved results contain `intensity` arrays (`t_values`, `rate_values`,
`lower_values`, `upper_values`), GP parameter/event marginals, MCMC artifacts and
the resolved observation/GP specification. Validation checks that intensity
endpoints and the saved specification match the run's declared dates. Existing
summary results and project archives remain unchanged.
