// One document shared by tabs. Opaque local-app file references and dirty state are session-only;
// the serializable document contains only metadata, events, and provenance.
import { phaseEdges } from './phase-settings.js';

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
    if (this.data.phases) {
      this.data.phases = this.data.phases.map((phase, index) => ({ ...phase,
        position: phase.position ?? { x: 50, y: 50 + (this.data.phases.length - index - 1) * 650 } }));
      const model = this.data.phase_model ?? { parameters: {} };
      this.data.phase_model = { ...model, parameters: { ...model.parameters,
        edges: phaseEdges(this.data.phases, model.parameters) } };
    }
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
  setPhaseCanvas(phases, edges) {
    this.edit(data => {
      data.phases = structuredClone(phases).map((phase, order) => ({ ...phase, order,
        position: phase.position ?? { x: 50, y: 50 + (phases.length - order - 1) * 650 } }));
      const model = data.phase_model ?? { parameters: {} };
      data.phase_model = { ...model, parameters: { ...model.parameters, edges: structuredClone(edges) } };
    });
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
