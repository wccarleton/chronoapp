export const MAX_EVENTS = 10000;
export const PAGE_SIZE = 100;

// Bound editable DOM size, while all events remain in semantic project state.
export function pagination(anchor, render, label) {
  let page = 0, total = 0;
  const bar = document.createElement('div'); bar.className = 'event-pagination';
  bar.setAttribute('aria-label', label);
  const previous = document.createElement('button'), next = document.createElement('button');
  previous.type = next.type = 'button';
  previous.textContent = 'Previous'; next.textContent = 'Next';
  previous.className = next.className = 'button secondary';
  const status = document.createElement('span'); status.setAttribute('aria-live', 'polite');
  const jumpLabel = document.createElement('label'); jumpLabel.textContent = 'Page ';
  const jump = document.createElement('input'); jump.type = 'number'; jump.min = '1'; jump.step = '1';
  jump.setAttribute('aria-label', `${label} page`); jumpLabel.append(jump);
  bar.append(previous, status, next, jumpLabel); anchor.before(bar);
  previous.addEventListener('click', () => { page--; render(); });
  next.addEventListener('click', () => { page++; render(); });
  jump.addEventListener('change', () => { page = Math.max(0, Math.trunc(Number(jump.value) || 1) - 1); render(); });
  return {
    last(count) { page = Math.max(0, Math.ceil(count / PAGE_SIZE) - 1); },
    update(count) {
      total = count;
      const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
      page = Math.max(0, Math.min(page, pages - 1));
      bar.hidden = total <= PAGE_SIZE;
      previous.disabled = page === 0; next.disabled = page === pages - 1;
      jump.value = page + 1; jump.max = pages;
      const start = page * PAGE_SIZE;
      status.textContent = `${start + 1}–${Math.min(start + PAGE_SIZE, total)} of ${total.toLocaleString()} events`;
      return start;
    },
  };
}
