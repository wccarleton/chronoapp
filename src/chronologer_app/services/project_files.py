"""Local file ownership; browser callers receive opaque references, never path authority."""
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import tempfile
import threading

from ..projects import MAX_BYTES, dump_project, load_project


class FileConflict(Exception):
    pass


class DialogUnavailable(Exception):
    pass


def choose_file(mode, *, name="Untitled project.chrono", directory=None):
    command = ([sys.executable, "--chrono-file-dialog"] if getattr(sys, "frozen", False)
               else [sys.executable, "-B", "-m", "chronologer_app.native_dialog"])
    result = subprocess.run(command, input=json.dumps({"mode": mode, "name": name,
                            "directory": directory, "title": "Save ChronoApp project" if mode == "save" else "Open ChronoApp project"}),
                            text=True, capture_output=True,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    try:
        response = json.loads(result.stdout)
    except ValueError:
        raise DialogUnavailable("The native file chooser could not start. Check that this local Python environment includes Tk.") from None
    if result.returncode or response.get("error"):
        raise DialogUnavailable(response.get("error") or "The native file chooser failed.")
    return Path(response["path"]).resolve() if response.get("path") else None


def fingerprint(path):
    if not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_write(path, content, expected):
    """Stage beside the destination so replace stays on the same filesystem."""
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        if fingerprint(path) != expected:
            raise FileConflict("This file changed outside this project tab. Open the latest copy, or use Save As.")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class ProjectFiles:
    def __init__(self):
        self.references = {}
        self.lock = threading.Lock()

    def _reference(self, path, digest, identifier=None):
        identifier = identifier or secrets.token_urlsafe(24)
        self.references[identifier] = (path, digest)
        return {"id": identifier, "name": path.name, "path": str(path)}

    def open(self):
        if not self.lock.acquire(blocking=False):
            raise FileConflict("Another file operation is in progress. Finish its dialog first.")
        try:
            path = choose_file("open")
            if path is None:
                return {"cancelled": True}
            with path.open("rb") as stream:
                content = stream.read(MAX_BYTES + 1)
            if len(content) > MAX_BYTES:
                raise ValueError("Project exceeds the 64 MiB limit.")
            project = load_project(content)
            file = self._reference(path, hashlib.sha256(content).hexdigest())
            return {"cancelled": False, "project": project, "file": file}
        finally:
            self.lock.release()

    def save(self, project, identifier=None, save_as=False):
        # Invalid drafts must not open dialogs or create placeholder files.
        content = dump_project(project)
        if not self.lock.acquire(blocking=False):
            raise FileConflict("Another file operation is in progress. Finish its dialog first.")
        try:
            current = self.references.get(identifier) if identifier else None
            if identifier and current is None and not save_as:
                raise FileConflict("The local app no longer recognizes this file reference, possibly after a restart. Use Save As to select the file again.")
            if save_as or current is None:
                name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', project['metadata']['project_name']).rstrip(' .') or 'Untitled project'
                path = choose_file("save", name=f"{name}.chrono", directory=str(current[0].parent) if current else None)
                if path is None:
                    return {"cancelled": True}
                expected = fingerprint(path)
                identifier = None
            else:
                path, expected = current
            atomic_write(path, content, expected)
            return {"cancelled": False, "file": self._reference(path, hashlib.sha256(content).hexdigest(), identifier)}
        finally:
            self.lock.release()


project_files = ProjectFiles()
