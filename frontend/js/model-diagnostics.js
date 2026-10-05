// Compact post-fit scores, shared by Summary and Process Lab.
export function createModelDiagnostics(container, score) {
  const node = (tag, text) => {
    const el = document.createElement(tag);
    if (text !== undefined) el.textContent = text;
    return el;
  };
  const details = node('details'); details.className = 'mcmc-diagnostics';
  details.append(node('summary', 'Model diagnostics'));
  container.append(details);
  if (!score || score.unavailable) {
    details.append(node('p', `WAIC unavailable: ${score?.unavailable ?? 'this saved run predates model diagnostics; rerun to calculate them.'}`));
    return;
  }
  const table = node('table');
  table.className = 'model-diagnostics-table';
  for (const [label, key] of [
    ['WAIC (deviance)', 'waic'], ['WAIC standard error', 'se'],
    ['ELPD WAIC (log scale)', 'elpd_waic'], ['Effective parameters (p WAIC)', 'p_waic'],
    ['Observed events', 'n_events'], ['Predictive units', 'n_units'], ['Retained posterior draws', 'n_samples'],
  ]) {
    const row = node('tr');
    const value = key === 'n_units' ? (score.n_units ?? score.n_events) : score[key];
    row.append(node('th', label), node('td', value == null ? 'Unavailable' :
      key.startsWith('n_') ? String(value) : Number(value).toPrecision(5)));
    table.append(row);
  }
  details.append(table);
  details.append(node('p', 'WAIC compares how well alternative process models predict the observed dating measurements, including radiocarbon determinations; it does not directly evaluate how well they predict the unknown true calendar dates of the events. Comparisons require the same observations and predictive units. For IPPP, prediction also includes the event count over the declared observation window.'));
  if (score.warning) details.append(node('p', 'WAIC reliability warning: a predictive-unit log-likelihood variance exceeds 0.4. Interpret this estimate cautiously.'));
  for (const note of score.notes) details.append(node('p', note));
  details.append(node('p', 'WAIC is not a convergence diagnostic. Inspect MCMC diagnostics and posterior uncertainty.'));
}
