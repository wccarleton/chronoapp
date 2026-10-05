// Canvas pixels are presentation only. Relationships use stable phase IDs.
const NS = 'http://www.w3.org/2000/svg';
const svgNode = (tag, attrs) => {
  const node = document.createElementNS(NS, tag);
  Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, value));
  return node;
};

export function phaseCanvas(canvas, list, status, { phases, edges, move, connect, remove, busy }) {
  const svg = svgNode('svg', { class: 'phase-edges', 'aria-label': 'Phase connections' });
  const stage = document.createElement('div'); stage.className = 'phase-stage';
  list.before(stage); stage.append(svg, list);
  const toolbar = document.createElement('div'); toolbar.className = 'phase-navigation';
  canvas.before(toolbar);
  let view = { x: 42, y: 32, scale: 1 };
  const zoomLabel = document.createElement('output'); zoomLabel.setAttribute('aria-label', 'Canvas zoom');
  function applyView() {
    stage.style.transform = `translate(${view.x}px, ${view.y}px) scale(${view.scale})`;
    zoomLabel.textContent = `${Math.round(view.scale * 100)}%`;
  }
  function local(clientX, clientY) {
    const bounds = canvas.getBoundingClientRect();
    return { x: clientX - bounds.left - canvas.clientLeft, y: clientY - bounds.top - canvas.clientTop };
  }
  function world(clientX, clientY) {
    const p = local(clientX, clientY);
    return { x: (p.x - view.x) / view.scale, y: (p.y - view.y) / view.scale };
  }
  function zoom(scale, p = { x: canvas.clientWidth / 2, y: canvas.clientHeight / 2 }) {
    if (drag) return;
    const next = Math.max(.1, Math.min(2.5, scale));
    view.x = p.x - (p.x - view.x) * next / view.scale;
    view.y = p.y - (p.y - view.y) * next / view.scale;
    view.scale = next; applyView();
  }
  function reset() { view = { x: 42, y: 32, scale: 1 }; applyView(); }
  function fit() {
    if (!cards().length) { reset(); return; }
    const left = Math.min(...cards().map(card => card.offsetLeft));
    const top = Math.min(...cards().map(card => card.offsetTop));
    const right = Math.max(...cards().map(card => card.offsetLeft + card.offsetWidth));
    const bottom = Math.max(...cards().map(card => card.offsetTop + card.offsetHeight));
    const scale = Math.max(.1, Math.min(1, (canvas.clientWidth - 64) / (right - left), (canvas.clientHeight - 64) / (bottom - top)));
    view = { scale, x: (canvas.clientWidth - (right - left) * scale) / 2 - left * scale,
      y: (canvas.clientHeight - (bottom - top) * scale) / 2 - top * scale };
    applyView();
  }
  for (const [label, id, action] of [['−', 'phase-zoom-out', () => zoom(view.scale / 1.2)],
    ['+', 'phase-zoom-in', () => zoom(view.scale * 1.2)], ['Fit model', 'phase-fit-view', fit], ['Reset view', 'phase-reset-view', reset]]) {
    const button = document.createElement('button'); button.type = 'button'; button.className = 'button secondary';
    button.id = id; button.textContent = label;
    button.setAttribute('aria-label', label === '−' ? 'Zoom out' : label === '+' ? 'Zoom in' : label);
    button.addEventListener('click', () => { if (!drag) action(); }); toolbar.append(button);
  }
  toolbar.append(zoomLabel);
  const hint = document.createElement('span'); hint.className = 'help';
  hint.textContent = 'Drag the background or scroll to pan. Ctrl + scroll zooms at the pointer. Use node grips to move phases.';
  toolbar.append(hint);
  canvas.addEventListener('wheel', event => {
    event.preventDefault(); if (drag) return;
    if (event.ctrlKey || event.metaKey) zoom(view.scale * Math.exp(-event.deltaY * .002), local(event.clientX, event.clientY));
    else {
      const unit = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? canvas.clientHeight : 1;
      view.x -= (event.shiftKey && !event.deltaX ? event.deltaY : event.deltaX) * unit;
      view.y -= (event.shiftKey && !event.deltaX ? 0 : event.deltaY) * unit; applyView();
    }
  }, { passive: false });
  canvas.addEventListener('pointerdown', event => {
    if (event.target.closest('.phase-card') || event.button !== 0 || drag) return;
    start(event, null, 'pan');
  });
  canvas.addEventListener('keydown', event => {
    if (event.target !== canvas || drag) return;
    const delta = { ArrowLeft: [40, 0], ArrowRight: [-40, 0], ArrowUp: [0, 40], ArrowDown: [0, -40] }[event.key];
    if (delta) { event.preventDefault(); view.x += delta[0]; view.y += delta[1]; applyView(); }
    else if (event.key === '+' || event.key === '=') { event.preventDefault(); zoom(view.scale * 1.2); }
    else if (event.key === '-') { event.preventDefault(); zoom(view.scale / 1.2); }
  });
  applyView();
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
    svg.style.left = '0px'; svg.style.top = '0px';
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
    canvas.classList.remove('panning');
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
    if (drag?.kind === 'pan') { view.x = drag.viewX; view.y = drag.viewY; applyView(); }
    cleanup(); source = null; draw();
  }
  function escape(event) { if (event.key === 'Escape') { event.preventDefault(); cancel(); } }
  function start(event, card, kind) {
    if (event.button !== 0 || (kind !== 'pan' && busy()) || drag) return;
    event.preventDefault();
    const id = card?.dataset.phaseId;
    drag = { kind, id, card, handle: event.currentTarget, pointer: event.pointerId,
      clientX: event.clientX, clientY: event.clientY, origin: world(event.clientX, event.clientY),
      viewX: view.x, viewY: view.y, x: card?.offsetLeft, y: card?.offsetTop };
    drag.handle.setPointerCapture(event.pointerId); drag.handle.focus();
    if (kind === 'connection') source = id;
    else if (kind === 'pan') canvas.classList.add('panning');
    else card.classList.add('dragging');
    document.addEventListener('pointermove', pointerMove);
    document.addEventListener('pointerup', pointerUp);
    document.addEventListener('pointercancel', cancel);
    document.addEventListener('keydown', escape);
    window.addEventListener('blur', cancel);
  }
  function pointerMove(event) {
    if (!drag || event.pointerId !== drag.pointer) return;
    if (drag.kind === 'pan') {
      view.x = drag.viewX + event.clientX - drag.clientX;
      view.y = drag.viewY + event.clientY - drag.clientY; applyView(); return;
    }
    const bounds = canvas.getBoundingClientRect();
    if (event.clientY < bounds.top + 30) view.y += 12;
    if (event.clientY > bounds.bottom - 30) view.y -= 12;
    if (event.clientX < bounds.left + 30) view.x += 12;
    if (event.clientX > bounds.right - 30) view.x -= 12;
    applyView();
    const p = world(event.clientX, event.clientY);
    if (drag.kind === 'node') {
      drag.card.style.left = `${Math.max(25, Math.min(100000, drag.x + p.x - drag.origin.x))}px`;
      drag.card.style.top = `${Math.max(25, Math.min(100000, drag.y + p.y - drag.origin.y))}px`;
    } else {
      drag.end = p;
    }
    geometry();
  }
  function pointerUp(event) {
    if (!drag || event.pointerId !== drag.pointer) return;
    const current = drag;
    const target = document.elementFromPoint(event.clientX, event.clientY)?.closest('.phase-input')?.closest('.phase-card')?.dataset.phaseId;
    cleanup();
    if (current.kind === 'node') move(current.id, { x: current.card.offsetLeft, y: current.card.offsetTop });
    else if (current.kind === 'pan') { draw(); return; }
    else if (target) link(target);
    else if (current.end) source = null;
    draw();
  }
  const observer = new ResizeObserver(geometry);
  function bind() {
    if (drag) cancel();
    if (!phases().some(phase => phase.id === source)) source = null;
    observer.disconnect();
    observer.observe(canvas);
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
  function reveal(card) {
    view.x = (canvas.clientWidth - card.offsetWidth * view.scale) / 2 - card.offsetLeft * view.scale;
    view.y = 32 - card.offsetTop * view.scale; applyView();
  }
  return { bind, draw, cancel, reset, reveal };
}
