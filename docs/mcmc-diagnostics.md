# Saved MCMC diagnostics

New density and mixture fits produce these reports in the isolated inference worker,
after sampling and before the raw DataTree is released. Model definitions, priors,
likelihoods and sampler settings are unchanged. Expand **MCMC diagnostics & chain
plots** in the fitted Summary block. Every scalar posterior variable is included,
including event dates, latent radiocarbon values and mixture components. Indexed
event variables include the input event ID; indices distinguish duplicate IDs.

- Rank-normalized split R-hat (ArviZ, two or more chains), bulk ESS, tail ESS
  (minimum of 5th/95th percentile ESS), and MCSE for the mean and SD.
- Per-chain divergence counts, energy BFMI, observed maximum tree depth, number of
  transitions at the configured depth limit (when PyMC supplies it), and mean
  acceptance rate. Missing sampler statistics are NA.
- Per-chain Geweke Z: first floor(0.1*n) versus last floor(0.5*n) draws, using
  Bartlett/Newey-West spectral variance with bandwidth floor(segment_length^(1/3))
  and biased autocovariances. Each segment needs at least 20 draws; otherwise NA.
  This Python implementation differs from [coda's AR spectral estimator](https://search.r-project.org/CRAN/refmans/coda/html/spectrum0.ar.html),
  while testing the same early/late mean comparison described by
  [geweke.diag](https://search.r-project.org/CRAN/refmans/coda/html/geweke.diag.html).
  It is not claimed to reproduce coda numerically. R is not required.

Constant or stuck chains have unavailable R-hat/ESS/MCSE, never a reassuring zero.
Unavailable numerical values are JSON null, CSV empty cells and UI NA. All plots
use retained draws only; warmup is excluded. Calendar values retain the native
negative-BP coordinate, explicitly labelled in plots/notes. No thinning, smoothing
or scientific reparameterization is introduced. Traces and histograms have separate
colours for each chain. Four scalar variables appear per selectable page.

New app summaries default to 1,000 retained draws and 1,000 tuning iterations
per chain, with four chains. Users can edit the three counts in MCMC sampling;
reports use the actual requested counts and exclude tuning. Treat R-hat > 1.01, low ESS,
E-BFMI < 0.3, divergences, depth-limit transitions and poorly mixing traces as
investigation prompts. A Geweke flag can arise by chance, especially across many
variables; passing diagnostics does not prove convergence. The first Geweke segment
has only 25 draws in a legacy 250-draw benchmark, so its spectral estimate is
particularly noisy; it has 100 draws at the new 1,000-draw default.

Downloads include unrounded CSV and JSON metrics, methods/software versions and
input IDs in JSON, editable vector SVG pages, a multipage vector PDF, and a snapshot
of the worker's messages. The originals remain in the normal log directory. Reports
are kept in memory with the result until project save; the `.chrono` ZIP embeds them
in `data/summaries.json`, without a temporary directory to move or reconcile.
Opening the project reconstructs download links even after server restart. Browser
downloads let users place individual artifacts in a publication/debugging folder.
Removing a saved result removes its artifacts from subsequent project saves.

Raw numerical chain matrices are still not saved. Future diagnostics cannot be
recomputed from these reports. Pre-existing saved runs contain no chains from which
to reconstruct this information and require a new fit. Project size is bounded at
64 MiB expanded; CSV import allows 16 MiB and 10,000 database events. Each analysis
still supports up to 100 selected events. No new engine code or R dependency is
introduced by this feature.
