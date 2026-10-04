// Card anchors are quantile probabilities, increasing from older to younger.
// Legacy presets are interpreted without rewriting saved input snapshots.
export function phaseAnchors(phase, settings = {}) {
  if (phase.anchors != null) return [...phase.anchors];
  if (settings.anchors === 'end_start') return phase.distribution === 'uniform' ? [0, 1] : [.05, .95];
  return [.5];
}
export function phaseEdges(phases, settings = {}) {
  if (settings.edges != null) return settings.edges.map(edge => ({ source: edge.source, target: edge.target }));
  return (settings.ordered ?? settings.anchors !== 'none')
    ? phases.slice(1).map((phase, i) => ({ source: phases[i].id, target: phase.id })) : [];
}
export function phaseSettings(settings = {}, phases = []) {
  return { ordered: settings.ordered ?? settings.anchors !== 'none', delta_scale: settings.delta_scale ?? null,
    edges: phaseEdges(phases, settings) };
}
export function phaseCopy(phase, settings = {}) {
  return { id: phase.id, label: phase.label, distribution: phase.distribution, order: phase.order,
    parameters: phase.parameters, anchors: phaseAnchors(phase, settings) };
}
export function anchorError(phase) {
  const anchors = phase.anchors;
  if (!Array.isArray(anchors) || ![1, 2].includes(anchors.length)
      || anchors.some(p => !Number.isFinite(p) || p < 0 || p > 1)) return 'Enter a required anchor quantile between 0 and 1; the second anchor is optional.';
  if (phase.distribution === 'normal' && anchors.some(p => p <= 0 || p >= 1)) return 'Normal anchors must be strictly between 0 and 1.';
  if (anchors.length === 2 && anchors[0] >= anchors[1]) return 'The younger anchor quantile must exceed the older anchor quantile.';
  return null;
}
