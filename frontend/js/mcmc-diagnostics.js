// Portable worker-generated artifacts. Never insert saved SVG markup into the DOM.
function node(tag, text, className) {
  const el = document.createElement(tag);
  if (text !== undefined) el.textContent = text;
  if (className) el.className = className;
  return el;
}
const format = value => value === null || value === undefined ? 'NA' : Number(value).toPrecision(4);

export function createMcmcDiagnostics(container, report) {
  const details = node('details', undefined, 'mcmc-diagnostics');
  details.append(node('summary', 'MCMC diagnostics & chain plots'));
  container.append(details);
  const urls = [];
  if (!report) {
    details.append(node('p', 'This saved run predates MCMC reports. Run the model again to generate diagnostics and chain plots.', 'help'));
    return { dispose() {} };
  }
  let built = false;
  details.addEventListener('toggle', () => {
    if (!details.open || built) return;
    built = true;
    const finiteRhats = report.variables.map(r => r.r_hat).filter(v => v !== null);
    details.append(node('p', `Largest R̂: ${finiteRhats.length ? format(Math.max(...finiteRhats)) : 'NA'}. Retained draws only; diagnostics do not certify convergence.`, 'help'));
    const table = (headers, rows) => {
      const scroll = node('div', undefined, 'mcmc-table-scroll');
      scroll.tabIndex = 0;
      const t = node('table');
      const head = node('thead'), tr = node('tr');
      headers.forEach(h => { const th = node('th', h); th.scope = 'col'; tr.append(th); });
      head.append(tr); t.append(head);
      const body = node('tbody');
      rows.forEach(cells => {
        const row = node('tr');
        cells.forEach(c => row.append(node('td', c)));
        body.append(row);
      });
      t.append(body); scroll.append(t); details.append(scroll);
    };
    table(['Chain', 'Divergences', 'E-BFMI', 'Max depth', 'At depth limit', 'Mean acceptance'], report.chains.map(c =>
      [c.chain, c.divergences ?? 'NA', format(c.bfmi), c.max_tree_depth ?? 'NA', c.reached_max_treedepth ?? 'NA', format(c.acceptance_mean)]));
    table(['Variable', 'R̂', 'ESS bulk', 'ESS tail', 'MCSE mean', 'MCSE SD', ...report.chains.map(c => `Geweke Z · chain ${c.chain}`)],
      report.variables.map(v => [v.variable, ...[v.r_hat, v.ess_bulk, v.ess_tail, v.mcse_mean, v.mcse_sd, ...v.geweke_z].map(format)]));
    report.notes.forEach(note => details.append(node('p', note, 'help')));
    details.append(node('p', Object.entries(report.versions).map(([key, value]) => `${key} ${value}`).join(' · '), 'help'));
    details.append(node('p', 'Reports, messages and vector plots are included when you save this project. Download individual files below. Removing the saved result removes its artifacts from future saves.', 'help'));
    const downloads = node('div', undefined, 'mcmc-downloads');
    const pages = [];
    for (const item of report.artifacts) {
      const bytes = Uint8Array.from(atob(item.data), c => c.charCodeAt(0));
      const url = URL.createObjectURL(new Blob([bytes], { type: item.mime }));
      urls.push(url);
      const link = node('a', item.name);
      link.href = url; link.download = item.name;
      downloads.append(link);
      if (item.mime === 'image/svg+xml') pages.push({ name: item.name, url });
    }
    details.append(downloads);
    if (pages.length) {
      const label = node('label', 'Chain plot page ');
      const select = node('select'); select.setAttribute('aria-label', 'Chain plot page');
      pages.forEach((page, i) => { const option = node('option', `${i + 1} of ${pages.length}`); option.value = i; select.append(option); });
      label.append(select); details.append(label);
      const img = node('img', undefined, 'mcmc-trace-image');
      const show = () => { img.src = pages[Number(select.value)].url; img.alt = `Retained chain traces and per-chain histograms, page ${Number(select.value) + 1}`; };
      select.addEventListener('change', show); show(); details.append(img);
    }
  });
  return { dispose() { urls.forEach(url => URL.revokeObjectURL(url)); } };
}
