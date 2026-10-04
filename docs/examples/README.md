# Example data

## Two-phase example

`two-phases.csv` contains six illustrative radiocarbon measurements using
IntCal20: three labelled **A** (older) and three labelled **B** (younger).
These are made-up observations for trying the phase workflow, not real
archaeological data or simulated draws from a fitted phase model.

Import it through **Project → Import CSV**. In **Phase**, add a card named **A**
with a **Uniform** distribution and a card named **B** with **Gaussian / Normal**.
Place A below B on the canvas and leave **Apply oldest-to-youngest order** enabled.
The labels assign all three dates to their matching phase automatically.

For center-to-center ordering, leave each card's sole anchor at **0.5**. To try
end-to-start ordering, set A's older/younger anchors to **0 / 1**, and B's to
**0.05 / 0.95**. Review the priors and sampling controls, then select
**Fit phase model**. Three observations per phase are deliberately sparse;
inspect diagnostics and prior sensitivity before interpreting the output.

## Trimodal calendar-time comparison

Load **`trimodal-calendar.csv`** for 60 synthetic radiocarbon determinations
generated from a genuinely trimodal calendar-time distribution. Calendar-time
component means are **1800, 3500, and 5200 cal BP**, with SDs **70, 100, and 90
years** and equal generating weights. Independent mixture draws produced
14, 25, and 21 events respectively; rows are not sorted by component.

Generation follows the measurement process: draw component and true calendar
date, use IntCal20 through `chronologer.utils.simulate_c14` to draw a radiocarbon
value including curve uncertainty, then add independent Gaussian laboratory
noise with SD 25, 30, 35, or 40 radiocarbon years. The input CSV contains the
resulting measured ages (rounded to 0.1 year) and the laboratory SD only; curve
uncertainty is handled separately by the calibration/model likelihood.

`trimodal-calendar-truth.csv` records latent dates and generating components for
inspection only—do **not** import it as observations. The metadata JSON records
seeds, curve-array checksum, and generating settings. Regenerate from the app
root with `conda run -n chronoapp python -B scripts/generate_trimodal_example.py`.
The existing helper uses linear interpolation; mixture inference currently uses
the measurement distribution's cubic splines. This small interpolation difference
is deliberate reuse of the existing helper, not a claim of exact model recovery.

For comparison, add all events to a Mixture summary and start with Maximum modes
= 5. A one-density comparison needs bounds spanning **all three** date regions
(for example 6000–1000 cal BP); the older 3500–1500 example bounds exclude modes.
Three generating components do not guarantee three recovered modes in a short
fit. No inference was used to select or filter these observations.

## Smaller density example

`density-benchmark.csv` contains 20 synthetic radiocarbon determinations for
exploring the Summary density model. These are illustrative measurements, not
actual archaeological data or a simulated draw from the full generative model.
The automated execution smoke test retains its original three-event fixture.

Load it using **Project → Import CSV** or **Calibrate → Load CSV**. CSV import
replaces the current project dataset. Columns are the event name (`id`),
conventional radiocarbon age in BP (`c14_mean`), one-standard-deviation measurement
error in years (`c14_err`), and calibration curve (`curve`).

Optional columns are `label` (grouping text), `datum` (`BP1950` or `BCAD`, default
`BP1950`), and `include_in_calibration` (`true` or `false`, default `true`). Datum
records a convention without converting the radiocarbon measurements. Included
rows can also be selected with the round checkboxes in Calibration.

To try the density model, open **Summarize**, add a summary, add all
20 project events, and choose **Density**. Use these settings:

| Setting | Value |
| --- | ---: |
| Older bound (cal BP) | 3500 |
| Younger bound (cal BP) | 1500 |
| Prior mean for population centre (cal BP) | 2500 |
| Prior SD for population centre (years) | 500 |
| Half-normal scale for population SD (years) | 400 |

Select **Fit density**. This short execution benchmark can report divergences;
it is not a validated scientific analysis.

`radiocarbon.csv` is a separate calibration example spanning a wider age range.
