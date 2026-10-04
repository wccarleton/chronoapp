import { request } from "./api.js";

const active = job => ["queued", "running"].includes(job.status);
const dismissed = new Set();
// Only show runs submitted here or observed active during this page's lifetime.
// The server retains finished runs for log access, not as startup notifications.
const observed = new Set();
let jobs = [], selectedLog = null, lastOverview = "", polling = false;
function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}
function button(text, action) {
  const node = element("button", text, "button secondary");
  node.type = "button"; node.addEventListener("click", action); return node;
}
async function showLog(job) {
  selectedLog = job.id;
  const panel = document.getElementById("run-log"); panel.hidden = false; panel.open = true;
  document.getElementById("run-log-location").textContent = job.log_path;
  await refreshLog();
}
async function refreshLog() {
  if (!selectedLog || !document.getElementById("run-log").open) return;
  const id = selectedLog;
  try {
    const response = await fetch(`/api/jobs/${id}/log`);
    if (!response.ok) throw new Error("Log unavailable; the server may have restarted.");
    const text = await response.text();
    if (id === selectedLog) document.getElementById("run-log-text").textContent = text;
  } catch (error) { document.getElementById("run-log-text").textContent = error.message; }
}
function render(maxWorkers = 2) {
  const visible = jobs.filter(job => observed.has(job.id) && !dismissed.has(job.id));
  document.getElementById("run-monitor").hidden = !visible.length;
  const running = jobs.filter(job => job.status === "running").length;
  const queued = jobs.filter(job => job.status === "queued").length;
  const overview = running || queued ? `Inference: ${running} running · ${queued} queued · up to ${maxWorkers} workers` : "Inference finished · results and logs below";
  if (overview !== lastOverview) { document.getElementById("run-overview").textContent = overview; lastOverview = overview; }
  const list = document.getElementById("run-list");
  // Keep existing controls in place while progress updates, preserving focus.
  for (const row of [...list.children]) if (!visible.some(job => job.id === row.dataset.jobId)) row.remove();
  for (const job of visible) {
    let row = [...list.children].find(row => row.dataset.jobId === job.id);
    if (!row) {
      row = element("div", undefined, "run-row"); row.dataset.jobId = job.id;
      const text = element("span", "", "run-description");
      const progress = element("progress"); progress.setAttribute("aria-label", `Sampling progress: ${job.label}`);
      const log = button("Messages", () => showLog(job));
      const download = element("a", "Download log"); download.href = `/api/jobs/${job.id}/log?download=true`;
      const cancel = button("Cancel", async () => {
        cancel.disabled = true;
        try { await request(`/jobs/${job.id}/cancel`, { method: "POST" }); await refresh(); }
        catch (error) { text.textContent = error.message; cancel.disabled = false; }
      }); cancel.classList.add("run-cancel");
      const dismiss = button("Dismiss", () => { dismissed.add(job.id); if (selectedLog === job.id) { selectedLog = null; document.getElementById("run-log").hidden = true; } render(maxWorkers); });
      dismiss.classList.add("run-dismiss");
      row.append(text, progress, log, download, cancel, dismiss); list.append(row);
    }
    const count = job.total && job.completed > 0 ? ` · ${job.completed}/${job.total} tuning + draws` : "";
    row.querySelector(".run-description").textContent = `${job.label} — ${job.stage}${count} · ${Math.floor(job.elapsed_seconds)} s${job.error ? ` · ${job.error}` : ""}`;
    const progress = row.querySelector("progress");
    if (job.status === "completed") { progress.max = 1; progress.value = 1; }
    else if (job.total && job.completed > 0) { progress.max = job.total; progress.value = job.completed; }
    else progress.removeAttribute("value");
    progress.hidden = ["failed", "cancelled"].includes(job.status);
    row.querySelector(".run-cancel").hidden = !active(job);
    row.querySelector(".run-cancel").disabled = job.stage === "Cancelling";
    row.querySelector(".run-dismiss").hidden = active(job);
  }
}
async function refresh() {
  if (polling) return;
  polling = true;
  try {
    const response = await request("/jobs"); jobs = response.jobs;
    jobs.filter(active).forEach(job => observed.add(job.id));
    render(response.max_workers); await refreshLog();
  } catch (error) {
    if (jobs.some(active)) {
      lastOverview = "";
      document.getElementById("run-overview").textContent = "Connection lost; reconnecting. The server may still be running your fit.";
    }
  } finally { polling = false; }
}
export function initJobs() {
  refresh(); setInterval(refresh, 750);
  window.addEventListener("beforeunload", event => {
    if (jobs.some(active)) { event.preventDefault(); event.returnValue = ""; }
  });
}
export async function runDensity(data, label) {
  const job = await request(data.simulation ? '/simulation/jobs' : data.observation ? '/ippp/jobs' : data.events && data.settings ? '/single_density/jobs' : data.events ? "/mixture/jobs" : "/density/jobs", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...data, label }),
  });
  observed.add(job.id);
  jobs.push(job); render();
  while (true) {
    let status;
    try { status = await request(`/jobs/${job.id}`); }
    catch (error) {
      if (error.message.startsWith("Cannot reach")) { await new Promise(resolve => setTimeout(resolve, 1000)); continue; }
      throw error;
    }
    if (!active(status)) {
      await refresh();
      return request(`/jobs/${job.id}/result`);
    }
    await new Promise(resolve => setTimeout(resolve, 500));
  }
}
