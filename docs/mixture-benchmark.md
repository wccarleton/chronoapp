# Summary: Gaussian mixture

Load `docs/examples/density-benchmark.csv`, open **Summarize**, add a summary,
choose **Mixture**, and use **Add all** to include the 20 demonstration dates.
Set **Maximum modes** to 5, then **Fit mixture**. Progress, cancellation, and
logs use the existing app-wide monitor. The main plot retains pan/zoom, reset,
SVG, PNG, and vector PDF exports. Settings and event snapshots save in projects;
the latest successful plot-ready result per summary is also saved. Raw chains
and full text logs are not embedded. The single-density model remains available.

**Maximum modes sets the maximum complexity available to the density model.
The model estimates weights for all available Gaussian components and can give
unnecessary components negligible weight. The displayed density is the quantity
of interest; individual mixture components should not automatically be interpreted
as archaeological groups or phases.**

The main curve is the posterior mean mixture density with a pointwise 95%
credible band. Small translucent event-date marginals are conditioned on that
model and scaled by peak height for display only. Components are not drawn.
An optional diagnostics disclosure shows mean component weights and the fraction
of draws where each weight is below 0.05; these are not inferred group counts.

## Engine boundary and defaults

Model construction, measurement likelihoods, priors, sampling, and evaluation
are in Chronologer's `density.py`. Public functions:
`build_gaussian_mixture`, `fit_gaussian_mixture`, `evaluate_mixture_density`.
ChronoApp converts event records to existing distribution objects and serializes
returned arrays; it does not construct a PyMC model.

The app supports BP1950 normal, uniform, and radiocarbon measurements. It negates
BP ages into the existing increasing negative-BP calendar coordinate. Other
datums/families fail explicitly. Radiocarbon inputs must share one curve because
the existing distribution's curve cache is class-wide. No curve-cache, IPPP,
Phase, calibration, or existing single-density model changes are made.

Defaults: C=mean measurement centres, S=max(range of centres, median measurement
SD); ordered means Normal(C,S), scales LogNormal(log(0.2*S),0.75), symmetric
weights Dirichlet(0.3). These are empirical data-scaled hyperpriors, not neutral
priors. Engine callers can override C/S. PyMC NUTS uses two chains, 250 tune and
250 draws, one core, `adapt_diag`, target acceptance 0.95, seed 912. The app's only
mixture setting is K_max (1–20); no prior/sampler controls are added to the UI.

The requested-grid evaluator computes actual mixture PDFs for every draw and
never renormalizes cropped grids. The default 2,048-point grid spans all retained
component means +/- six SDs. This wide domain includes uncertainty in components
with small weights. Zoom is available for inspecting the dates more closely.

## Verification

Engine tests cover K=1/2/5 construction, finite logp/gradients, NUTS, strict mean
ordering, normalized weights, exact weighted-PDF evaluation, nonnegativity and
approximate integral one. Measurement likelihoods and gradients are compared
against existing radiocarbon and SciPy distributions. App tests cover a real
spawned worker, JSON serialization, and unsupported-input validation.

`scripts/check_mixture_browser.py` performs the 20-event/K=5 workflow with real
inference and real exports, saving a screenshot and result JSON in `docs/`.
Short execution tests and this benchmark are not convergence evidence.

### Recorded benchmark (2026-10-01)

20 synthetic radiocarbon events, K_max=5, 2 chains × 250 retained draws after
250 tuning draws per chain: **114.01 seconds**, **0 divergences**. Some samples
reached maximum tree depth. Convergence/ESS were not assessed; ordering does not
remove the weak identification of overlapping or low-weight components.

Derived defaults: C=-2670.6498, S=418.7561 years (negative-BP coordinates).
Mean weights in ascending mean order: **0.147, 0.275, 0.280, 0.207, 0.091**.
Fractions below weight 0.05: **0.666, 0.422, 0.302, 0.390, 0.646**.
Components are frequently downweighted, particularly the outer two; none is
consistently empty, and there is no defensible inferred group count from this
short fit. Wide weight intervals are retained in the result JSON.

The evaluated mean-density integral was **1.0000000012**. The default grid
includes long low-weight tails (approximately -12,583 to +7,553 in negative-BP
coordinates); use the existing view controls to inspect the date region.
Real SVG/PNG/vector-PDF exports passed, including checking that PDF/SVG contain
vector objects rather than embedded raster charts. Project settings roundtrip
and changes to K_max invalidate stale displayed results.

Complete engine suite: **44 passed, 9 warnings in 44.96 s** (PyTensor loop-fusion
warnings). Complete app suite: **79 passed, 1 warning in 31.77 s** (existing
Starlette HTTPX deprecation). `pip check`: **No broken requirements found**.
Runtime also reports the environment's existing unavailable C++ compiler warning;
no compiler, backend, or dependencies were added.

Existing browser regressions also passed: Project save/load, shared event tables,
calibration, Phase/Summary state, mobile/dark layouts, and the single-density
fit with all three export formats. Its original short fixture still reports nine
divergences, as before this change.
