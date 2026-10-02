// Shared by Bayesian model UIs. Burn-in is PyMC tuning, not extra post-hoc trimming.
export const DEFAULT_SAMPLING = Object.freeze({ draws: 1000, tune: 1000, chains: 4 });
export function samplingFor(spec) {
  const recorded = spec.result?.sampling ?? spec.saved_run?.result.sampling;
  const values = spec.parameters.sampling ?? recorded ?? DEFAULT_SAMPLING;
  return Object.fromEntries(Object.entries(DEFAULT_SAMPLING).map(([key, fallback]) =>
    [key, values[key] === undefined ? fallback : values[key]]));
}
export function samplingError(settings) {
  return Object.entries(settings).some(([key, value]) => !Number.isSafeInteger(value) || value < (key === 'tune' ? 0 : 1))
    ? 'Sampling counts must be whole numbers: draws and chains at least 1; burn-in/tuning at least 0.' : null;
}
export function samplingControls(settings, onChange) {
  const section = document.createElement('details'); section.className = 'sampling-settings';
  const title = document.createElement('summary'); section.append(title);
  const values = { ...settings };
  const refresh = () => { title.textContent = `MCMC sampling · ${values.draws ?? '—'} draws + ${values.tune ?? '—'} tuning per chain · ${values.chains ?? '—'} chains`; };
  refresh();
  const warning = document.createElement('p'); warning.className = 'help';
  warning.textContent = 'Advanced settings: only change these if you understand their effect on MCMC sampling. Too little tuning or too few draws/chains can give unreliable results; larger values increase runtime, memory and report size. Defaults are a starting point, not a convergence guarantee. Always inspect diagnostics.';
  section.append(warning);
  const fields = document.createElement('div'); fields.className = 'phase-fields';
  for (const [key, caption] of Object.entries({ draws: 'Retained draws per chain', tune: 'Burn-in / tuning per chain', chains: 'Number of chains' })) {
    const label = document.createElement('label'); label.textContent = caption;
    const input = document.createElement('input'); input.type = 'number'; input.step = '1';
    input.min = key === 'tune' ? '0' : '1'; input.value = values[key] ?? ''; input.dataset.sampling = key;
    input.addEventListener('input', () => { values[key] = input.value === '' ? null : Number(input.value); refresh(); onChange({ ...values }); });
    label.append(input); fields.append(label);
  }
  section.append(fields);
  const explanation = document.createElement('p'); explanation.className = 'help';
  explanation.textContent = 'Burn-in means PyMC warmup/tuning: those iterations adapt the sampler and are discarded. Draws are the additional retained iterations in each chain. One chain cannot provide between-chain R̂. Chains currently run sequentially within each inference worker.';
  section.append(explanation);
  return section;
}
