import { projectState as state } from "./project-state.js";
import { runDensity } from "./jobs.js?v=job-monitor-2";
import { createSummaryPlot } from "./plots.js";
import { createMcmcDiagnostics } from "./mcmc-diagnostics.js";
import { pagination, PAGE_SIZE } from "./pagination.js";
import { DEFAULT_SAMPLING, samplingFor, samplingError, samplingControls } from "./sampling-settings.js";

// Latest plot-ready result persists per summary; raw chains are never serialized.
const models = { density: "Density", mixture: "Mixture" };
const modelGlosses = {
  ippp_gp: 'A Gaussian process describes log event intensity on a finite grid. The model fits event dates jointly with the full point-process likelihood over your declared observation period, including empty time and the total event count. The curve is events per year, not a normalized density or a demographic estimate. Assumes complete observation throughout the period; sampling effort, preservation and selection are not modeled.',
  density: "Assumes event dates follow one truncated-normal model within your calendar bounds. Fits its location and scale jointly with each event’s date using the radiocarbon measurements and calibration curve. Produces the model density averaged over the posterior, a pointwise 95% credible band, parameter posteriors, and model-conditioned event-date posteriors. Location and scale are the underlying normal’s parameters; truncation can make the model’s actual mean and SD differ.",
  mixture: "Maximum modes sets the maximum complexity available to the density model. The model estimates weights for all available Gaussian components and can give unnecessary components negligible weight. The displayed density is the quantity of interest; individual mixture components should not automatically be interpreted as archaeological groups or phases. Measurement uncertainty is modeled separately from event times.",
};
// Explicit starting suggestions in cal BP/year units, shown and editable before fitting.
const defaults = { older: 5000, younger: 1, mean: 2500, mean_sd: 500, sd_scale: 400 };
const settingsFor = summary => summary.model === 'ippp_gp'
  ? { older: summary.parameters.older ?? null, younger: summary.parameters.younger ?? null,
      grid_size: summary.parameters.grid_size === undefined ? 32 : summary.parameters.grid_size }
  : summary.model === "mixture"
  ? { K_max: summary.parameters.K_max === undefined ? 5 : summary.parameters.K_max }
  : Object.fromEntries(Object.entries(defaults).map(([key, value]) => [key, summary.parameters[key] === undefined ? value : summary.parameters[key]]));
const signature = summary => JSON.stringify([summary.model, summary.events, settingsFor(summary), samplingFor(summary)]);
function node(tag, text, className) {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  if (className) element.className = className;
  return element;
}
function button(text, action) {
  const element = node("button", text, "button secondary");
  element.type = "button";
  element.addEventListener("click", action);
  return element;
}
function describe(event) {
  const p = event.parameters;
  return event.distribution === "calrcarbon"
    ? `${event.id} · ${p.c14_mean} ± ${p.c14_err} ¹⁴C BP · ${p.curve}`
    : `${event.id} · ${event.distribution}`;
}

export function initSummarize({ process = false } = {}) {
  const kind = process ? 'process' : 'summary';
  const list = document.getElementById(`${kind}-list`);
  const add = document.getElementById(`add-${kind}`);
  const specs = () => (process ? state.data?.processes : state.data?.summaries) ?? [];
  const availableModels = process ? { ippp_gp: 'IPPP · Gaussian process' } : models;
  let ownChange = false;
  let generation = 0;
  let projectDocument = state.data;
  const running = new Map();
  const results = new Map(), failures = new Map(), plots = new Map();
  function commit(summaries) {
    ownChange = true;
    try { process ? state.setProcesses(summaries) : state.setSummaries(summaries); } finally { ownChange = false; }
  }
  function update(id, change) {
    commit(specs().map(summary => summary.id === id ? { ...summary, ...change } : summary));
    const current = specs().find(summary => summary.id === id);
    const displayedSignature = results.get(id)?.signature ?? (current.saved_run ? signature(current.saved_run) : null);
    if (displayedSignature && displayedSignature !== signature(current)) {
      results.delete(id); plots.get(id)?.dispose(); plots.delete(id);
      [...list.children].find(card => card.dataset.summaryId === id)?.querySelector(".summary-result")?.replaceChildren();
    }
    const savedStatus = [...list.children].find(card => card.dataset.summaryId === id)?.querySelector(".saved-run-state");
    if (savedStatus) savedStatus.textContent = current.saved_run && signature(current) !== signature(current.saved_run)
      ? "Inputs have changed since this run. Load saved run to restore its inputs and plots, or fit the edited model." : "";
    failures.delete(id);
  }
  function render() {
    plots.forEach(plot => plot.dispose()); plots.clear();
    list.replaceChildren();
    add.disabled = !state.data || specs().length >= 100;
    document.getElementById(`${kind}-empty`).hidden = specs().length > 0;
    for (const summary of specs()) {
      const card = node("section", undefined, "summary-card");
      card.dataset.summaryId = summary.id;
      const fields = node("div", undefined, "phase-fields");
      const nameLabel = node("label", process ? 'Process name' : "Summary name");
      const name = node("input");
      name.value = summary.label; name.maxLength = 120;
      name.addEventListener("input", () => update(summary.id, { label: name.value }));
      nameLabel.append(name);
      const modelLabel = node("label", "Model");
      const select = node("select", undefined, "phase-distribution");
      for (const [value, label] of Object.entries(availableModels)) select.append(new Option(label, value));
      select.value = summary.model;
      select.addEventListener("change", () => { update(summary.id, { model: select.value }); render(); });
      modelLabel.append(select); fields.append(nameLabel, modelLabel);
      const gloss = node("p", modelGlosses[summary.model], "help summary-model-gloss");
      gloss.id = `model-gloss-${summary.id}`;
      select.setAttribute("aria-describedby", gloss.id);
      card.append(fields, gloss, node("p", `${summary.events.length} events · saved copies, independent of later dataset edits`, "help"));
      const selected = node("ul", undefined, "summary-events");
      summary.events.forEach((event, index) => {
        const row = node("li");
        const remove = button("Remove", () => {
          update(summary.id, { events: summary.events.filter((_, i) => i !== index) }); render();
        });
        remove.setAttribute("aria-label", `Remove event ${event.id}`);
        row.append(node("span", describe(event)), remove); selected.append(row);
      });
      const picker = node("details", undefined, "summary-picker");
      picker.append(node("summary", "+ Add events from project"));
      const searchLabel = node("label", "Search project events");
      const search = node("input"); search.type = "search"; search.placeholder = "Name, distribution or curve";
      searchLabel.append(search); picker.append(searchLabel);
      const choices = node("div", undefined, "summary-choices");
      const chosen = new Set();
      const events = state.data.events;
      picker.append(choices);
      const pickerPager = pagination(choices, renderChoices, 'Summary event picker');
      const searchable = events.map((event, index) => ({ index, text: describe(event) }));
      function renderChoices() {
        choices.replaceChildren();
        const matches = searchable.filter(row => row.text.toLowerCase().includes(search.value.toLowerCase()));
        const start = pickerPager.update(matches.length);
        matches.slice(start, start + PAGE_SIZE).forEach(({ index, text }) => {
          const label = node('label'), check = node('input'); check.type = 'checkbox';
          check.checked = chosen.has(index);
          check.addEventListener('change', () => { check.checked ? chosen.add(index) : chosen.delete(index); });
          label.append(check, node('span', text)); choices.append(label);
        });
        if (!matches.length) choices.append(node('p', events.length ? 'No matching events.' : 'No project events yet. Load a CSV in Project first.', 'help'));
      }
      renderChoices();
      search.addEventListener('input', renderChoices);
      const status = node("p", "", "help"); status.setAttribute("role", "status");
      const addAll = button("Add all", () => {
        // Match saved copies once each, preserving distinct duplicate project rows.
        const existing = summary.events.map(event => JSON.stringify(event));
        const remaining = events.filter(event => {
          const index = existing.indexOf(JSON.stringify(event));
          if (index < 0) return true;
          existing.splice(index, 1); return false;
        });
        if (!remaining.length) { status.textContent = "All project events are already included."; return; }
        if (summary.events.length + remaining.length > 100) { status.textContent = "Each summary supports up to 100 events."; return; }
        update(summary.id, { events: [...summary.events, ...remaining] }); render();
      });
      addAll.disabled = !events.length;
      addAll.title = "Add all project events, including those hidden by search";
      const removeAll = button("Remove all", () => {
        update(summary.id, { events: [] }); render();
      });
      removeAll.disabled = !summary.events.length;
      removeAll.setAttribute("aria-label", "Remove all events from this summary");
      picker.append(button("Add selected", () => {
        if (!chosen.size) { status.textContent = "Select at least one event."; return; }
        if (summary.events.length + chosen.size > 100) { status.textContent = "Each summary supports up to 100 events."; return; }
        update(summary.id, { events: [...summary.events, ...[...chosen].sort((a, b) => a - b).map(i => events[i])] }); render();
      }), addAll, button("Go to Project / load CSV", () => document.getElementById("project-tab").click()), status);
      card.append(selected, removeAll, picker, button(process ? 'Remove process' : "Remove summary", () => {
        if (window.confirm(`Remove ${summary.label}?`)) { commit(specs().filter(item => item.id !== summary.id)); render(); }
      }));
      const fitSettings = node("div", undefined, "phase-fields summary-settings");
      if (summary.model === 'ippp_gp') {
        fitSettings.append(node('p', 'Declare the observation period explicitly. These dates describe when events could have been observed, not the oldest and youngest measured events. Start must be older than end.', 'help'));
        for (const [key, caption] of Object.entries({ older: 'Observation start · older cal BP (required)', younger: 'Observation end · younger cal BP (required)', grid_size: 'GP grid nodes' })) {
          const label = node('label', caption), input = node('input');
          input.type = 'number'; input.step = key === 'grid_size' ? '1' : 'any';
          input.dataset.setting = key; input.value = settingsFor(summary)[key] ?? '';
          input.required = true;
          if (key === 'grid_size') { input.min = '4'; input.max = '256'; }
          else input.placeholder = 'Required — no default';
          input.addEventListener('input', () => {
            const current = specs().find(s => s.id === summary.id);
            update(summary.id, { parameters: { ...current.parameters, ...settingsFor(current), [key]: input.value === '' ? null : Number(input.value) } });
          });
          label.append(input); fitSettings.append(label);
        }
        fitSettings.append(node('p', 'Benchmark priors: baseline log rate Normal(log(10 / period length), 1.5); GP amplitude HalfNormal(1); length scale LogNormal(log(period length / 5), 0.5), with an exponentiated-quadratic covariance. Intensity is linearly interpolated between positive grid-node rates; its integral uses that same interpolation. Priors can be overridden in the engine API. Check grid-resolution and prior sensitivity before scientific use.', 'help'));
      } else if (summary.model === "density") {
        fitSettings.append(node("p", "Truncated-normal model density. All events share these calendar bounds and one calibration curve. Review the bounds and hyperpriors before fitting.", "help"));
        for (const [key, caption] of Object.entries({ older: "Older bound (cal BP)", younger: "Younger bound (cal BP)", mean: "Location hyperprior mean (cal BP)", mean_sd: "Location hyperprior SD (years)", sd_scale: "Scale hyperprior: half-normal scale (years)" })) {
          const label = node("label", caption), input = node("input");
          input.type = "number"; input.step = "any"; input.dataset.setting = key;
          input.value = settingsFor(summary)[key] ?? "";
          input.addEventListener("input", () => {
            const current = specs().find(s => s.id === summary.id);
            update(summary.id, { parameters: { ...current.parameters, ...settingsFor(current), [key]: input.value === "" ? null : Number(input.value) } });
          });
          label.append(input); fitSettings.append(label);
        }
      } else {
        const label = node("label", "Maximum modes"), input = node("input");
        input.type = "number"; input.min = "1"; input.max = "20"; input.step = "1";
        input.dataset.setting = "K_max"; input.value = settingsFor(summary).K_max;
        input.addEventListener("input", () => {
          const current = specs().find(s => s.id === summary.id);
          update(summary.id, { parameters: { ...current.parameters, K_max: input.value === "" ? null : Number(input.value) } });
        });
        label.append(input); fitSettings.append(label);
        fitSettings.append(node("p", "Normal, uniform, or radiocarbon measurements in BP1950. Each radiocarbon event uses its selected curve. Fixed sparse-weight and scale hyperpriors use a time scale derived from the input measurements. Inspect diagnostics before interpretation.", "help"));
      }
      const fitStatus = node("p", running.has(summary.id) ? "Inference submitted. Progress, cancellation and messages are above the tabs; you can keep working elsewhere." : failures.get(summary.id) ?? "", "summary-fit-status help");
      fitStatus.setAttribute("role", "status");
      const run = button(process ? 'Fit GP IPPP' : summary.model === "mixture" ? "Fit mixture" : "Fit density", async () => {
        const current = specs().find(s => s.id === summary.id);
        if (running.has(summary.id) || !current) return;
        const settings = settingsFor(current);
        const sampling = samplingFor(current);
        const error = samplingError(sampling);
        if (error) { fitStatus.textContent = error; return; }
        const mixture = current.model === "mixture";
        const ippp = current.model === 'ippp_gp';
        if (ippp && (![settings.older, settings.younger].every(v => typeof v === 'number' && Number.isFinite(v)) || settings.older <= settings.younger)) {
          fitStatus.textContent = 'Declare both observation start and end explicitly; older cal BP must be greater than younger cal BP.'; return;
        }
        if (ippp && (!Number.isInteger(settings.grid_size) || settings.grid_size < 4 || settings.grid_size > 256)) {
          fitStatus.textContent = 'GP grid nodes must be an integer from 4 to 256.'; return;
        }
        if (mixture && (!Number.isInteger(settings.K_max) || settings.K_max < 1 || settings.K_max > 20)) {
          fitStatus.textContent = "Maximum modes must be an integer from 1 to 20."; return;
        }
        if ((mixture || ippp) && (!current.events.length || current.events.some(e => !["calrcarbon", "normal", "uniform"].includes(e.distribution) || (e.datum ?? "BP1950") !== "BP1950"))) {
          fitStatus.textContent = "Add normal, uniform, or radiocarbon measurements using BP1950 before fitting."; return;
        }
        if (!mixture && !ippp && (!current.events.length || current.events.some(e => e.distribution !== "calrcarbon"))) {
          fitStatus.textContent = "Add radiocarbon events before fitting; other event distributions are not supported in this benchmark."; return;
        }
        if (!mixture && !ippp && (!Object.values(settings).every(v => typeof v === "number" && Number.isFinite(v))
            || settings.older <= settings.younger || settings.mean_sd <= 0 || settings.sd_scale <= 0)) {
          fitStatus.textContent = "Enter finite prior settings with positive scales and Older greater than Younger."; return;
        }
        // Record the exact visible settings used, including starting suggestions.
        const parameters = { ...settings, sampling };
        update(current.id, { parameters });
        const token = { id: current.id, generation, signature: signature(current) };
        running.set(current.id, token); results.delete(current.id); failures.delete(current.id); render();
        try {
          const payload = (mixture || ippp) ? { ...(ippp ? { observation: settings } : { K_max: settings.K_max }), events: current.events.map(e => ({
            id: e.id, distribution: e.distribution, parameters: e.parameters, datum: e.datum ?? "BP1950",
          })) } : { settings, determinations: current.events.map(e => ({
            id: e.id, age: e.parameters.c14_mean, error: e.parameters.c14_err, curve: e.parameters.curve,
          })) };
          const result = await runDensity({ ...payload, sampling }, `${state.data.metadata.project_name} / ${current.label}`);
          const latest = specs().find(s => s.id === token.id);
          if (generation === token.generation && latest && signature(latest) === token.signature) {
            results.set(token.id, { signature: token.signature, result });
            const saved_run = { id: crypto.randomUUID(), created_at: new Date().toISOString(),
              model: latest.model, events: structuredClone(latest.events), parameters,
              result };
            commit(specs().map(s => s.id === token.id ? { ...s, saved_run } : s));
          }
        } catch (error) {
          if (generation === token.generation) failures.set(token.id, error.message);
        } finally { if (running.get(token.id) === token) running.delete(token.id); render(); }
      });
      run.classList.add("summary-fit");
      run.disabled = running.has(summary.id);
      card.append(fitSettings, samplingControls(samplingFor(summary), sampling => {
        const current = specs().find(s => s.id === summary.id);
        update(summary.id, { parameters: { ...current.parameters, sampling } });
      }), run, fitStatus);
      if (summary.saved_run) {
        const saved = summary.saved_run;
        const tools = node("div", undefined, "summary-saved-run");
        const size = new Blob([JSON.stringify(saved)]).size / 1024;
        tools.append(node("p", `Latest saved run: ${new Date(saved.created_at).toLocaleString()} · ${size.toFixed(0)} KiB before compression. Included when you save this project. Successful reruns replace it.`, "help"));
        tools.append(button("Load saved run", () => {
          if (signature(summary) !== signature(saved) && !window.confirm("Restore this run’s saved inputs and settings? Current summary edits will be replaced.")) return;
          update(summary.id, { model: saved.model, events: saved.events, parameters: saved.parameters });
          results.set(summary.id, { signature: signature(saved), result: saved.result });
          render();
        }), button("Remove saved result", () => {
          if (!window.confirm("Remove this summary’s saved plots? Inputs are kept. Save the project to keep this removal.")) return;
          results.delete(summary.id);
          commit(specs().map(s => {
            if (s.id !== summary.id) return s;
            const { saved_run, ...remaining } = s; return remaining;
          })); render();
        }));
        tools.append(node("p", signature(summary) !== signature(saved) ? "Inputs have changed since this run. Load saved run to restore its inputs and plots, or fit the edited model." : "", "help saved-run-state"));
        card.append(tools);
      }
      // Keep an active fit's own specification fixed; other tabs remain usable.
      if (running.has(summary.id)) {
        card.querySelectorAll("input, select, button").forEach(control => { control.disabled = true; });
        card.setAttribute("aria-busy", "true");
      }
      const resultContainer = node("div", undefined, "summary-result");
      card.append(resultContainer);
      list.append(card);
      const fitted = results.get(summary.id) ?? (summary.saved_run ? { signature: signature(summary.saved_run), result: summary.saved_run.result } : null);
      if (!running.has(summary.id) && fitted && fitted.signature === signature(summary)) {
        try {
          const result = fitted.result;
          resultContainer.append(node("p", `Completed in ${result.elapsed_seconds.toFixed(1)} s · ${result.sampling.chains} chains × ${result.sampling.draws} draws (${result.sampling.tune} tuning per chain) · ${result.sampling.cores ?? 1} cores. ${result.warnings.join(" ")}`, "help"));
          const plot = createSummaryPlot(resultContainer, result, summary.label);
          const mcmc = createMcmcDiagnostics(resultContainer, result.mcmc);
          plots.set(summary.id, { dispose() { plot.dispose(); mcmc.dispose(); } });
          if (result.model === "gaussian_mixture") {
            const diagnostics = node("details", undefined, "mixture-diagnostics");
            diagnostics.append(node("summary", "Mixture diagnostics"));
            diagnostics.append(node("p", `Mean component weights (ordered by calendar coordinate): ${result.diagnostics.weight_mean.map(w => w.toFixed(3)).join(", ")}. Component identities are not archaeological groups.`, "help"));
            diagnostics.append(node("p", `Fraction of draws with weight below 0.05: ${result.diagnostics.weight_below_005.map(w => w.toFixed(2)).join(", ")}. These describe weight uncertainty, not an inferred number of groups.`, "help"));
            resultContainer.append(diagnostics);
          }
        } catch (error) { resultContainer.replaceChildren(node("p", error.message, "help")); }
      }
    }
  }
  state.addEventListener("change", event => {
    if (!ownChange) {
      if (state.data !== projectDocument) {
        projectDocument = state.data; generation++; results.clear(); failures.clear(); running.clear();
      }
      render();
    }
  });
  add.addEventListener("click", () => {
    if (!state.data || state.busy || specs().length >= 100) return;
    commit([...specs(), { id: `${kind}-${crypto.randomUUID()}`, label: `${process ? 'Process' : 'Summary'} ${specs().length + 1}`,
      model: process ? 'ippp_gp' : "density", events: [], parameters: { sampling: { ...DEFAULT_SAMPLING } } }]);
    render(); list.lastElementChild.querySelector("input").focus();
  });
  render();
}
