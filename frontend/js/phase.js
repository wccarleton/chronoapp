import { projectState as state } from "./project-state.js";

// Visual profiles only. Future Chronologer adapters consume state.data.phases:
// { id, label, distribution, order, parameters }. No pixel positions or inferred
// boundaries are part of a PhaseSpec. Add renderers here without changing cards.
const profiles = {
  uniform: { label: "Uniform", width: () => 1 },
  normal: { label: "Gaussian / Normal", width: t => Math.exp(-.5 * ((t - .5) / .15) ** 2) },
};
const NS = "http://www.w3.org/2000/svg";
function node(tag, className, text) {
  const item = document.createElement(tag);
  if (className) item.className = className;
  if (text !== undefined) item.textContent = text;
  return item;
}
function density(type) {
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", "0 0 100 120");
  svg.setAttribute("class", "phase-density");
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", `${profiles[type].label} density along vertical time; schematic`);
  const path = document.createElementNS(NS, "path");
  const points = Array.from({ length: 61 }, (_, i) => {
    const t = i / 60;
    return `${(12 + 75 * profiles[type].width(t)).toFixed(2)},${10 + t * 100}`;
  });
  path.setAttribute("d", `M12,10 L${points.join(" L")} L12,110 Z`);
  svg.append(path);
  return svg;
}

export function initPhase() {
  const list = document.getElementById("phase-list");
  const canvas = document.getElementById("phase-canvas");
  const add = document.getElementById("add-phase");
  const status = document.getElementById("phase-status");
  let ownChange = false, drag = null;
  const specs = () => state.data?.phases ?? [];
  // Saved semantic order remains oldest-first; display younger above older.
  const visualSpecs = () => [...specs()].reverse();
  function commit(phases) {
    ownChange = true;
    state.setPhases(phases);
    ownChange = false;
  }
  function update(id, change) {
    commit(specs().map(phase => phase.id === id ? { ...phase, ...change } : phase));
  }
  function announce(id) {
    const phase = specs().find(item => item.id === id);
    status.textContent = `${phase.label}, position ${phase.order + 1} of ${specs().length}, counted from oldest at the bottom.`;
  }
  function render() {
    list.replaceChildren();
    document.getElementById("phase-empty").hidden = specs().length > 0;
    add.disabled = !state.data || specs().length >= 100;
    for (const phase of visualSpecs()) {
      const card = node("li", "phase-card");
      card.dataset.phaseId = phase.id;
      const grip = node("button", "phase-grip", "⠿");
      grip.type = "button";
      grip.setAttribute("aria-label", `Move ${phase.label}; arrow up or down to reorder`);
      grip.title = "Drag vertically, or use arrow keys, to reorder";
      grip.addEventListener("pointerdown", event => startDrag(event, phase.id, card));
      grip.addEventListener("keydown", event => {
        if (!["ArrowUp", "ArrowDown"].includes(event.key) || drag || state.busy) return;
        event.preventDefault();
        const phases = [...specs()];
        const index = phases.findIndex(item => item.id === phase.id);
        const target = Math.max(0, Math.min(phases.length - 1, index + (event.key === "ArrowUp" ? 1 : -1)));
        if (target === index) return;
        phases.splice(target, 0, phases.splice(index, 1)[0]);
        commit(phases); render();
        [...list.children].find(item => item.dataset.phaseId === phase.id).querySelector("button").focus();
        announce(phase.id);
      });
      const controls = node("div", "phase-fields");
      const nameLabel = node("label", "", "Phase name");
      const input = node("input", "phase-name");
      input.value = phase.label;
      input.maxLength = 120;
      input.addEventListener("input", () => {
        update(phase.id, { label: input.value });
        grip.setAttribute("aria-label", `Move ${input.value}; arrow up or down to reorder`);
      });
      nameLabel.append(input);
      const familyLabel = node("label", "", "Distribution");
      const select = node("select", "phase-distribution");
      for (const [value, profile] of Object.entries(profiles)) select.append(new Option(profile.label, value));
      select.value = phase.distribution;
      select.addEventListener("change", () => {
        update(phase.id, { distribution: select.value });
        card.querySelector("svg").replaceWith(density(select.value));
      });
      familyLabel.append(select);
      controls.append(nameLabel, familyLabel);
      card.append(grip, node("span", "phase-order", String(phase.order + 1)), controls, density(phase.distribution));
      list.append(card);
    }
  }
  function startDrag(event, id, card) {
    if (event.button !== 0 || state.busy || drag) return;
    event.preventDefault();
    event.currentTarget.focus();
    drag = { id, card, grip: event.currentTarget, pointer: event.pointerId, offset: event.clientY - card.getBoundingClientRect().top,
      phases: visualSpecs(), original: visualSpecs().map(item => item.id).join() };
    drag.grip.setPointerCapture(event.pointerId);
    card.classList.add("dragging");
    document.addEventListener("pointermove", moveDrag);
    document.addEventListener("pointerup", finishDrag);
    document.addEventListener("pointercancel", cancelDrag);
    document.addEventListener("keydown", escapeDrag);
    window.addEventListener("blur", cancelDrag);
  }
  function moveDrag(event) {
    if (!drag || event.pointerId !== drag.pointer) return;
    event.preventDefault();
    const bounds = canvas.getBoundingClientRect();
    if (event.clientY < bounds.top + 35) canvas.scrollTop -= 12;
    if (event.clientY > bounds.bottom - 35) canvas.scrollTop += 12;
    const y = event.clientY - list.getBoundingClientRect().top;
    const others = [...list.children].filter(card => card !== drag.card);
    const index = others.filter(card => y > card.offsetTop + card.offsetHeight / 2).length;
    const current = drag.phases.findIndex(phase => phase.id === drag.id);
    if (index !== current) {
      const previous = new Map(others.map(card => [card, card.offsetTop]));
      drag.phases.splice(index, 0, drag.phases.splice(current, 1)[0]);
      list.insertBefore(drag.card, others[index] ?? null);
      drag.grip.setPointerCapture(drag.pointer);
      if (!window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
        others.forEach(card => card.animate([
          { transform: `translateY(${previous.get(card) - card.offsetTop}px)` }, { transform: "translateY(0)" },
        ], { duration: 160, easing: "ease-out" }));
      }
      [...list.children].forEach((card, order) => { card.querySelector(".phase-order").textContent = list.children.length - order; });
    }
    drag.card.style.transform = `translateY(${y - drag.card.offsetTop - drag.offset}px)`;
  }
  function cleanup() {
    document.removeEventListener("pointermove", moveDrag);
    document.removeEventListener("pointerup", finishDrag);
    document.removeEventListener("pointercancel", cancelDrag);
    document.removeEventListener("keydown", escapeDrag);
    window.removeEventListener("blur", cancelDrag);
    drag = null;
  }
  function finishDrag(event) {
    if (!drag || event.pointerId !== drag.pointer) return;
    const { id, phases, original } = drag;
    cleanup();
    if (phases.map(item => item.id).join() !== original) commit([...phases].reverse());
    render();
    [...list.children].find(item => item.dataset.phaseId === id)?.querySelector("button").focus({ preventScroll: true });
    announce(id);
  }
  function cancelDrag() { if (drag) { cleanup(); render(); } }
  function escapeDrag(event) { if (event.key === "Escape") { event.preventDefault(); cancelDrag(); } }
  state.addEventListener("change", () => { if (!ownChange) { cancelDrag(); render(); } });
  add.addEventListener("click", () => {
    if (state.busy || !state.data || specs().length >= 100) return;
    const phase = { id: `phase-${crypto.randomUUID()}`, label: `Phase ${specs().length + 1}`,
      distribution: "uniform", order: specs().length, parameters: {} };
    commit([...specs(), phase]); render();
    list.firstElementChild.scrollIntoView({ block: "nearest" });
    list.firstElementChild.querySelector("input").focus({ preventScroll: true });
    announce(phase.id);
  });
  render();
}
