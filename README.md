# Chronologer

**Bayesian chronological modelling for archaeology, without the scripting.**

Chronologer is a desktop application for radiocarbon calibration and
probabilistic modelling of archaeological events through time.

It provides a graphical interface for moving from individual radiocarbon
determinations to explicit models of temporal density and event-generating
processes. The aim is to make the statistical assumptions visible while
keeping the machinery needed to fit the models out of the way.

> **Beta:** Chronologer is under active development. Results should be
> inspected critically and MCMC diagnostics checked before scientific use.

**[Download the Windows beta · v0.1.0-beta.1](https://github.com/wccarleton/chronoapp/releases/download/v0.1.0-beta.1/Chronologer-0.1.0-beta.1-win64.zip)**

[Website](https://wccarleton.github.io/chronoapp/) · [Documentation](https://wccarleton.github.io/chronoapp/docs/)

No Python installation is required. Download the ZIP, extract it, and
double-click `ChronoApp.exe`.

## Try it with example data

No need to enter dates by hand: the Windows ZIP includes synthetic test data
in `ChronoApp/docs/examples/`. Start with
[`density-benchmark.csv`](docs/examples/density-benchmark.csv) (20 dates), or try
[`trimodal-calendar.csv`](docs/examples/trimodal-calendar.csv) (60 dates) for mixture modelling.
In the app, choose **Project → Import CSV**, then select a file.
These are made-up datasets for trying the tools, not archaeological observations.
See the [example guide](docs/examples/README.md) for suggested model settings.

## What can I do with it?

### Calibrate radiocarbon dates

Enter determinations directly or import a CSV, calibrate one or many dates,
inspect individual or stacked results, and export publication-ready figures
as SVG, PDF, or PNG.

Chronologer keeps the measurement process separate from subsequent models of
the events themselves.

### Summarize events through time

The **Summary** workspace fits Bayesian models of the latent temporal
distribution of events rather than summing calibrated probability
distributions.

Single-density and flexible mixture models are available, with uncertainty
in event dates propagated through the model.

### Model an event-generating process

The **Process Lab** moves beyond normalized temporal densities.

Its Gaussian-process inhomogeneous Poisson point-process (GP-IPPP) model
estimates an event intensity — events per unit time — over an explicitly
declared observation period.

The model retains information about both event timing and event count and
does not require the inferred intensity to approach zero at the edges of the
observation window.

### Inspect the inference

Bayesian models include MCMC diagnostics and chain plots. Model results,
diagnostics, figures, inputs, and settings can be retained in a Chronologer
project and reopened without rerunning the analysis.

## Projects

Chronologer projects are portable `.chrono` files.

A project stores your event data, model specifications, settings, and saved
results in a single file. Save it wherever you normally keep your research
data and reopen it later to continue working.

CSV import is available for bringing existing radiocarbon datasets into a
project.

## Current status

Chronologer is an early beta.

Currently implemented:

- radiocarbon calibration using IntCal20
- individual and stacked calibration plots
- Bayesian single-density temporal models
- Bayesian Gaussian-mixture temporal models
- Gaussian-process IPPP event-intensity modelling
- MCMC diagnostics and chain plots
- SVG, vector PDF, and PNG figure export
- portable `.chrono` projects
- CSV import
- Windows distribution requiring no Python installation

The **Phase** workspace fits uniform or normal phase distributions using each
event’s project label for membership. Arrange the phase cards, choose ordering
anchors in **Run phase model**, and fit to obtain phase densities, derived
quantile intervals, anchor separations and MCMC diagnostics. Results are retained
when saving the project. **Depth** is reserved for future age-depth models.

## A note on modelling philosophy

Chronologer treats archaeological dates as uncertain observations of events.

Those events may in turn be described by a temporal distribution or generated
by an explicit stochastic process. These are different inferential objects,
and Chronologer keeps them separate.

The interface therefore tries to make substantive chronological assumptions
explicit rather than hiding them inside plotting operations or conventional
workflow terminology.

## Documentation

Detailed documentation is available in [`docs/`](docs/), including model
definitions, priors, project format, validation benchmarks, diagnostics, and
known limitations.

## For developers

Chronologer consists of a Python scientific engine and the Chronologer
application interface. Development requires Python 3.12+.

Build the Windows bundle from the `chronoapp` Conda environment with
`powershell -ExecutionPolicy Bypass -File scripts/build_windows.ps1`.
The output is `dist/Chronologer-0.1.0-beta.1-win64.zip`.
See [`AGENTS.md`](AGENTS.md) for architecture and [`scripts/`](scripts/) for workflow checks.

## Citation

Chronologer is under active development. Citation information will be added
with the first archival software release.

## License

Chronologer is open-source software released under the [MIT License](LICENSE).
Bundled third-party components retain their own licenses.
