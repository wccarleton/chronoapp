# Roadmap

## Next: CSV column mapper

Keep the project event table as the canonical internal representation while
allowing users to import existing CSV layouts without reformatting them first.
Use one simple import dialog, rather than a multi-step wizard.

- Preview the CSV headers and first five data rows.
- Use dropdowns to map source columns to project event fields, including event
  ID, distribution, measurement parameters, calibration curve, datum, and label.
- Drop source columns that are not mapped; do not import them as extra metadata.
- Use explicit defaults for unmapped destination fields. Distribution defaults
  to **Radiocarbon**. Show the defaults so users can see the interpretation.
- Require mappings for essential measurement values; do not invent ages or
  uncertainties. Generate event IDs when an ID column is not mapped.
- Allow a fixed calibration curve or datum when those are not mapped columns.
- Support radiocarbon, normal calendar dates, and uniform calendar intervals.
  Mixed files can map a distribution column and the fields required by each type.
- Familiar headers may prefill mappings, but the preview must show the choices.
- Validate mapped rows before importing, with useful row-specific errors.
  Failed or cancelled imports must preserve current project edits.
- Keep scientific interpretation explicit: uncertainty is SD, and choosing a
  datum does not itself convert calendar coordinates.

Reuse the existing event validation and native file-open flow. The mapper
belongs in ChronoApp; no modelling-engine changes are expected. Keep the initial
checks small: radiocarbon compatibility, calendar/mixed mapping, discarded
columns and defaults, and preservation of edits after a failed import.

Defer remembered mappings, elaborate wizard steps, and additional import formats.
Initial effort estimate: roughly 20–40 minutes, including a few fast checks;
this is a planning estimate rather than a deadline.

## Larger inference selections and bulk event controls

Replace the hard 100-event inference selection limit with a non-blocking
computational resource warning. Retain the project's existing 10,000-event
capacity; selecting more than 100 events should not prevent adding or fitting.

- Keep individual event selection in **Add events from project**.
- Add **Add this page (N)** for the visible, filtered page and **Add all
  matching (N)** for all events matching the current filter across pages.
- Skip events already selected; button counts should reflect new additions.
- Show the selected event count. Above 100 selected events, display:
  > Large selection: fitting time and memory use increase with event count,
  > model complexity, draws, and chains. Consider starting with a smaller run.
- Remove the 100-event restriction consistently from the UI, inference request
  validation, and saved-summary validation, so there are no hidden limits.
- Preserve pagination, independent summary event snapshots, saved-run
  compatibility, and existing result invalidation when inputs change.

Keep checks small: filtered page/all selection, duplicate skipping, a selection
above 100 with a warning, and request/save compatibility without expensive fits.
This is planned work; the inference limit remains in place until implemented.

## Branch plan

Simulation is committed on `simulate` in both repos; Phase remains on its
separate `phase` branches. Do not merge experimental features solely to patch
the importer.

1. Create an `importer` branch from ChronoApp `main`.
2. Implement and check the mapper, then merge it into `main`.
3. Merge updated `main` into ChronoApp `simulate` and `phase`, resolving any
   small project-validation conflicts there.
4. Merge the experimental features into `main` separately when ready.

Prefer merging the shared `main` history into feature branches over
cherry-picking the importer patch. Chronologer needs no importer patch unless
implementation reveals an engine requirement.
