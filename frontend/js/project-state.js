// One document shared by tabs. Opaque local-app file references and dirty state are session-only;
// the serializable document contains only metadata, events, and provenance.
class ProjectState extends EventTarget {
  data = null;
  fileHandle = null;
  dirty = false;
  revision = 0;
  defaultCurve = null;
  busy = false;
  notify(replace = false) {
    this.dispatchEvent(new CustomEvent("change", { detail: { replace } }));
  }
  replace(data, handle = null) {
    this.data = structuredClone(data);
    this.fileHandle = handle;
    this.dirty = false;
    this.revision++;
    this.notify(true);
  }
  edit(update, replace = false) {
    if (!this.data) return;
    update(this.data);
    this.data.metadata.modified_at = new Date().toISOString();
    this.dirty = true;
    this.revision++;
    this.notify(replace);
  }
  setEvents(events) { this.edit(data => { data.events = structuredClone(events); }); }
  updateEvent(index, update) {
    if (!this.data?.events[index]) return;
    this.setEvents(this.data.events.map((event, i) => i === index ? { ...event, ...update } : event));
  }
  removeEvent(index) { this.setEvents(this.data.events.filter((_, i) => i !== index)); }
  setSummaries(summaries) { this.edit(data => { data.summaries = structuredClone(summaries); }); }
  setProcesses(processes) { this.edit(data => { data.processes = structuredClone(processes); }); }
  setPhaseModel(model) { this.edit(data => { data.phase_model = structuredClone(model); }); }
  // Future inference adapters consume these semantic specs, never canvas pixels.
  setPhases(phases) {
    this.edit(data => { data.phases = structuredClone(phases).map((phase, order) => ({ ...phase, order })); });
  }
  setName(name) { this.edit(data => { data.metadata.project_name = name; }); }
  importRecords(imported) {
    this.edit(data => {
      data.events = imported.events;
      data.source_csv = imported.source_csv;
    }, true);
  }
}

export const projectState = new ProjectState();
