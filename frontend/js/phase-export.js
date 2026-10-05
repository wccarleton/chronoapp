import { profiles, profilePath } from './phase-profile.js';
import { phaseAnchors, phaseEdges, phaseSettings, anchorError } from './phase-settings.js';

const NS = 'http://www.w3.org/2000/svg';
const W = 188, H = 260;
const svgNode = (tag, attrs = {}, text) => {
  const node = document.createElementNS(NS, tag);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
  if (text !== undefined) node.textContent = text;
  return node;
};

// Numerical normal quantile for schematic placement only, never inference.
function normalQuantile(p) {
  const cdf = z => {
    const x = Math.abs(z) / Math.SQRT2, t = 1 / (1 + .3275911 * x);
    const erf = 1 - (((((1.061405429 * t - 1.453152027) * t + 1.421413741) * t
      - .284496736) * t + .254829592) * t) * Math.exp(-x * x);
    return (1 + (z < 0 ? -erf : erf)) / 2;
  };
  let lo = -9, hi = 9;
  for (let i = 0; i < 60; i++) {
    const mid = (lo + hi) / 2;
    if (cdf(mid) < p) lo = mid; else hi = mid;
  }
  return (lo + hi) / 2;
}

export function phaseSvg(project) {
  const phases = project.phases ?? [], settings = project.phase_model?.parameters ?? {};
  if (!phases.length) throw Error('Add at least one phase before exporting.');
  const nodes = phases.map((phase, index) => {
    if (!profiles[phase.distribution]) throw Error(`Unsupported distribution for ${phase.label}.`);
    const anchors = phaseAnchors(phase, settings);
    const error = anchorError({ ...phase, anchors });
    if (error) throw Error(`${phase.label}: ${error}`);
    const scores = anchors.map(p => phase.distribution === 'normal' ? normalQuantile(p) : p);
    const extent = Math.max(10 / 3, ...scores.map(z => Math.abs(z) + .4));
    const position = phase.position ?? { x: 50, y: 50 + (phases.length - index - 1) * 650 };
    return { phase, anchors, scores, extent, x: position.x, y: position.y };
  });
  const left = Math.min(...nodes.map(n => n.x)), top = Math.min(...nodes.map(n => n.y));
  const width = Math.max(...nodes.map(n => n.x)) - left + W + 300;
  const height = Math.max(...nodes.map(n => n.y)) - top + H + 170;
  nodes.forEach(n => { n.x += 100 - left; n.y += 85 - top; });
  const svg = svgNode('svg', { xmlns: NS, viewBox: `0 0 ${width} ${height}`, width, height,
    role: 'img', 'aria-labelledby': 'map-title map-description', 'font-family': 'Arial, sans-serif', 'font-size': 12 });
  const title = project.metadata?.project_name ?? 'Phase model';
  svg.append(svgNode('title', { id: 'map-title' }, `${title} — schematic phase map`),
    svgNode('desc', { id: 'map-description' }, 'Older below, younger above. Distribution silhouettes and quantile anchors are schematic. Positions, sizes and spacing do not express dates, durations or gaps. Connections define relationships; screen positions do not.'));
  const defs = svgNode('defs'), marker = svgNode('marker', { id: 'map-arrow', viewBox: '0 0 10 10',
    refX: 9, refY: 5, markerWidth: 7, markerHeight: 7, orient: 'auto' });
  marker.append(svgNode('path', { d: 'M0 0 L10 5 L0 10 Z', fill: '#315f6b' })); defs.append(marker); svg.append(defs);
  svg.append(svgNode('metadata', {}, JSON.stringify({ phases, edges: phaseEdges(phases, settings),
    ordered: phaseSettings(settings).ordered, schematic: true })));
  const background = svgNode('g', { id: 'timeline', 'aria-label': 'Schematic time direction' });
  for (let y = 85; y <= height - 85; y += 130) background.append(svgNode('line', {
    x1: 70, x2: width - 25, y1: y, y2: y, stroke: '#dce4e6', 'stroke-width': 1 }));
  background.append(svgNode('line', { x1: 45, x2: 45, y1: height - 65, y2: 65,
    stroke: '#315f6b', 'stroke-width': 1.5, 'marker-end': 'url(#map-arrow)' }),
    svgNode('text', { x: 12, y: 48, fill: '#315f6b' }, 'Younger'),
    svgNode('text', { x: 12, y: height - 40, fill: '#315f6b' }, 'Older'),
    svgNode('text', { x: 100, y: height - 30, fill: '#52676e' }, 'Schematic only · no inferred dates, durations or gaps'));
  const titleLines = title.match(new RegExp(`.{1,${Math.max(20, Math.floor((width - 130) / 9))}}`, 'gu')) ?? [''];
  titleLines.forEach((line, i) => background.append(svgNode('text', { x: 100, y: 30 + i * 18,
    fill: '#223b43', 'font-size': 16 }, line)));
  svg.append(background);
  const point = (node, index) => {
    const score = node.scores[index];
    return { x: node.x + W * (node.phase.distribution === 'normal' ? Math.exp(-.5 * score ** 2) : 1),
      y: node.y + H * (node.phase.distribution === 'normal' ? .5 - score / (2 * node.extent) : 1 - score) };
  };
  const enabled = phaseSettings(settings).ordered;
  const connections = svgNode('g', { id: 'connections', 'data-enabled': enabled });
  for (const edge of phaseEdges(phases, settings)) {
    const source = nodes.find(n => n.phase.id === edge.source), target = nodes.find(n => n.phase.id === edge.target);
    if (!source || !target) throw Error('A connection refers to a missing phase.');
    const a = point(source, source.anchors.length - 1), b = point(target, 0);
    const line = svgNode('path', { d: `M${a.x + 5},${a.y} C${a.x + 110},${a.y} ${b.x + 110},${b.y} ${b.x + 5},${b.y}`,
      fill: 'none', stroke: enabled ? '#315f6b' : '#8b999d', 'stroke-width': 2,
      'marker-end': 'url(#map-arrow)', 'data-source': edge.source, 'data-target': edge.target,
      ...(enabled ? {} : { 'stroke-dasharray': '7 5' }) });
    line.append(svgNode('title', {}, `${source.phase.label} q=${source.anchors.at(-1)} → ${target.phase.label} q=${target.anchors[0]}${enabled ? '' : ' (inactive)'}`));
    connections.append(line);
  }
  if (!enabled) background.append(svgNode('text', { x: 100, y: height - 50, fill: '#52676e' }, 'Dashed connections are inactive (Apply connections is off).'));
  svg.append(connections);
  const layer = svgNode('g', { id: 'phases' });
  nodes.forEach((node, index) => {
    const { phase } = node;
    const group = svgNode('g', { id: `phase-node-${index}`, 'data-phase-id': phase.id,
      'data-distribution': phase.distribution, transform: `translate(${node.x} ${node.y})` });
    group.append(svgNode('title', {}, `${phase.label} — ${profiles[phase.distribution].label}`));
    const shape = svgNode('g', { 'data-part': 'distribution' });
    shape.append(svgNode('path', { d: profilePath(phase.distribution, { x: 0, y: 0, width: W, height: H, extent: node.extent }),
      fill: '#d5e9ed', stroke: '#315f6b', 'stroke-width': 1.5 })); group.append(shape);
    const anchors = svgNode('g', { 'data-part': 'anchors' });
    node.anchors.forEach((p, i) => {
      const a = point(node, i), x = a.x - node.x, y = a.y - node.y;
      anchors.append(svgNode('line', { x1: 0, x2: x, y1: y, y2: y, stroke: '#a35028', 'stroke-dasharray': '3 3' }),
        svgNode('circle', { cx: x, cy: y, r: 4, fill: '#a35028', 'data-quantile': p }),
        svgNode('text', { x: x + 9, y: y - 8, fill: '#a35028' }, `q=${p}`));
    }); group.append(anchors);
    const label = svgNode('g', { 'data-part': 'label' });
    const lines = phase.label.match(/.{1,22}/gu) ?? [''];
    lines.forEach((line, i) => label.append(svgNode('text', { x: W / 2, y: H / 2 + (i - (lines.length - 1) / 2) * 12 + 4,
      'text-anchor': 'middle', 'font-size': 10, fill: '#223b43', 'font-weight': 'bold' }, line)));
    group.append(label); layer.append(group);
  });
  svg.append(layer);
  return new XMLSerializer().serializeToString(svg);
}

export function downloadPhaseSvg(project) {
  const text = phaseSvg(project);
  const url = URL.createObjectURL(new Blob([text], { type: 'image/svg+xml;charset=utf-8' }));
  const link = document.createElement('a'); link.href = url;
  link.download = `${(project.metadata?.project_name ?? 'Phase model').replace(/[<>:"/\\|?*]/g, '_')}-phases.svg`;
  link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
}
