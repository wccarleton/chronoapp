// Run before styles load so a saved dark preference never flashes a light page.
(() => {
  const key = "chronologer-theme";
  const system = window.matchMedia("(prefers-color-scheme: dark)");
  const iconVersion = Date.now().toString();
  let preference = null;
  try {
    const saved = localStorage.getItem(key);
    if (saved === "light" || saved === "dark") preference = saved;
  } catch { /* Theme switching still works when storage is unavailable. */ }

  function apply() {
    const theme = preference ?? (system.matches ? "dark" : "light");
    document.documentElement.dataset.theme = theme;
    const icon = document.querySelector("img.brand-mark");
    if (icon) {
      const url = new URL(`assets/chronologer_icon_${theme}.png`, document.baseURI);
      url.searchParams.set("v", iconVersion);
      if (icon.src !== url.href) icon.src = url.href;
    }
    const button = document.getElementById("theme-toggle");
    if (button) {
      button.setAttribute("aria-pressed", String(theme === "dark"));
      button.title = `Switch to ${theme === "dark" ? "light" : "dark"} mode`;
    }
  }
  apply();
  system.addEventListener("change", () => { if (!preference) apply(); });
  window.addEventListener("storage", event => {
    if (event.key !== key && event.key !== null) return;
    preference = event.newValue === "light" || event.newValue === "dark" ? event.newValue : null;
    apply();
  });
  document.addEventListener("DOMContentLoaded", () => {
    apply();
    document.getElementById("theme-toggle").addEventListener("click", () => {
      preference = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
      try { localStorage.setItem(key, preference); } catch { /* Session-only preference. */ }
      apply();
    });
  });
})();
