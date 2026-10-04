export const simulating = spec => ['density', 'single_density'].includes(spec.model) && spec.parameters.mode === 'simulate';
export function simulationFor(spec) {
  const p = spec.parameters.simulation ?? {};
  const distribution = p.distribution ?? 'calrcarbon';
  return { n: p.n === undefined ? 10 : p.n, distribution, error: p.error === undefined ? 30 : p.error,
    curve: distribution === 'calrcarbon' ? p.curve === undefined ? 'intcal20' : p.curve : null,
    draws: p.draws === undefined ? 1000 : p.draws };
}
export function simulationError(p) {
  if (!Number.isInteger(p.n) || p.n < 1 || p.n > 100) return 'Simulate between 1 and 100 events per dataset.';
  if (!Number.isInteger(p.draws) || p.draws < 2 || p.draws > 10000) return 'Use 2–10,000 independent predictive replicates.';
  if (!Number.isFinite(p.error) || p.error <= 0) return 'Measurement SD must be positive.';
  if (p.distribution === 'calrcarbon' && !p.curve) return 'Select a calibration curve.';
  return null;
}
export function simulationControls(spec, change) {
  const section = document.createElement('div'); section.className = 'phase-fields simulation-options';
  const p = simulationFor(spec);
  const update = values => { Object.assign(p, values); change({ ...p }, 'distribution' in values); };
  const add = (caption, input) => {
    const label = document.createElement('label'); label.textContent = caption;
    label.append(input); section.append(label);
  };
  for (const [key, caption] of Object.entries({ n: 'Events per dataset (n)', draws: 'Independent predictive replicates', error: 'Measurement SD · years' })) {
    const input = document.createElement('input'); input.type = 'number'; input.step = key === 'error' ? 'any' : '1';
    input.min = key === 'draws' ? '2' : key === 'error' ? '0' : '1';
    if (key !== 'error') input.max = key === 'draws' ? '10000' : '100';
    input.value = p[key]; input.dataset.simulation = key;
    input.addEventListener('input', () => update({ [key]: input.value === '' ? null : Number(input.value) }));
    add(caption, input);
  }
  const family = document.createElement('select'); family.dataset.simulation = 'distribution';
  for (const [value, label] of [['calrcarbon', 'Radiocarbon'], ['normal', 'Normal calendar date'], ['uniform', 'Uniform calendar date']]) family.append(new Option(label, value));
  family.value = p.distribution; family.addEventListener('change', () => update({ distribution: family.value,
    curve: family.value === 'calrcarbon' ? p.curve ?? 'intcal20' : null })); add('Simulated measurement distribution', family);
  if (p.distribution === 'calrcarbon') {
    const curve = document.createElement('select'); curve.dataset.simulation = 'curve';
    for (const option of document.getElementById('curve-select').options) if (option.value) curve.append(option.cloneNode(true));
    if (![...curve.options].some(option => option.value === p.curve)) curve.append(new Option(p.curve, p.curve));
    curve.value = p.curve; curve.addEventListener('change', () => update({ curve: curve.value })); add('Calibration curve', curve);
  }
  const note = document.createElement('p'); note.className = 'help';
  note.textContent = 'Each replicate draws a new location and scale from the displayed hyperpriors, then event dates and measurements. No MCMC or tuning. SD is laboratory error for radiocarbon, calendar error for normal, and uniform half-width / √3. CSV exports the first dataset; only radiocarbon CSVs are currently importable.';
  section.append(note); return section;
}
export function csvDownload(result, title) {
  const button = document.createElement('button'); button.type = 'button'; button.className = 'button secondary simulation-download';
  button.textContent = 'Download simulated dates CSV';
  button.addEventListener('click', () => {
    const rows = result.simulation.events, type = rows[0].distribution;
    const fields = type === 'calrcarbon' ? ['c14_mean', 'c14_err', 'curve'] : type === 'normal' ? ['mean', 'sd'] : ['lower', 'upper'];
    const header = ['id', ...(type === 'calrcarbon' ? [] : ['distribution']), ...fields, 'datum'];
    const quote = value => `"${String(value).replaceAll('"', '""')}"`;
    const text = [header, ...rows.map(row => header.map(key => row[key] ?? row.parameters[key]))]
      .map(row => row.map(quote).join(',')).join('\r\n') + '\r\n';
    const url = URL.createObjectURL(new Blob([text], { type: 'text/csv;charset=utf-8' }));
    const link = document.createElement('a'); link.href = url;
    link.download = `${title.replace(/[<>:"/\\|?*]/g, '_') || 'Simulation'}.csv`; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  return button;
}
