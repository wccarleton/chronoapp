"""Version-one, data-only project archives. No engine evaluation or file dialogs."""

import csv
import io
import json
import math
import zipfile
import zlib
from datetime import datetime, timezone
from importlib.metadata import version
from . import __version__

from chronologer.calcurves import DEFAULT_CURVES
from .saved_results import validate_saved_run
from .sampling import validate_saved_sampling

MAX_BYTES = 64 * 1024 * 1024
MAX_CSV_BYTES = 16 * 1024 * 1024
MAX_EVENTS = 10000


def new_project():
    now = datetime.now(timezone.utc).isoformat()
    return {
        "metadata": {"format_version": 1, "project_name": "Untitled project",
                     "chronoapp_version": __version__,
                     "chronologer_version": version("chronologer"),
                     "created_at": now, "modified_at": now, "active_dataset": "events"},
        "events": [], "source_csv": None,
    }


def _text(value, label, limit=120):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"{label} must be nonempty text (maximum {limit} characters).")


def validate_project(project):
    if not isinstance(project, dict) or not {"metadata", "events", "source_csv"} <= set(project) or set(project) - {"metadata", "events", "source_csv", "phases", "summaries", "processes"}:
        raise ValueError("Project must contain metadata, events, and source_csv.")
    meta = project["metadata"]
    if not isinstance(meta, dict):
        raise ValueError("Project metadata must be an object.")
    if type(meta.get("format_version")) is not int or meta["format_version"] != 1:
        raise ValueError("Unsupported project format version; this application supports version 1.")
    required = {"format_version", "project_name", "chronoapp_version", "chronologer_version",
                "created_at", "modified_at", "active_dataset"}
    if set(meta) != required or meta["active_dataset"] != "events":
        raise ValueError("Invalid project metadata or active dataset.")
    for key in required - {"format_version"}:
        _text(meta[key], key)
    for key in ("created_at", "modified_at"):
        try:
            stamp = datetime.fromisoformat(meta[key].replace("Z", "+00:00"))
            if stamp.tzinfo is None:
                raise ValueError()
        except ValueError:
            raise ValueError(f"{key} must be an ISO timestamp with a timezone.") from None
    events = project["events"]
    if not isinstance(events, list) or len(events) > MAX_EVENTS:
        raise ValueError(f"Project events must be a list of at most {MAX_EVENTS} records.")
    for index, event in enumerate(events, 1):
        prefix = f"Event {index}"
        if (not isinstance(event, dict) or not {"id", "distribution", "parameters"} <= set(event)
                or set(event) - {"id", "distribution", "parameters", "label", "datum", "include_in_calibration"}):
            raise ValueError(f"{prefix} requires id, distribution, and parameters.")
        _text(event["id"], f"{prefix} ID")
        _text(event["distribution"], f"{prefix} distribution")
        if "label" in event and (not isinstance(event["label"], str) or len(event["label"]) > 120):
            raise ValueError(f"{prefix}: label must be text of at most 120 characters.")
        if "datum" in event and event["datum"] not in ("BP1950", "BCAD"):
            raise ValueError(f"{prefix}: datum must be BP1950 or BCAD.")
        if "include_in_calibration" in event and type(event["include_in_calibration"]) is not bool:
            raise ValueError(f"{prefix}: include_in_calibration must be a boolean.")
        parameters = event["parameters"]
        if not isinstance(parameters, dict):
            raise ValueError(f"{prefix} parameters must be an object.")
        if event["distribution"] == "calrcarbon":
            if set(parameters) != {"c14_mean", "c14_err", "curve"}:
                raise ValueError(f"{prefix} requires c14_mean, c14_err, and curve.")
            for key in ("c14_mean", "c14_err"):
                value = parameters[key]
                if type(value) not in (int, float) or not math.isfinite(value):
                    raise ValueError(f"{prefix}: {key} must be a finite number.")
            if parameters["c14_err"] <= 0:
                raise ValueError(f"{prefix}: c14_err must be greater than zero.")
            if not isinstance(parameters["curve"], str) or parameters["curve"] not in DEFAULT_CURVES:
                raise ValueError(f"{prefix}: unsupported calibration curve.")
    phases = project.get("phases", [])
    if not isinstance(phases, list) or len(phases) > 100:
        raise ValueError("Phases must be a list of at most 100 specifications.")
    phase_ids = set()
    for index, phase in enumerate(phases):
        if not isinstance(phase, dict) or set(phase) != {"id", "label", "distribution", "order", "parameters"}:
            raise ValueError("Each phase requires id, label, distribution, order, and parameters.")
        _text(phase["id"], "Phase ID")
        _text(phase["label"], "Phase label")
        if phase["id"] in phase_ids:
            raise ValueError("Phase IDs must be unique.")
        phase_ids.add(phase["id"])
        if phase["distribution"] not in ("uniform", "normal"):
            raise ValueError("Phase distribution must be uniform or normal.")
        if type(phase["order"]) is not int or phase["order"] != index:
            raise ValueError("Phase order must match its zero-based list position.")
        if not isinstance(phase["parameters"], dict):
            raise ValueError("Phase parameters must be a JSON object.")
    summaries = project.get("summaries", [])
    if not isinstance(summaries, list) or len(summaries) > 100:
        raise ValueError("Summaries must be a list of at most 100 specifications.")
    processes = project.get('processes', [])
    if not isinstance(processes, list) or len(processes) > 100:
        raise ValueError('Processes must be a list of at most 100 specifications.')
    if any(isinstance(s, dict) and s.get('model') != 'ippp_gp' for s in processes):
        raise ValueError('Process Lab supports the ippp_gp model.')
    if any(isinstance(s, dict) and s.get('model') == 'ippp_gp' for s in summaries):
        raise ValueError('IPPP models belong in Process Lab.')
    summary_ids = set()
    for summary in summaries + processes:
        if (not isinstance(summary, dict) or not {"id", "label", "model", "events", "parameters"} <= set(summary)
                or set(summary) - {"id", "label", "model", "events", "parameters", "saved_run"}):
            raise ValueError("Each summary requires id, label, model, events, and parameters.")
        _text(summary["id"], "Summary ID")
        _text(summary["label"], "Summary label")
        if summary["id"] in summary_ids:
            raise ValueError("Summary IDs must be unique.")
        summary_ids.add(summary["id"])
        if summary["model"] not in ("density", 'single_density', "mixture", 'ippp_gp'):
            raise ValueError("Unsupported analysis model.")
        if not isinstance(summary["parameters"], dict):
            raise ValueError("Summary parameters must be a JSON object.")
        validate_saved_sampling(summary['parameters'])
        if not isinstance(summary["events"], list) or len(summary["events"]) > 100:
            raise ValueError("A Summary analysis currently supports at most 100 events; the project database supports 10,000.")
        # Reuse the event validator for independent input snapshots.
        validate_project({"metadata": meta, "events": summary["events"], "source_csv": None})
        if "saved_run" in summary:
            validate_saved_run(summary["saved_run"])
            validate_project({"metadata": meta, "events": summary["saved_run"]["events"], "source_csv": None})
    source = project["source_csv"]
    if source is not None:
        if not isinstance(source, dict) or set(source) != {"name", "text"}:
            raise ValueError("CSV provenance requires name and text.")
        _text(source["name"], "Source filename", 255)
        if not isinstance(source["text"], str):
            raise ValueError("Source CSV must be text.")
    try:
        encoded = json.dumps(project, allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, RecursionError):
        raise ValueError("Project contains invalid JSON values.") from None
    if len(encoded) > MAX_BYTES:
        raise ValueError("Project exceeds the 64 MiB limit. Remove unused saved Summary results.")
    return project


def import_csv(content: bytes, filename: str, default_curve: str | None = None):
    if len(content) > MAX_CSV_BYTES:
        raise ValueError("CSV exceeds the 16 MiB limit.")
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError("CSV must be UTF-8 encoded.") from None
    reader = csv.DictReader(io.StringIO(text.lstrip('\ufeff'), newline=''), strict=True)
    try:
        columns = reader.fieldnames or []
        if len(columns) != len(set(columns)):
            raise ValueError("CSV contains duplicate column names.")
        required = {"id", "c14_mean", "c14_err"}
        if not required <= set(columns):
            raise ValueError("CSV requires columns: id, c14_mean, c14_err; optional: curve, label, datum, include_in_calibration.")
        if set(columns) - required - {"curve", "label", "datum", "include_in_calibration"}:
            raise ValueError("CSV contains unsupported columns; accepted: id, c14_mean, c14_err, curve, label, datum, include_in_calibration.")
        events = []
        for row in reader:
            line = reader.line_num
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f"CSV line {line}: column count does not match the header.")
            try:
                mean, error = float(row["c14_mean"]), float(row["c14_err"])
            except ValueError:
                raise ValueError(f"CSV line {line}: c14_mean and c14_err must be numbers.") from None
            curve = row.get("curve", "").strip() or default_curve
            if not curve:
                raise ValueError(f"CSV line {line}: supply curve or select a calibration curve before import.")
            events.append({"id": row["id"].strip(), "distribution": "calrcarbon",
                           "parameters": {"c14_mean": mean, "c14_err": error, "curve": curve}})
            if "label" in row:
                events[-1]["label"] = row["label"].strip()
            if "datum" in row:
                events[-1]["datum"] = row["datum"].strip() or "BP1950"
            if "include_in_calibration" in row:
                value = row["include_in_calibration"].strip().lower()
                if value not in ("", "true", "false"):
                    raise ValueError(f"CSV line {line}: include_in_calibration must be true or false.")
                events[-1]["include_in_calibration"] = value != "false"
            if len(events) > MAX_EVENTS:
                raise ValueError(f"CSV supports at most {MAX_EVENTS} events.")
    except csv.Error as exc:
        raise ValueError(f"Malformed CSV near line {reader.line_num}: {exc}") from None
    if not events:
        raise ValueError("CSV contains no event rows.")
    project = new_project()
    project["events"] = events
    project["source_csv"] = {"name": filename, "text": text}
    validate_project(project)
    return {"events": events, "source_csv": project["source_csv"]}


def dump_project(project) -> bytes:
    validate_project(project)
    stream = io.BytesIO()
    def encode(value):
        # Compact numeric arrays keep validated files below the expanded-size
        # limit too; pretty printing could otherwise produce an unreadable save.
        return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("project.json", encode(project["metadata"]))
        archive.writestr("data/events.json", encode(project["events"]))
        if "phases" in project:
            archive.writestr("data/phases.json", encode(project["phases"]))
        if "summaries" in project:
            archive.writestr("data/summaries.json", encode(project["summaries"]))
        if 'processes' in project:
            archive.writestr('data/processes.json', encode(project['processes']))
        if project["source_csv"] is not None:
            archive.writestr("data/source.csv", project["source_csv"]["text"].encode("utf-8"))
            archive.writestr("data/source.json", encode({"name": project["source_csv"]["name"]}))
    return stream.getvalue()


def load_project(content: bytes):
    if len(content) > MAX_BYTES:
        raise ValueError("Project exceeds the 64 MiB limit.")
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            infos = archive.infolist()
            names = [item.filename for item in infos]
            required = {"project.json", "data/events.json"}
            allowed = required | {"data/source.csv", "data/source.json", "data/phases.json", "data/summaries.json", 'data/processes.json'}
            if (len(names) != len(set(names)) or not required <= set(names)
                    or set(names) - allowed or sum(item.file_size for item in infos) > MAX_BYTES):
                raise ValueError("Invalid project archive entries or expanded size exceeds 64 MiB.")
            if ("data/source.csv" in names) != ("data/source.json" in names):
                raise ValueError("Incomplete CSV provenance in project archive.")
            def read_json(name):
                return json.loads(archive.read(name).decode("utf-8"))
            meta = read_json("project.json")
            if not isinstance(meta, dict) or type(meta.get("format_version")) is not int or meta["format_version"] != 1:
                raise ValueError("Unsupported project format version; this application supports version 1.")
            source = None
            if "data/source.csv" in names:
                provenance = read_json("data/source.json")
                if not isinstance(provenance, dict) or set(provenance) != {"name"}:
                    raise ValueError("Invalid source CSV metadata.")
                source = {"name": provenance["name"], "text": archive.read("data/source.csv").decode("utf-8")}
            project = {"metadata": meta, "events": read_json("data/events.json"), "source_csv": source}
            if "data/phases.json" in names:
                project["phases"] = read_json("data/phases.json")
            if "data/summaries.json" in names:
                project["summaries"] = read_json("data/summaries.json")
            if 'data/processes.json' in names:
                project['processes'] = read_json('data/processes.json')
            return validate_project(project)
    except (zipfile.BadZipFile, UnicodeDecodeError, json.JSONDecodeError, RuntimeError, NotImplementedError, EOFError, zlib.error) as exc:
        raise ValueError(f"Invalid .chrono project archive: {exc}") from None
