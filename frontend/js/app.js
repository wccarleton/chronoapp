import { initCalibration } from "./calibrate.js";
import { initProject } from "./project.js";
import { initPhase } from "./phase.js";
import { initPhaseRun } from "./phase-run.js";
import { initSummarize } from "./summarize.js?v=job-monitor-2";
import { initJobs } from "./jobs.js?v=job-monitor-2";

const tabs = [...document.querySelectorAll('.tabs > [role="tab"]')];
function activate(tab) {
  for (const candidate of tabs) {
    const selected = candidate === tab;
    candidate.setAttribute("aria-selected", String(selected));
    candidate.tabIndex = selected ? 0 : -1;
    document.getElementById(candidate.getAttribute("aria-controls")).hidden = !selected;
  }
  document.title = `Chronologer · ${{"project-tab": "Project", "calibrate-tab": "Calibrate", "summarize-tab": "Summarize", "phase-tab": "Phase", "depth-tab": "Depth", "process-tab": "Process Lab"}[tab.id]}`;
}
tabs.forEach((tab, index) => {
  tab.addEventListener("click", () => activate(tab));
  tab.addEventListener("keydown", event => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const next = event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1
      : (index + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length;
    activate(tabs[next]);
    tabs[next].focus();
  });
});
document.getElementById("back-to-calibrate")?.addEventListener("click", () => {
  const tab = document.getElementById("calibrate-tab");
  activate(tab);
  tab.focus();
});
await initProject();
initJobs();
initPhase();
initPhaseRun();
initSummarize();
initSummarize({ process: true });
initCalibration();
