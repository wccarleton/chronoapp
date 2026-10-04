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
