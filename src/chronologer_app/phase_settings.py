"""Data-only phase anchor settings and compatibility with model-wide presets."""
import math


def anchors_for(phase, settings):
    if phase.get('anchors') is not None:
        return list(phase['anchors'])
    if settings.get('anchors') == 'end_start':
        return [0., 1.] if phase['distribution'] == 'uniform' else [.05, .95]
    return [.5]


def ordered(settings):
    value = settings.get('ordered')
    return value if value is not None else settings.get('anchors') != 'none'


def connections(phases, settings):
    """Resolve explicit ID edges, preserving legacy oldest-first chains."""
    edges = settings.get('edges')
    if edges is None:
        return list(zip(phases, phases[1:])) if ordered(settings) else []
    if not isinstance(edges, list) or len(edges) > 100:
        raise ValueError('Phase edges must be a list of at most 100 connections.')
    nodes = {phase['id']: phase for phase in phases}
    seen, outgoing = set(), {node: [] for node in nodes}
    pairs = []
    for edge in edges:
        if (not isinstance(edge, dict) or set(edge) != {'source', 'target'}
                or not all(isinstance(edge[k], str) and edge[k] in nodes for k in ('source', 'target'))):
            raise ValueError('Phase connections require existing source and target IDs.')
        a, b = edge['source'], edge['target']
        if a == b or (a, b) in seen:
            raise ValueError('Phase connections cannot be duplicate or self-connections.')
        seen.add((a, b)); outgoing[a].append(b)
        pairs.append((nodes[a], nodes[b]))
    visited, active = set(), set()
    def visit(node):
        if node in active:
            raise ValueError('Phase connections cannot form cycles.')
        if node in visited:
            return
        active.add(node)
        for target in outgoing[node]:
            visit(target)
        active.remove(node); visited.add(node)
    for node in nodes:
        visit(node)
    return pairs if ordered(settings) else []


def validate_anchors(phase):
    anchors = phase.get('anchors')
    if anchors is None:  # Legacy cards acquire their anchors from the old preset.
        return
    if (not isinstance(anchors, (list, tuple)) or len(anchors) not in (1, 2)
            or any(type(p) not in (int, float) or not math.isfinite(p) or not 0 <= p <= 1 for p in anchors)):
        raise ValueError('Phase anchors require one or two finite quantiles in [0, 1].')
    if phase['distribution'] == 'normal' and any(not 0 < p < 1 for p in anchors):
        raise ValueError('Normal phase anchors must be strictly between 0 and 1.')
    if len(anchors) == 2 and anchors[0] >= anchors[1]:
        raise ValueError('The younger anchor quantile must exceed the older anchor quantile.')
