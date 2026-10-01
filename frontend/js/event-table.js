import { projectState as state } from "./project-state.js";
import { getCurves } from "./api.js";

// UI parameter slots retain their original names in project data. These choices
// describe event inputs only; they do not introduce new inference models.
const families = {
  calrcarbon: { label: "Radiocarbon", parameters: { c14_mean: null, c14_err: null } },
  normal: { label: "Normal", parameters: { mean: null, sd: null } },
  uniform: { label: "Uniform", parameters: { lower: null, upper: null } },
};
const captions = { c14_mean: "¹⁴C age BP", c14_err: "Error (1σ)", mean: "Mean (cal BP)", sd: "SD (years)", lower: "Lower (cal BP)", upper: "Upper (cal BP)" };

export function fillCurveChoices(select, catalog, value) {
  select.replaceChildren();
  for (const item of catalog) {
    const option = new Option(`${item.label}${item.available ? "" : " · not installed"}`, item.id);
    option.disabled = !item.available; select.append(option);
  }
  if (value && !catalog.some(item => item.id === value)) {
    const option = new Option(`${value} · unavailable`, value);
    option.disabled = true; select.append(option);
  }
  select.value = value ?? "";
}

export function initEventTable() {
  const rows = document.getElementById("project-events");
  const add = document.getElementById("add-event");
  let catalog = [], ownChange = false, previousEvents = "";
  function change(action) {
    ownChange = true;
    try { action(); previousEvents = JSON.stringify(state.data?.events); }
    finally { ownChange = false; }
  }
  function render() {
    previousEvents = JSON.stringify(state.data?.events);
    rows.replaceChildren();
    const events = state.data?.events ?? [];
    add.disabled = !state.data || events.length >= 100;
    events.forEach((event, index) => {
      const row = document.createElement("tr"); row.dataset.eventIndex = index;
      function cell() { const td = document.createElement("td"); row.append(td); return td; }
      function input(field, value, update, type = "text") {
        const td = cell(), node = document.createElement("input");
        node.type = type; node.value = value ?? ""; node.dataset.field = field;
        node.setAttribute("aria-label", `${field}, event ${index + 1}`);
        if (type === "number") node.step = "any"; else node.maxLength = 120;
        node.addEventListener("input", () => change(() => update(node.value)));
        td.append(node); return { td, node };
      }
      input("id", event.id, id => state.updateEvent(index, { id }));
      input("label", event.label, label => state.updateEvent(index, { label }));
      const datumCell = cell(), datum = document.createElement("select");
      datum.dataset.field = "datum"; datum.setAttribute("aria-label", `Datum, event ${index + 1}`);
      for (const value of ["BP1950", "BCAD"]) datum.append(new Option(value, value));
      datum.value = event.datum ?? "BP1950";
      datum.addEventListener("change", () => {
        change(() => state.updateEvent(index, { datum: datum.value })); render();
      });
      datumCell.append(datum);
      const familyCell = cell(), family = document.createElement("select");
      family.dataset.field = "distribution";
      family.setAttribute("aria-label", `Distribution, event ${index + 1}`);
      for (const [key, definition] of Object.entries(families)) family.append(new Option(`${definition.label} (${key})`, key));
      if (!families[event.distribution]) family.append(new Option(event.distribution, event.distribution));
      family.value = event.distribution;
      family.addEventListener("change", () => {
        const current = state.data.events[index], definition = families[family.value];
        if (!definition || family.value === current.distribution) return;
        if (Object.values(current.parameters).some(value => value !== null && value !== "")
            && !window.confirm("Changing the distribution clears this event's parameters. Continue?")) {
          family.value = current.distribution; return;
        }
        const parameters = { ...definition.parameters };
        if (family.value === "calrcarbon") parameters.curve = state.defaultCurve || catalog.find(item => item.available)?.id || "intcal20";
        change(() => state.updateEvent(index, { distribution: family.value, parameters })); render();
      });
      familyCell.append(family);
      const keys = event.distribution === "calrcarbon" ? ["c14_mean", "c14_err"] : Object.keys(event.parameters);
      for (let slot = 0; slot < 3; slot++) {
        const key = keys[slot], value = key ? event.parameters[key] : null;
        const numeric = value === null || typeof value === "number";
        const { td, node } = input(`p${slot + 1}`, numeric ? value : JSON.stringify(value), raw => {
          const current = state.data.events[index];
          state.updateEvent(index, { parameters: { ...current.parameters, [key]: raw === "" ? null : Number(raw) } });
        }, numeric ? "number" : "text");
        node.disabled = !key;
        node.readOnly = !numeric;
        if (key) {
          node.dataset.parameter = key;
          const hint = document.createElement("small"); hint.textContent = captions[key] || key;
          if (event.datum === "BCAD" && event.distribution !== "calrcarbon") hint.textContent = hint.textContent.replace("cal BP", "BCAD");
          if (!numeric) hint.textContent += " · preserved, read-only";
          td.append(hint); node.setAttribute("aria-label", `${captions[key] || key}, event ${index + 1}`);
        } else node.placeholder = "—";
      }
      const curveCell = cell();
      if (event.distribution === "calrcarbon") {
        const curve = document.createElement("select"); curve.dataset.field = "curve";
        curve.setAttribute("aria-label", `Calibration curve, event ${index + 1}`);
        fillCurveChoices(curve, catalog, event.parameters.curve);
        curve.addEventListener("change", () => change(() => {
          const current = state.data.events[index];
          state.updateEvent(index, { parameters: { ...current.parameters, curve: curve.value } });
        }));
        curveCell.append(curve);
      } else curveCell.textContent = "—";
      const remove = document.createElement("button"); remove.type = "button"; remove.className = "remove-row";
      remove.textContent = "×"; remove.setAttribute("aria-label", `Remove event ${index + 1}`);
      remove.addEventListener("click", () => { change(() => state.removeEvent(index)); render(); });
      cell().append(remove);
      if (keys.length > 3) {
        const note = document.createElement("small"); note.textContent = `+${keys.length - 3} parameters preserved`;
        familyCell.append(note);
      }
      rows.append(row);
    });
  }
  add.addEventListener("click", () => {
    if (!state.data || state.busy || state.data.events.length >= 100) return;
    change(() => state.setEvents([...state.data.events, {
      id: `Event ${state.data.events.length + 1}`, label: "", datum: "BP1950", distribution: "calrcarbon",
      parameters: { ...families.calrcarbon.parameters, curve: state.defaultCurve || catalog.find(item => item.available)?.id || "intcal20" },
    }]));
    render(); rows.lastElementChild.querySelector("input").focus();
  });
  state.addEventListener("change", () => {
    if (!ownChange && previousEvents !== JSON.stringify(state.data?.events)) render();
  });
  getCurves().then(response => { catalog = response.curves; render(); }).catch(() => { /* Stored curve IDs stay visible. */ });
  render();
}
