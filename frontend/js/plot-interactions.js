// Viewport geometry only: these operations never alter the supplied plot data.
export function moveView(view, from, to, factor = 1) {
  const xSpan = (view.x[1] - view.x[0]) * factor;
  const ySpan = (view.y[1] - view.y[0]) * factor;
  const anchorX = view.x[0] + from.x * (view.x[1] - view.x[0]);
  const anchorY = view.y[1] - from.y * (view.y[1] - view.y[0]);
  const next = {
    x: [anchorX - to.x * xSpan, anchorX + (1 - to.x) * xSpan],
    y: [anchorY - (1 - to.y) * ySpan, anchorY + to.y * ySpan],
  };
  // Bound extreme gestures to keep SVG coordinates and tick arithmetic useful.
  if (xSpan < .001 || xSpan > 1e7 || ySpan < 1e-15 || ySpan > 1e12
      || ![...next.x, ...next.y].every(Number.isFinite)
      || next.x.some(value => Math.abs(value) > 1e9)) return view;
  return next;
}

export function bindPlotInteractions(svg, { point, getView, setView, reset }) {
  const pointers = new Map();
  const center = { x: .5, y: .5 };
  const inside = p => p.x >= 0 && p.x <= 1 && p.y >= 0 && p.y <= 1;
  function gesture() {
    const points = [...pointers.values()];
    const a = points[0], b = points[1] ?? a;
    return {
      midpoint: point((a.x + b.x) / 2, (a.y + b.y) / 2),
      distance: Math.hypot(a.x - b.x, a.y - b.y),
    };
  }
  svg.addEventListener("pointerdown", event => {
    if (event.button !== 0 || !inside(point(event.clientX, event.clientY))) return;
    if (pointers.size >= 2) return;
    event.preventDefault();
    svg.focus({ preventScroll: true });
    pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
    svg.setPointerCapture(event.pointerId);
    svg.classList.add("is-dragging");
  });
  svg.addEventListener("pointermove", event => {
    if (!pointers.has(event.pointerId)) return;
    const before = gesture();
    pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
    const after = gesture();
    const factor = before.distance > 5 && after.distance > 5
      ? before.distance / after.distance : 1;
    setView(moveView(getView(), before.midpoint, after.midpoint, factor));
  });
  function end(event) {
    pointers.delete(event.pointerId);
    if (svg.hasPointerCapture(event.pointerId)) svg.releasePointerCapture(event.pointerId);
    if (!pointers.size) svg.classList.remove("is-dragging");
  }
  svg.addEventListener("pointerup", end);
  svg.addEventListener("pointercancel", end);
  svg.addEventListener("lostpointercapture", end);
  svg.addEventListener("wheel", event => {
    const anchor = point(event.clientX, event.clientY);
    if (!inside(anchor)) return;
    event.preventDefault();
    const delta = event.deltaY * (event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? 300 : 1);
    const factor = Math.exp(Math.max(-1, Math.min(1, delta * .002)));
    setView(moveView(getView(), anchor, anchor, factor));
  }, { passive: false });
  svg.addEventListener("keydown", event => {
    const shift = { ArrowLeft: [.1, 0], ArrowRight: [-.1, 0], ArrowUp: [0, .1], ArrowDown: [0, -.1] }[event.key];
    if (shift) {
      event.preventDefault();
      setView(moveView(getView(), center, { x: center.x + shift[0], y: center.y + shift[1] }));
    } else if (["+", "=", "-", "Home"].includes(event.key)) {
      event.preventDefault();
      if (event.key === "Home") reset();
      else setView(moveView(getView(), center, center, event.key === "-" ? 1.25 : .8));
    }
  });
}
