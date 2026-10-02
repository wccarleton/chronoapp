# Current status

## Working
- Project opens first; shared editable events, CSV import and per-event curves work.
- Projects support 10,000 events with paginated tables and searchable selectors.
- Native Open/Save and browser copy tools round-trip `.chrono` archives.
- Calibration has individual/stacked plots, overlays, pan/zoom and vector exports.
- Summary runs single-density and Gaussian-mixture models through Chronologer.
- Process Lab runs the new GP IPPP with mandatory older/younger observation dates.
- GP results include intensity uncertainty, event posteriors and parameter plots.
- Workers provide cross-tab progress, cancellation, logs and configurable MCMC counts.
- All models support parallel chains; Auto uses up to four CPUs per fit, with manual override.
- Progress sums interleaved chains; cancellation stops worker descendants on Windows.
- Expandable diagnostics include R-hat, ESS, MCSE, Python Geweke and chain plots.
- Saved runs restore plots/diagnostics without sampling; changed inputs hide stale plots.
- Phase is a saved, reorderable UI prototype; Depth remains a preview.

## In progress
- GP engine/API, Process Lab and parallel-chain settings are complete and ready for review.
- No implementation task is currently outstanding.
- Latest full suites: engine 78 passed (17 warnings), app 109 passed (1 warning).
- Browser checks passed real GP sampling, tab switching, save/load and SVG/PNG/PDF export.
- Browser checks also passed Auto/legacy cores settings and a saved/reopened parallel fit.
- Use Conda environment `chronoapp`; PyMC 6.3.2, PyTensor 3.3.2, ArviZ 1.3.0.

## Known limitations / issues
- No blocking failure remains in the tested GP workflow; smoke fits do not prove convergence.
- GP uses a finite grid and assumes complete observation; resolution needs scientific judgment.
- Process Lab accepts at most 100 supported BP1950 events per fit.
- Existing missing-g++/PyTensor performance and Starlette/httpx deprecation warnings remain.
- Restarting the server loses linked file handles; select the destination again with Save As.
- Two completed pre-restart results were backed up under ignored `.local/session-backups/`.

## Next task
- The requested GP IPPP benchmark is implemented and ready for user review.
- No subsequent scientific benchmark has been selected; do not infer a new roadmap.
- Details: `docs/ippp-gp-benchmark.md`; engine mathematics: `../chronologer/docs/ippp-gp.md`.
