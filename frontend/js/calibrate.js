import { getCurves, getCurve, calibrate } from "./api.js";
import { createPlotWorkspace } from "./plots.js";
import { projectState } from "./project-state.js";
import { fillCurveChoices } from "./event-table.js";
import { pagination, MAX_EVENTS, PAGE_SIZE } from "./pagination.js";

export async function initCalibration() {
  const byId = id => document.getElementById(id);
  const rows = byId("determination-rows");
  const form = byId("calibration-form");
  form.noValidate = true; // Validate selected events in state, including other pages.
  const pager = pagination(rows.closest('.table-scroll'), renderRows, 'Radiocarbon events');
  const inclusion = document.createElement('div'); inclusion.className = 'event-pagination';
  for (const [label, include] of [['Include all', true], ['Exclude all', false]]) {
    const control = document.createElement('button'); control.type = 'button';
    control.className = 'button secondary'; control.textContent = label;
    control.addEventListener('click', () => projectState.setEvents(projectState.data.events.map(event =>
      event.distribution === 'calrcarbon' ? { ...event, include_in_calibration: include } : event)));
    inclusion.append(control);
  }
  rows.closest('.table-scroll').before(inclusion);
  const select = byId("curve-select");
  const button = byId("calibrate-button");
  let nextId = 1, revision = 0, curveRequest = 0;
  let curve = null, results = null, busy = false;
  let catalogReady = false, ownChange = false, eventsSnapshot = "";
  let curveCatalog = [];
  const plots = createPlotWorkspace(byId("result-plots"), byId("curve-plot"));

  function showErrors(messages) {
    const box = byId("form-errors");
    box.replaceChildren();
    box.hidden = !messages.length;
    const list = document.createElement("ul");
    messages.forEach(message => {
      const item = document.createElement("li");
      item.textContent = message;
      list.append(item);
    });
    box.append(list);
  }
  function changed(row) {
    revision++;
    if (results) byId("results-status").textContent = "Inputs changed. Calibrate again to update these results.";
    if (catalogReady && row) {
      ownChange = true;
      try {
        const input = field => row.querySelector(`[data-field=${field}]`).value.trim();
        const update = { id: input("id"), distribution: "calrcarbon", parameters: {
          c14_mean: input("age") === "" ? null : Number(input("age")),
          c14_err: input("error") === "" ? null : Number(input("error")), curve: input("curve"),
        }, include_in_calibration: row.querySelector('[data-field=include]').checked };
        if (row.dataset.eventIndex === "") {
          row.dataset.eventIndex = projectState.data.events.length;
          projectState.setEvents([...projectState.data.events, { ...update, label: "", datum: "BP1950" }]);
        } else projectState.updateEvent(Number(row.dataset.eventIndex), update);
        eventsSnapshot = JSON.stringify(projectState.data.events);
      } finally { ownChange = false; }
    }
  }
  function updateRows() {
    const count = (projectState.data?.events ?? []).filter(e => e.distribution === 'calrcarbon').length || rows.children.length;
    byId("row-count").textContent = `${count} ${count === 1 ? "sample" : "samples"}`;
    rows.querySelectorAll(".remove-row").forEach(remove => { remove.disabled = count === 1; });
    byId("add-row").disabled = (projectState.data?.events.length ?? 0) >= MAX_EVENTS;
  }
  function addRow(age = "", error = "", id = null, curveId = select.value, index = null, included = true) {
    const row = document.createElement("tr");
    row.dataset.eventIndex = index ?? "";
    const rowId = nextId++;
    const includeCell = document.createElement("td"), include = document.createElement("input");
    include.type = "checkbox"; include.className = "calibration-include";
    include.checked = included; include.dataset.field = "include";
    include.setAttribute("aria-label", `Include row ${rowId} in calibration`);
    include.addEventListener("change", () => changed(row));
    includeCell.append(include); row.append(includeCell);
    [["id", id ?? `Sample ${rowId}`, "text"], ["age", age ?? "", "number"], ["error", error ?? "", "number"]].forEach(([field, value, type]) => {
      const td = document.createElement("td");
      const input = document.createElement("input");
      input.type = type;
      input.value = value;
      input.dataset.field = field;
      input.setAttribute("aria-label", `${field === "id" ? "Sample ID" : field === "age" ? "Radiocarbon age BP" : "Laboratory error"}, row ${rowId}`);
      input.required = true;
      if (type === "number") { input.step = "any"; input.inputMode = "decimal"; }
      else input.maxLength = 120;
      input.addEventListener("input", () => { input.removeAttribute("aria-invalid"); changed(row); });
      td.append(input);
      row.append(td);
      if (field === "id") {
        const distribution = document.createElement("td"); distribution.textContent = "calrcarbon";
        distribution.className = "event-distribution"; row.append(distribution);
      }
    });
    const curveCell = document.createElement("td");
    const rowCurve = document.createElement("select");
    rowCurve.dataset.field = "curve";
    rowCurve.setAttribute("aria-label", `Calibration curve, row ${rowId}`);
    rowCurve.required = true;
    fillCurveChoices(rowCurve, curveCatalog, curveId);
    rowCurve.addEventListener("change", () => { rowCurve.removeAttribute("aria-invalid"); changed(row); });
    curveCell.append(rowCurve);
    row.append(curveCell);
    const td = document.createElement("td");
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "remove-row";
    remove.textContent = "×";
    remove.setAttribute("aria-label", `Remove row ${rowId}`);
    remove.addEventListener("click", () => {
      if (row.dataset.eventIndex !== "") projectState.removeEvent(Number(row.dataset.eventIndex));
      else { row.remove(); updateRows(); }
    });
    td.append(remove); row.append(td); rows.append(row);
    return row;
  }
  async function loadCurve() {
    const token = ++curveRequest;
    curve = null;
    plots.setCurve(null);
    byId("curve-status").hidden = false;
    byId("curve-status").textContent = "Loading calibration curve…";
    byId("curve-description").textContent = `${select.value} · supplied by chronologer`;
    try {
      const loaded = await getCurve(select.value);
      if (token !== curveRequest) return;
      curve = loaded;
      byId("curve-status").hidden = true;
      byId("curve-subtitle").textContent = `${curve.id} · curve values supplied by chronologer`;
      plots.setCurve(curve);
    } catch (error) {
      if (token !== curveRequest) return;
      byId("curve-status").textContent = error.message;
    }
  }
  function restoreProject() {
    revision++;
    results = null;
    plots.clearResults();
    byId("results-empty").hidden = false;
    byId("result-count").hidden = true;
    byId("result-subtitle").textContent = "Calendar-time distributions";
    byId("results-status").textContent = "Calibrate to generate plots for this project.";
    const events = projectState.data?.events ?? [];
    eventsSnapshot = JSON.stringify(events);
    showErrors([]);
    renderRows();
    select.disabled = !catalogReady;
    button.disabled = busy || !catalogReady;
    if (catalogReady) {
      projectState.defaultCurve = select.value || null;
    }
  }
  function renderRows() {
    rows.replaceChildren(); nextId = 1;
    const events = projectState.data?.events ?? [];
    const radiocarbon = events.map((event, index) => ({ event, index })).filter(({ event }) => event.distribution === 'calrcarbon');
    const start = pager.update(radiocarbon.length);
    for (const { event, index } of radiocarbon.slice(start, start + PAGE_SIZE)) {
      addRow(event.parameters.c14_mean, event.parameters.c14_err, event.id, event.parameters.curve, index, event.include_in_calibration !== false);
    }
    if (!events.length) addRow();
    updateRows();
  }
  projectState.addEventListener("change", event => {
    if (!ownChange && (event.detail.replace || eventsSnapshot !== JSON.stringify(projectState.data?.events))) restoreProject();
  });
  byId("add-row").addEventListener("click", () => {
    if ((projectState.data?.events.length ?? 0) >= MAX_EVENTS) return;
    // Commit an initial blank row before adding another, so both tables agree.
    for (const existing of rows.children) if (existing.dataset.eventIndex === "") changed(existing);
    const row = addRow();
    changed(row);
    pager.last(projectState.data.events.filter(e => e.distribution === 'calrcarbon').length);
    renderRows();
    rows.lastElementChild.querySelector('[data-field=id]').focus({ preventScroll: true });
    const scroller = rows.closest(".table-scroll");
    scroller.scrollTop = scroller.scrollHeight;
    updateRows();
  });
  select.addEventListener("change", () => {
    projectState.defaultCurve = select.value || null;
    loadCurve();
  });
  form.addEventListener("submit", async event => {
    event.preventDefault();
    if (busy || !catalogReady) return;
    const errors = [];
    let invalid = null;
    for (const row of rows.children) if (row.dataset.eventIndex === '') changed(row);
    const selectedEvents = projectState.data.events.map((event, index) => ({ event, index }))
      .filter(({ event }) => event.distribution === 'calrcarbon' && event.include_in_calibration !== false);
    if (selectedEvents.length > 100) {
      showErrors(['Projects support 10,000 events; calibration currently supports 100 selected events per run. Use Exclude all, then select the events to calibrate across any pages.']);
      return;
    }
    const determinations = selectedEvents.map(({ event, index }) => {
      const values = {};
      const row = rows.querySelector(`[data-event-index="${index}"]`);
      Object.entries({ id: event.id, age: event.parameters.c14_mean, error: event.parameters.c14_err, curve: event.parameters.curve }).forEach(([field, raw]) => {
        const input = row?.querySelector(`[data-field=${field}]`);
        const value = String(raw ?? '').trim();
        const valid = field === "curve" ? curveCatalog.some(item => item.id === value && item.available)
          : field === "id" ? value.length > 0 : value !== "" && Number.isFinite(Number(value)) && (field !== "error" || Number(value) > 0);
        input?.setAttribute("aria-invalid", String(!valid));
        if (!valid) {
          invalid ??= input;
          errors.push(`Project event ${index + 1}: ${field === "curve" ? `curve '${value}' is unavailable; choose an installed curve` : field === "id" ? "enter a sample ID" : field === "error" ? "error must be a number greater than zero" : "enter a finite radiocarbon age"}.`);
        }
        values[field] = ["id", "curve"].includes(field) ? value : Number(value);
      });
      return values;
    });
    if (!determinations.length) errors.push("Select at least one radiocarbon event to calibrate.");
    showErrors(errors);
    if (errors.length) { invalid?.focus(); return; }
    const submittedRevision = revision;
    busy = true; button.disabled = true;
    form.setAttribute("aria-busy", "true");
    button.textContent = "Calibrating…";
    byId("results-status").textContent = "Calculating with chronologer…";
    try {
      const names = [...new Set(determinations.map(row => row.curve))];
      const [response, loadedCurves] = await Promise.all([
        calibrate({ determinations }),
        Promise.all(names.map(name => getCurve(name))),
      ]);
      if (submittedRevision !== revision) {
        byId("results-status").textContent = "Inputs changed during calibration. Calibrate again to show current results.";
        return;
      }
      results = response;
      byId("results-empty").hidden = true;
      byId("result-count").hidden = false;
      byId("result-count").textContent = `${response.results.length} ${response.results.length === 1 ? "sample" : "samples"}`;
      byId("result-subtitle").textContent = `${names.join(" / ")} · individual views and stacked comparison`;
      byId("results-status").textContent = "Individual plots preserve engine values; stacked plots scale each density to the same peak height.";
      plots.setResults(response, Object.fromEntries(loadedCurves.map(item => [item.id, item])));
    } catch (error) {
      showErrors([error.message]);
      byId("results-status").textContent = results ? "Calibration failed. Previous results remain displayed." : "Calibration did not complete.";
    } finally {
      busy = false; button.disabled = !catalogReady;
      form.setAttribute("aria-busy", "false");
      button.textContent = "Calibrate determinations →";
    }
  });
  try {
    const catalog = await getCurves();
    curveCatalog = catalog.curves;
    select.replaceChildren();
    for (const item of catalog.curves) {
      const option = new Option(`${item.label}${item.available ? "" : " · not installed"}`, item.id);
      option.disabled = !item.available;
      select.append(option);
    }
    const available = catalog.curves.find(item => item.available);
    if (!available) throw new Error("No calibration curves are installed in the engine.");
    select.value = available.id; select.disabled = false;
    catalogReady = true;
    byId("connection-status").textContent = `chronologer ${catalog.engine_version} · Connected`;
    restoreProject();
    loadCurve();
  } catch (error) {
    byId("connection-status").textContent = "Engine unavailable";
    select.replaceChildren(new Option("No curves available", ""));
    byId("curve-status").textContent = "Connect to the engine to load calibration curves.";
    showErrors([error.message]);
  }
}
