import { projectState as state } from "./project-state.js";
import { initEventTable } from "./event-table.js";

const LIMIT = 64 * 1024 * 1024;

async function request(path, options = {}) {
  const response = await fetch(`/api/projects/${path}`, options);
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `Project operation failed (${response.status}).`);
  }
  return response;
}

async function bytes(file) {
  if (file.size > LIMIT) throw new Error("Project exceeds the 64 MiB limit.");
  return file.arrayBuffer();
}

async function localFileRequest(action, payload) {
  // The local app owns selected paths; the browser holds only an opaque ID.
  const session = await (await request("files/session")).json();
  const response = await request(`files/${action}`, {
    method: "POST", headers: { "Content-Type": "application/json", "X-ChronoApp-Token": session.token },
    ...(payload === undefined ? {} : { body: JSON.stringify(payload) }),
  });
  return response.json();
}

export async function initProject() {
  const name = document.getElementById("project-name");
  const status = document.getElementById("project-status");
  const csvInput = document.getElementById("csv-file");
  const projectInput = document.getElementById("project-file");
  let openedCopyName = null;
  function message(text, error = false) {
    status.textContent = text;
    status.classList.toggle("project-error", error);
    document.getElementById("csv-status").textContent = error ? text : "";
  }
  function render() {
    if (!state.data) return;
    const { metadata, events, source_csv } = state.data;
    if (document.activeElement !== name) name.value = metadata.project_name;
    document.getElementById("project-location").textContent = state.fileHandle
      ? `File: ${state.fileHandle.path || state.fileHandle.name}` : openedCopyName
        ? `Opened copy: ${openedCopyName} · Save to choose a project file.`
        : "Not saved to a file yet";
    document.getElementById("project-indicator").textContent = `${metadata.project_name || "Untitled project"}${state.dirty ? " · Unsaved changes" : ""}`;
    document.getElementById("project-details").textContent = `${events.length} events · ${state.data.phases?.length ?? 0} phases · ${source_csv ? `Source: ${source_csv.name}` : "No source CSV"} · ${state.dirty ? "Unsaved changes" : "No unsaved changes"}`;
  }
  state.addEventListener("change", render);
  name.addEventListener("input", () => state.setName(name.value));
  window.addEventListener("beforeunload", event => {
    if (state.dirty) { event.preventDefault(); event.returnValue = ""; }
  });
  function canDiscard() {
    return !state.dirty || window.confirm("Discard unsaved project changes? Save first if you want to keep them.");
  }
  async function run(action, operation = "project") {
    if (state.busy) return;
    state.busy = true;
    document.querySelectorAll("[data-project-action]").forEach(button => { button.disabled = true; });
    document.getElementById("calibration-form").inert = true;
    document.getElementById("phase-panel").inert = true;
    document.getElementById("summarize-panel").inert = true;
    name.disabled = true;
    document.getElementById("project-event-editor").inert = true;
    try { await action(); }
    catch (error) {
      if (["NotAllowedError", "SecurityError", "NoModificationAllowedError"].includes(error.name)) {
        const recovery = operation === "open"
          ? "Use Open copy to read the project without file-handle access."
          : "Try Save As in a writable folder, or Download copy.";
        message(`File access blocked (${error.name}). Your changes are still in this app. ${recovery} Browser detail: ${error.message}`, true);
      } else if (error.name !== "AbortError") message(error.message || "Project operation failed.", true);
    } finally {
      state.busy = false;
      document.querySelectorAll("[data-project-action]").forEach(button => { button.disabled = false; });
      document.getElementById("calibration-form").inert = false;
      document.getElementById("phase-panel").inert = false;
      document.getElementById("summarize-panel").inert = false;
      name.disabled = false;
      document.getElementById("project-event-editor").inert = false;
    }
  }
  async function save(asNew) {
    if (!state.data) throw new Error("Create or open a project first.");
    const snapshot = structuredClone(state.data), revision = state.revision;
    message(asNew || !state.fileHandle ? "Choose where to save in the file dialog…" : "Saving project…");
    const response = await localFileRequest("save", { project: snapshot, file_id: state.fileHandle?.id ?? null, save_as: asNew });
    if (response.cancelled) { message("Save cancelled. Your project is unchanged."); return; }
    state.fileHandle = response.file;
    openedCopyName = null;
    if (revision === state.revision) state.dirty = false;
    state.notify();
    message(`Saved ${response.file.name}.`);
  }
  const actions = {
    new: () => run(async () => {
      if (!canDiscard()) return;
      const response = await request("new");
      openedCopyName = null;
      state.replace(await response.json());
      message("New project created.");
    }),
    open: () => run(async () => {
      if (!canDiscard()) return;
      message("Choose a project in the file dialog…");
      const response = await localFileRequest("open");
      if (response.cancelled) { message("Open cancelled. Your project is unchanged."); return; }
      openedCopyName = null;
      state.replace(response.project, response.file);
      message(`Opened ${response.file.name}. ${state.data.events.length} events restored.`);
    }, "open"),
    "open-copy": () => {
      if (state.busy) return;
      projectInput.value = "";
      projectInput.click();
    },
    save: () => run(() => save(false)),
    "save-as": () => run(() => save(true)),
    download: () => run(async () => {
      const response = await request("encode", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(state.data) });
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = url;
      link.download = `${(state.data.metadata.project_name.trim() || "Untitled project").replace(/[<>:"/\\|?*]/g, "_")}.chrono`;
      document.body.append(link); link.click(); link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 30000);
      message("Project copy sent to browser downloads. Check that the download completed. The linked file and unsaved-changes status have not changed.");
    }),
    csv: () => {
      if (state.busy) return;
      if (state.data?.events.length && !window.confirm("Replace the current event dataset with a CSV? The rest of the project is kept.")) return;
      csvInput.value = "";
      csvInput.click();
    },
  };
  document.querySelectorAll("[data-project-action]").forEach(button => {
    button.addEventListener("click", () => actions[button.dataset.projectAction]());
  });
  csvInput.addEventListener("change", () => run(async () => {
    const file = csvInput.files[0];
    if (!file) return;
    const params = new URLSearchParams({ filename: file.name });
    if (state.defaultCurve) params.set("default_curve", state.defaultCurve);
    const response = await request(`import-csv?${params}`, { method: "POST", headers: { "Content-Type": "text/csv" }, body: await bytes(file) });
    state.importRecords(await response.json());
    message(`Imported ${state.data.events.length} events from ${file.name}. Save to keep this project.`);
    document.getElementById("csv-status").textContent = `Loaded ${state.data.events.length} events from ${file.name}.`;
  }));
  projectInput.addEventListener("change", () => run(async () => {
    const file = projectInput.files[0];
    if (!file || !canDiscard()) return;
    const response = await request("decode", {
      method: "POST", headers: { "Content-Type": "application/octet-stream" }, body: await bytes(file),
    });
    const project = await response.json();
    openedCopyName = file.name;
    state.replace(project);
    message(`Opened ${file.name}. ${project.events.length} events restored. Save to choose a project file.`);
  }, "open"));
  await run(async () => { state.replace(await (await request("new")).json()); });
  initEventTable();
}
