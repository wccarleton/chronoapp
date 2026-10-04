"""Adapt validated BP1950 app records to existing engine measurements."""
import chronologer
from chronologer.distributions import calrcarbon
from scipy.stats import norm, uniform


def measurements(rows):
    observations = []
    for row in rows:
        p = row['parameters']
        if row['distribution'] == 'calrcarbon':
            curve = chronologer.load_calcurve(p['curve'], quiet=True)
            observations.append(calrcarbon(curve, -p['c14_mean'], p['c14_err']))
        elif row['distribution'] == 'normal':
            observations.append(norm(-p['mean'], p['sd']))
        else:
            observations.append(uniform(-p['upper'], p['upper'] - p['lower']))
    return observations
