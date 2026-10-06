import { projectState as state } from "./project-state.js";
import { phaseAnchors, phaseSettings, phaseEdges, anchorError } from './phase-settings.js';
import { phaseCanvas } from './phase-canvas.js';
import { profiles, profilePath } from './phase-profile.js';
import { downloadPhaseSvg } from './phase-export.js';

// Visual profiles only. The inference adapter consumes state.data.phases:
// Cards retain positions for presentation; phaseCopy excludes them from engine specs.
// Directed edges use stable IDs, never screen position or the card list order.
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
  path.setAttribute("d", profilePath(type));
  svg.append(path);
  return svg;
}

export function initPhase() {
  const list = document.getElementById("phase-list");
  const canvas = document.getElementById("phase-canvas");
  const add = document.getElementById("add-phase");
  const status = document.getElementById("phase-status");
  const orderToggle = document.getElementById('phase-ordered');
  const exportButton = node('button', 'button secondary', 'Export phase map SVG');
  exportButton.type = 'button'; exportButton.id = 'export-phase-svg';
  orderToggle.parentElement.after(exportButton);
  exportButton.addEventListener('click', () => {
    try { downloadPhaseSvg(state.data); status.textContent = 'Schematic phase map exported. Shapes, anchors and connections are editable SVG groups.'; }
    catch (error) { status.textContent = error.message; }
  });
  let ownChange = false;
  let projectDocument = state.data;
  const collapsed = new Set();
  const specs = () => state.data?.phases ?? [];
  const edges = () => phaseEdges(specs(), state.data?.phase_model?.parameters);
  function setEdges(value) { commit(specs(), value); }
  const surface = phaseCanvas(canvas, list, status, {
    phases: specs, edges, busy: () => state.busy,
    move: (id, position) => {
      update(id, { position });
      const card = [...list.children].find(item => item.dataset.phaseId === id);
      card.style.left = `${position.x}px`; card.style.top = `${position.y}px`;
      status.textContent = 'Panel moved; model relationships unchanged.';
    },
    connect: (source, target) => {
      const current = edges();
      if (![source, target].every(id => specs().some(phase => phase.id === id))) return 'Both phases must exist.';
      if (source === target) return 'A phase cannot connect to itself.';
      if (current.some(edge => edge.source === source && edge.target === target)) return 'This connection already exists.';
      if (current.length >= 100) return 'The canvas supports at most 100 connections.';
      const pending = [target], visited = new Set();
      while (pending.length) {
        const id = pending.pop();
        if (id === source) return 'Connections cannot form a cycle.';
        if (visited.has(id)) continue;
        visited.add(id); pending.push(...current.filter(edge => edge.source === id).map(edge => edge.target));
      }
      setEdges([...current, { source, target }]); return null;
    },
    remove: edge => setEdges(edges().filter(item => item.source !== edge.source || item.target !== edge.target)),
  });
  function commit(phases, connections = edges()) {
    ownChange = true;
    const ids = new Set(phases.map(phase => phase.id));
    try { state.setPhaseCanvas(phases, connections.filter(edge => ids.has(edge.source) && ids.has(edge.target))); }
    finally { ownChange = false; }
  }
  function update(id, change) {
    commit(specs().map(phase => phase.id === id ? { ...phase, ...change } : phase));
  }
  function announce(id) {
    const phase = specs().find(item => item.id === id);
    status.textContent = `${phase.label}. Connect its top output to the bottom input of a younger phase.`;
  }
  function render() {
    for (const id of collapsed) if (!specs().some(phase => phase.id === id)) collapsed.delete(id);
    list.replaceChildren();
    document.getElementById("phase-empty").hidden = specs().length > 0;
    add.disabled = !state.data || specs().length >= 100;
    exportButton.disabled = !state.data || !specs().length;
    orderToggle.checked = phaseSettings(state.data?.phase_model?.parameters).ordered;
    orderToggle.disabled = !state.data || state.busy;
    for (const phase of specs()) {
      const card = node("li", "phase-card");
      card.dataset.phaseId = phase.id;
      const grip = node("button", "phase-grip", "⠿");
      grip.type = "button";
      grip.setAttribute("aria-label", `Move ${phase.label} on canvas`);
      const controls = node("div", "phase-fields");
      controls.id = `phase-fields-${phase.id}`;
      const content = node('div', 'phase-content');
      const toggle = node('button', 'phase-toggle', phase.label);
      const membershipBadge = node('span', 'phase-membership');
      toggle.type = 'button'; toggle.setAttribute('aria-controls', controls.id);
      function refreshCollapse() {
        const closed = collapsed.has(phase.id);
        card.classList.toggle('collapsed', closed);
        controls.hidden = closed;
        toggle.setAttribute('aria-expanded', String(!closed));
        toggle.title = `${closed ? 'Expand' : 'Collapse'} phase settings`;
      }
      toggle.addEventListener('click', () => {
        if (collapsed.has(phase.id)) collapsed.delete(phase.id); else collapsed.add(phase.id);
        refreshCollapse(); surface.draw();
      });
      content.append(toggle, membershipBadge, controls); refreshCollapse();
      const nameLabel = node("label", "", "Phase name");
      const input = node("input", "phase-name");
      input.value = phase.label;
      input.maxLength = 120;
      input.addEventListener("input", () => {
        update(phase.id, { label: input.value });
        grip.setAttribute("aria-label", `Move ${input.value} on canvas`);
        toggle.textContent = input.value;
        surface.draw();
      });
      nameLabel.append(input);
      const familyLabel = node("label", "", "Distribution");
      const select = node("select", "phase-distribution");
      for (const [value, profile] of Object.entries(profiles)) select.append(new Option(profile.label, value));
      select.value = phase.distribution;
      select.addEventListener("change", () => {
        update(phase.id, { distribution: select.value });
        card.querySelector("svg").replaceWith(density(select.value));
        refreshAnchors();
      });
      familyLabel.append(select);
      controls.append(nameLabel, familyLabel);
      const anchors = phaseAnchors(phase, state.data?.phase_model?.parameters);
      const olderLabel = node('label', '', 'Anchor quantile · older when two');
      const olderAnchor = node('input', 'phase-anchor');
      olderAnchor.type = 'number'; olderAnchor.step = 'any'; olderAnchor.required = true;
      olderAnchor.value = anchors[0] ?? '';
      const youngerLabel = node('label', '', 'Younger anchor quantile · optional');
      const youngerAnchor = node('input', 'phase-anchor-younger');
      youngerAnchor.type = 'number'; youngerAnchor.step = 'any'; youngerAnchor.value = anchors[1] ?? '';
      youngerAnchor.placeholder = 'Blank: use the sole anchor on both sides';
      olderLabel.append(olderAnchor); youngerLabel.append(youngerAnchor);
      const anchorStatus = node('p', 'help'); anchorStatus.setAttribute('role', 'status');
      function refreshAnchors() {
        const current = specs().find(item => item.id === phase.id);
        const problem = anchorError({ ...current, anchors: phaseAnchors(current, state.data?.phase_model?.parameters) });
        for (const field of [olderAnchor, youngerAnchor]) {
          field.min = '0'; field.max = '1'; field.setCustomValidity(problem ?? '');
        }
        anchorStatus.textContent = problem ?? 'One anchor is shared by both relationships. With two, the younger quantile must be greater than the older. Normal anchors exclude 0 and 1.';
      }
      function changeAnchors() {
        const values = [olderAnchor.value === '' ? null : Number(olderAnchor.value)];
        if (youngerAnchor.value !== '') values.push(Number(youngerAnchor.value));
        update(phase.id, { anchors: values }); refreshAnchors();
      }
      olderAnchor.addEventListener('input', changeAnchors);
      youngerAnchor.addEventListener('input', changeAnchors);
      controls.append(olderLabel, youngerLabel, anchorStatus);
      refreshAnchors();
      const members = () => (state.data?.events ?? []).filter(event => event.label === input.value).length;
      const membership = node('p', 'help');
      function refreshMembership() {
        card.classList.toggle('no-data', members() === 0);
        membershipBadge.hidden = members() > 0;
        membershipBadge.textContent = 'No observed events';
        membership.textContent = members() ? `${members()} project events with this label` : 'No observed events · fitting unobserved phases is not yet supported.';
      }
      refreshMembership(); input.addEventListener('input', refreshMembership);
      const priors = node('details', 'phase-priors');
      priors.append(node('summary', '', 'Phase priors (optional)'));
      for (const [key, caption] of Object.entries({ prior_center: 'Location prior mean · years (BP1950)', prior_scale: 'Location prior SD / reference time scale · years', delta_scale: 'Input delta prior scale · years (non-root phases)' })) {
        const label = node('label', '', caption), field = node('input');
        field.type = 'number'; field.step = 'any'; field.value = phase.parameters[key] ?? '';
        field.placeholder = key === 'delta_scale' ? 'Legacy model setting, otherwise Auto' : 'Auto from labelled measurements';
        if (key !== 'prior_center') field.min = '0';
        field.addEventListener('input', () => {
          const current = specs().find(item => item.id === phase.id);
          update(phase.id, { parameters: { ...current.parameters, [key]: field.value === '' ? null : Number(field.value) } });
        });
        label.append(field); priors.append(label);
      }
      const remove = node('button', 'button secondary', 'Remove phase'); remove.type = 'button';
      remove.addEventListener('click', () => { commit(specs().filter(item => item.id !== phase.id)); render(); });
      controls.append(membership, priors, remove);
      card.append(grip, node("span", "phase-order", String(phase.order + 1)), content, density(phase.distribution));
      list.append(card);
    }
    surface.bind();
  }
  state.addEventListener("change", () => {
    if (!ownChange) {
      surface.cancel();
      if (projectDocument !== state.data) { projectDocument = state.data; collapsed.clear(); surface.reset(); }
      render();
    }
  });
  orderToggle.addEventListener('change', () => {
    if (!state.data || state.busy) return;
    const model = state.data.phase_model ?? { parameters: {} };
    ownChange = true;
    try { state.setPhaseModel({ ...model, parameters: { ...model.parameters, edges: edges(), ordered: orderToggle.checked } }); }
    finally { ownChange = false; }
  });
  add.addEventListener("click", () => {
    if (state.busy || !state.data || specs().length >= 100) return;
    const phase = { id: `phase-${crypto.randomUUID()}`, label: `Phase ${specs().length + 1}`,
      distribution: "uniform", order: specs().length, parameters: {}, anchors: [.5],
      position: { x: specs().length ? Math.min(100000, Math.max(...specs().map(item => item.position?.x ?? 50)) + 480) : 50,
        y: specs().length ? Math.max(25, Math.min(...specs().map(item => item.position?.y ?? 50)) - 150) : 50 } };
    commit([...specs(), phase]); render();
    surface.reveal(list.lastElementChild);
    list.lastElementChild.querySelector("input").focus({ preventScroll: true });
    announce(phase.id);
  });
  render();
}
