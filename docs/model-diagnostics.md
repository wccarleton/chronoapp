# Model diagnostics

Summary (single density and mixture) and Process Lab (GP IPPP) report WAIC
on the deviance scale, ELPD WAIC on the log scale, effective parameter count
(p WAIC), predictive-unit standard error where available, and retained-draw
and event counts. A reliability warning flags log-likelihood variance above
0.4 in any predictive unit. These are predictive assessments, separate from
the existing convergence diagnostics. No cross-tab comparisons are assumed.

The interface explains that WAIC assesses prediction of observed dating
measurements, including radiocarbon determinations, rather than directly
assessing prediction of unknown true event calendar dates. Comparisons require
the same observations and predictive units. IPPP additionally assesses the
event count over the declared observation window.

Chronologer's `model_diagnostics` module computes scores after sampling from
retained posterior parameter draws. Adaptive quadrature integrates out event
dates against the original normal, uniform or radiocarbon measurement
likelihood. Radiocarbon uses each event's curve and combines measurement and
curve uncertainty; the likelihood is not normalized into a calibrated PDF.
Single-density scoring retains its fitted truncation bounds; mixtures retain
all weights and components. No priors, sampling settings or fit return types
change. Numerical failures and insufficient draws produce an unavailable
reason rather than preventing access to the fitted result.

IPPP uses one predictive unit: the complete declared observation window.
For every draw its likelihood is the product of measurement-integrated
intensities multiplied by exp(-integrated intensity). The integral uses the
fitted piecewise-linear grid across the full window, preserving the count
likelihood. The score does not condition on event count or normalize intensity.
With one window, between-unit standard error is unavailable and predictive
interpretation is limited. It is not an event-level leave-one-out score.

Saved runs contain compact estimates and notes, plus a downloadable
`model-diagnostics.json` in the MCMC artifacts. Old saved runs load normally
and show an unavailable message. Prior simulations do not receive these scores.
Phase branch diagnostics remain on their own branches; this change does not
merge Phase or its inference into main. Their eventual integration can reuse
the renderer, with compatibility for their existing score schema.

Validation uses synthetic posterior arrays, analytic measurement-integral
checks, mocked worker fits, archive round-trips and a headless browser fixture.
No MCMC runs were performed. Actual fits and scientific sensitivity checks
remain for user testing. Quadrature adds post-fit work, particularly for
radiocarbon observations, and may report unavailable for extreme numerical
scales.
