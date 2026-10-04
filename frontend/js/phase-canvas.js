// Canvas pixels are presentation only. Relationships use stable phase IDs.
const NS = 'http://www.w3.org/2000/svg';
const svgNode = (tag, attrs) => {
  const node = document.createElementNS(NS, tag);
  Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, value));
  return node;
};

export function phaseCanvas(canvas, list, status, { phases, edges, move, connect, remove, busy }) {
  const svg = svgNode('svg', { class: 'phase-edges', 'aria-label': 'Phase connections' });
  list.before(svg);
  const relationships = document.createElement('div');
  relationships.className = 'phase-connections'; canvas.after(relationships);
  let drag = null, source = null;
  const cards = () => [...list.children];
  const cardFor = id => cards().find(card => card.dataset.phaseId === id);
  function point(id, output) {
    const card = cardFor(id);
    if (!card) return null;
    return { x: card.offsetLeft + card.offsetWidth / 2,
      y: card.offsetTop + (output ? 0 : card.offsetHeight) };
  }
  function curve(a, b) {
    const offset = Math.max(45, Math.abs(b.y - a.y) / 2);
    return `M${a.x},${a.y} C${a.x},${a.y - offset} ${b.x},${b.y + offset} ${b.x},${b.y}`;
  }
  function geometry() {
    svg.style.left = `${list.offsetLeft}px`; svg.style.top = `${list.offsetTop}px`;
    const width = Math.max(canvas.clientWidth - 40, ...cards().map(card => card.offsetLeft + card.offsetWidth + 50));
    const height = Math.max(400, ...cards().map(card => card.offsetTop + card.offsetHeight + 50));
    list.style.width = `${width}px`; list.style.height = `${height}px`;
    svg.setAttribute('width', width); svg.setAttribute('height', height);
    svg.replaceChildren();
    const defs = svgNode('defs', {}), marker = svgNode('marker', { id: 'phase-arrow', viewBox: '0 0 10 10',
      refX: 9, refY: 5, markerWidth: 7, markerHeight: 7, orient: 'auto-start-reverse' });
    marker.append(svgNode('path', { d: 'M0 0 L10 5 L0 10 Z', fill: 'var(--accent)' })); defs.append(marker); svg.append(defs);
    for (const edge of edges()) {
      const a = point(edge.source, true), b = point(edge.target, false);
      if (!a || !b) continue;
      const line = svgNode('path', { d: curve(a, b), class: 'phase-edge', 'marker-end': 'url(#phase-arrow)',
        'data-source': edge.source, 'data-target': edge.target });
      svg.append(line);
    }
    if (drag?.kind === 'connection' && drag.end) {
      svg.append(svgNode('path', { d: curve(point(drag.id, true), drag.end), class: 'phase-edge pending' }));
    }
  }
  function draw() {
    geometry(); relationships.replaceChildren();
    for (const edge of edges()) {
      const a = phases().find(p => p.id === edge.source), b = phases().find(p => p.id === edge.target);
      if (!a || !b) continue;
      const button = document.createElement('button'); button.type = 'button'; button.className = 'button secondary';
      button.textContent = `${a.label} → ${b.label} ×`; button.title = 'Delete connection';
      button.setAttribute('aria-label', `Delete connection ${a.label} to ${b.label}`);
      button.disabled = busy(); button.addEventListener('click', () => { remove(edge); source = null; draw(); });
      relationships.append(button);
    }
    cards().forEach(card => card.classList.toggle('connecting', card.dataset.phaseId === source));
  }
  function link(target) {
    if (!source || busy()) return;
    const problem = connect(source, target);
    status.textContent = problem ?? 'Connection created. Source is older; target is younger.';
    source = null; draw();
  }
  function cleanup() {
    if (drag?.handle.hasPointerCapture(drag.pointer)) drag.handle.releasePointerCapture(drag.pointer);
    cards().forEach(card => card.classList.remove('dragging'));
    document.removeEventListener('pointermove', pointerMove);
    document.removeEventListener('pointerup', pointerUp);
    document.removeEventListener('pointercancel', cancel);
    document.removeEventListener('keydown', escape);
    window.removeEventListener('blur', cancel);
    drag = null;
  }
  function cancel() {
    if (drag?.kind === 'node') {
      drag.card.style.left = `${drag.x}px`; drag.card.style.top = `${drag.y}px`;
    }
    cleanup(); source = null; draw();
  }
  function escape(event) { if (event.key === 'Escape') { event.preventDefault(); cancel(); } }
  function start(event, card, kind) {
    if (event.button !== 0 || busy() || drag) return;
    event.preventDefault();
    const id = card.dataset.phaseId;
    drag = { kind, id, card, handle: event.currentTarget, pointer: event.pointerId,
      clientX: event.clientX, clientY: event.clientY, scrollX: canvas.scrollLeft, scrollY: canvas.scrollTop,
      x: card.offsetLeft, y: card.offsetTop };
    drag.handle.setPointerCapture(event.pointerId); drag.handle.focus();
    if (kind === 'connection') source = id; else card.classList.add('dragging');
    document.addEventListener('pointermove', pointerMove);
    document.addEventListener('pointerup', pointerUp);
    document.addEventListener('pointercancel', cancel);
    document.addEventListener('keydown', escape);
    window.addEventListener('blur', cancel);
  }
  function pointerMove(event) {
    if (!drag || event.pointerId !== drag.pointer) return;
    const bounds = canvas.getBoundingClientRect();
    if (event.clientY < bounds.top + 30) canvas.scrollTop -= 12;
    if (event.clientY > bounds.bottom - 30) canvas.scrollTop += 12;
    if (drag.kind === 'node') {
      drag.card.style.left = `${Math.max(25, Math.min(100000, drag.x + event.clientX - drag.clientX + canvas.scrollLeft - drag.scrollX))}px`;
      drag.card.style.top = `${Math.max(25, Math.min(100000, drag.y + event.clientY - drag.clientY + canvas.scrollTop - drag.scrollY))}px`;
    } else {
      const origin = list.getBoundingClientRect();
      drag.end = { x: event.clientX - origin.left, y: event.clientY - origin.top };
    }
    geometry();
  }
  function pointerUp(event) {
    if (!drag || event.pointerId !== drag.pointer) return;
    const current = drag;
    const target = document.elementFromPoint(event.clientX, event.clientY)?.closest('.phase-input')?.closest('.phase-card')?.dataset.phaseId;
    cleanup();
    if (current.kind === 'node') move(current.id, { x: current.card.offsetLeft, y: current.card.offsetTop });
    else if (target) link(target);
    else if (current.end) source = null;
    draw();
  }
  const observer = new ResizeObserver(geometry);
  function bind() {
    if (drag) cancel();
    if (!phases().some(phase => phase.id === source)) source = null;
    observer.disconnect();
    cards().forEach((card, index) => {
      const phase = phases().find(p => p.id === card.dataset.phaseId);
      const position = phase.position ?? { x: 50, y: 50 + (phases().length - index - 1) * 650 };
      card.style.left = `${position.x}px`; card.style.top = `${position.y}px`;
      const grip = card.querySelector('.phase-grip');
      grip.title = 'Drag to move; arrow keys move the panel; Escape cancels';
      grip.setAttribute('aria-label', `Move ${phase.label} on canvas`);
      grip.addEventListener('pointerdown', event => start(event, card, 'node'));
      grip.addEventListener('keydown', event => {
        if (!['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(event.key) || busy()) return;
        event.preventDefault();
        move(phase.id, { x: Math.min(100000, Math.max(25, card.offsetLeft + (event.key === 'ArrowLeft' ? -20 : event.key === 'ArrowRight' ? 20 : 0))),
          y: Math.min(100000, Math.max(25, card.offsetTop + (event.key === 'ArrowUp' ? -20 : event.key === 'ArrowDown' ? 20 : 0))) });
        geometry();
      });
      for (const output of [false, true]) {
        const port = document.createElement('button'); port.type = 'button';
        port.className = `phase-port ${output ? 'phase-output' : 'phase-input'}`;
        port.title = output ? 'Output: drag to a younger phase input' : 'Input: connect from an older phase output';
        port.setAttribute('aria-label', `${phase.label} ${output ? 'output' : 'input'} connector`);
        if (output) {
          port.addEventListener('pointerdown', event => start(event, card, 'connection'));
          port.addEventListener('click', event => { if (event.detail === 0) { source = phase.id; draw(); } });
        } else port.addEventListener('click', () => link(phase.id));
        card.append(port);
      }
      observer.observe(card);
    });
    draw();
  }
  return { bind, draw, cancel };
}
