import { projectState as state } from './project-state.js';
import { runDensity } from './jobs.js?v=job-monitor-2';
import { createSummaryPlot } from './plots.js';
import { createMcmcDiagnostics } from './mcmc-diagnostics.js';
import { DEFAULT_SAMPLING, samplingFor, samplingError, samplingControls } from './sampling-settings.js';
import { phaseSettings, phaseCopy, anchorError } from './phase-settings.js';

function node(tag, text, className) {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  if (className) element.className = className;
  return element;
}
function button(text, action) {
  const element = node('button', text, 'button secondary'); element.type = 'button';
  element.addEventListener('click', action); return element;
}
const eventCopy = event => ({ id: event.id, label: event.label, distribution: event.distribution,
  parameters: event.parameters, datum: event.datum ?? 'BP1950' });
const settingsFor = spec => phaseSettings(spec.parameters);
const savedSignature = saved => JSON.stringify({ phases: saved.parameters.phases.map(phase => phaseCopy(phase, saved.parameters)), events: saved.events.map(eventCopy),
  settings: settingsFor(saved), sampling: saved.parameters.sampling });
const number = value => value.toLocaleString(undefined, { maximumFractionDigits: 1 });

export function initPhaseRun() {
  const panel = document.getElementById('phase-run');
  const spec = () => state.data?.phase_model ?? { parameters: { sampling: { ...DEFAULT_SAMPLING } } };
  let projectDocument = state.data, running = null, ownChange = false, viewSaved = false, message = '';
  let plots = [], output;
  function payload() {
    const phases = (state.data?.phases ?? []).map(phase => phaseCopy(phase, spec().parameters));
    const labels = new Set(phases.map(phase => phase.label));
    return { phases, events: (state.data?.events ?? []).filter(event => labels.has(event.label)).map(eventCopy),
      settings: settingsFor(spec()), sampling: samplingFor(spec()) };
  }
  function commit(model) {
    ownChange = true;
    try { state.setPhaseModel(model); } finally { ownChange = false; }
  }
  function update(change) {
    commit({ ...spec(), parameters: { ...spec().parameters, ...change } });
    viewSaved = false; message = ''; renderOutput();
    document.getElementById('phase-fit-status').textContent = error(payload()) ?? '';
  }
  function error(data) {
    if (!data.phases.length) return 'Add phases above before fitting.';
    const labels = data.phases.map(phase => phase.label);
    if (labels.some(label => !label.trim()) || new Set(labels).size !== labels.length) return 'Phase names must be nonempty and unique.';
    for (const phase of data.phases) {
      const problem = anchorError(phase);
      if (problem) return `${phase.label}: ${problem}`;
    }
    const empty = labels.filter(label => !data.events.some(event => event.label === label));
    if (empty.length) return `No matching event labels for: ${empty.join(', ')}. Edit the names above or the labels in Project.`;
    if (data.events.length > 100) return 'This phase model currently supports at most 100 matching events.';
    if (data.events.some(event => event.datum !== 'BP1950' || !['normal', 'uniform', 'calrcarbon'].includes(event.distribution))) return 'Phase modelling requires normal, uniform or radiocarbon measurements using BP1950.';
    if (data.settings.delta_scale !== null && !(Number.isFinite(data.settings.delta_scale) && data.settings.delta_scale > 0)) return 'Delta prior scale must be positive, or blank for Auto.';
    return samplingError(data.sampling);
  }
  function renderOutput() {
    plots.forEach(plot => plot.dispose()); plots = [];
    output.replaceChildren();
    const saved = spec().saved_run;
    if (!saved) return;
    const matches = JSON.stringify(payload()) === savedSignature(saved);
    if (!matches && !viewSaved) {
      output.append(node('p', 'Inputs have changed since this run. Fit the edited model or view the saved run’s outputs.', 'help saved-run-state'));
      return;
    }
    const result = saved.result;
    output.append(node('p', `${matches ? 'Completed run' : 'Saved run · historical inputs'}: ${new Date(saved.created_at).toLocaleString()} · ${result.elapsed_seconds.toFixed(1)} s · ${result.sampling.chains} chains × ${result.sampling.draws} draws · ${result.sampling.cores ?? 1} cores. ${result.warnings.join(' ')}`, 'help'));
    const intervals = node('table', undefined, 'phase-estimates');
    const head = node('tr');
    ['Phase', 'Distribution interval', 'Older quantile · BP1950', 'Younger quantile · BP1950'].forEach(text => head.append(node('th', text)));
    const thead = node('thead'); thead.append(head); intervals.append(thead);
    const body = node('tbody');
    for (const phase of result.phases) {
      const interval = phase.interval, row = node('tr');
      const estimate = value => `${number(-value.mean)} (${number(-value.upper)}–${number(-value.lower)})`;
      [phase.label, `${100 * interval.p}–${100 * interval.q}% quantiles`, estimate(interval.lower), estimate(interval.upper)].forEach(text => row.append(node('td', text)));
      body.append(row);
    }
    intervals.append(body); output.append(intervals);
    output.append(node('p', 'Quantile estimates show posterior means, with 95% credible intervals in parentheses. Uniform intervals are exact distribution limits; normal intervals use the 5th and 95th percentiles. These are derived queries, not boundary parameters.', 'help'));
    if (result.diagnostics.deltas.length) {
      output.append(node('h3', 'Anchor separations'));
      for (const delta of result.diagnostics.deltas) output.append(node('p', `${delta.before} (${delta.anchors[0]}) → ${delta.after} (${delta.anchors[1]}): delta ${number(delta.mean)} years (95% interval ${number(delta.lower)}–${number(delta.upper)}).`, 'help'));
    }
    for (const phase of result.phases) {
      const section = node('section', undefined, 'phase-result'); section.append(node('h3', phase.label));
      output.append(section);
      const events = result.marginals.events.filter(event => saved.events[event.index].label === phase.label);
      plots.push(createSummaryPlot(section, { ...result, density: phase.density, distribution: phase.distribution,
        marginals: { parameters: phase.parameters, events } }, phase.label));
    }
    plots.push(createMcmcDiagnostics(output, result.mcmc));
  }
  function render() {
    plots.forEach(plot => plot.dispose()); plots = [];
    panel.replaceChildren();
    panel.append(node('h2', 'Run phase model'));
    const data = payload();
    const excluded = (state.data?.events.length ?? 0) - data.events.length;
    panel.append(node('p', `${data.phases.length} phases · ${data.events.length} matching events · ${excluded} project events outside these phase labels. Membership uses exact labels; calibration selection is separate.`, 'help'));
    const fields = node('div', undefined, 'phase-fields');
    const deltaLabel = node('label', 'Delta prior scale · years');
    const delta = node('input'); delta.type = 'number'; delta.step = 'any'; delta.min = '0'; delta.id = 'phase-delta-scale';
    delta.value = data.settings.delta_scale ?? ''; delta.placeholder = 'Auto from phase prior time scales';
    delta.addEventListener('input', () => update({ delta_scale: delta.value === '' ? null : Number(delta.value) }));
    deltaLabel.append(delta); fields.append(deltaLabel); panel.append(fields);
    panel.append(node('p', 'When card ordering is enabled, adjacent phases connect the older phase’s younger (or sole) anchor to the younger phase’s older anchor. Delta has a positive half-normal prior; it measures anchor separation and is a phase gap only for end-to-start ordering. Downstream locations are derived; only chain roots retain independent location priors.', 'help'));
    panel.append(node('p', 'Blank phase priors use the labelled measurements: location mean = mean measurement centers; reference time scale = max(center range, median measurement SD). Positive scale has a log-normal prior with log SD 0.75 and reference sigma 0.2 × time scale (uniform width = √12 × reference sigma). Auto delta scale uses the larger time scale of adjacent phases. Review priors for your model.', 'help'));
    panel.append(samplingControls(data.sampling, sampling => update({ sampling })));
    const status = node('p', running ? 'Inference submitted. Progress, cancellation and messages are above the tabs.' : message || error(data) || '', 'help');
    status.id = 'phase-fit-status'; status.setAttribute('role', 'status');
    const run = button('Fit phase model', async () => {
      if (running || !state.data || state.busy) return;
      const inputs = structuredClone(payload());
      const problem = error(inputs);
      if (problem) { status.textContent = problem; return; }
      const token = { document: state.data, inputs }; running = token; message = ''; viewSaved = false; render();
      try {
        const result = await runDensity(inputs, 'Phase model');
        if (state.data === token.document) {
          const saved_run = { id: crypto.randomUUID(), created_at: new Date().toISOString(), model: 'phase',
            events: inputs.events, parameters: { ...inputs.settings, phases: inputs.phases, sampling: inputs.sampling }, result };
          commit({ ...spec(), saved_run });
        }
      } catch (failure) { if (state.data === token.document) message = failure.message; }
      finally { if (running === token) { running = null; render(); } }
    });
    run.id = 'fit-phase'; run.disabled = !state.data || Boolean(running); panel.append(run, status);
    if (spec().saved_run) {
      panel.append(node('p', 'The latest completed run is included when you save this project. It contains its input snapshot, settings, plots and diagnostics; successful reruns replace it.', 'help'));
      panel.append(button('View saved run', () => { viewSaved = true; renderOutput(); }), button('Remove saved result', () => {
        const { saved_run, ...remaining } = spec(); commit(remaining); viewSaved = false; render();
      }));
    }
    output = node('div', undefined, 'summary-result'); output.id = 'phase-output'; panel.append(output);
    if (running) panel.querySelectorAll('input, select, button').forEach(control => { control.disabled = true; });
    if (running) panel.setAttribute('aria-busy', 'true'); else panel.removeAttribute('aria-busy');
    renderOutput();
  }
  state.addEventListener('change', () => {
    if (ownChange) return;
    if (projectDocument !== state.data) { projectDocument = state.data; running = null; message = ''; }
    viewSaved = false; render();
  });
  render();
}
