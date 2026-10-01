"""Bounded local process jobs with progress, cancellation and per-run logs."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stderr, redirect_stdout
import logging
import multiprocessing
import os
from pathlib import Path
import threading
import time
import traceback
import uuid

MAX_WORKERS = 2
MAX_PENDING = 8
MAX_HISTORY = 20
TERMINAL = {"completed", "failed", "cancelled"}


def _worker(function, args, connection, log_path):
    try:
        with open(log_path, "a", encoding="utf-8", buffering=1) as log:
            with redirect_stdout(log), redirect_stderr(log):
                handler = logging.StreamHandler(log)
                handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
                logging.getLogger().handlers = [handler]
                logging.getLogger().setLevel(logging.INFO)
                last_sent, last_stage = 0., None

                def progress(update):
                    nonlocal last_sent, last_stage
                    now = time.monotonic()
                    if update["stage"] != last_stage or now - last_sent >= .15 or update["completed"] == update["total"]:
                        connection.send(("progress", update))
                        last_sent = now
                    if update["stage"] != last_stage:
                        print(update["stage"], flush=True)
                        last_stage = update["stage"]
                try:
                    result = function(*args, progress_callback=progress)
                    print("Completed", flush=True)
                    connection.send(("result", result))
                except Exception as error:
                    traceback.print_exc()
                    connection.send(("error", {"error": str(error), "error_type": type(error).__name__}))
    except Exception as error:
        try:
            connection.send(("error", {"error": f"Worker/logging failure: {error}", "error_type": type(error).__name__}))
        except (OSError, EOFError):
            pass
    finally:
        connection.close()


class JobManager:
    def __init__(self, log_dir=None, workers=MAX_WORKERS, max_pending=MAX_PENDING):
        self.log_dir = Path(log_dir or os.environ.get("CHRONOAPP_LOG_DIR") or
                            Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local" / "state")) / "ChronoApp" / "logs")
        self.workers, self.max_pending = workers, max_pending
        self.lock = threading.RLock()
        self.jobs = {}
        self.pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="chrono-job")
        self.closed = False

    def submit(self, function, args, label):
        with self.lock:
            if self.closed:
                raise RuntimeError("Job service is shutting down.")
            active = sum(job["finished"] is None for job in self.jobs.values())
            if active >= self.max_pending:
                raise ValueError("The inference queue is full. Wait for a run to finish.")
            finished = [key for key, job in self.jobs.items() if job["status"] in TERMINAL and job["finished"]]
            for key in finished[:max(0, len(finished) - MAX_HISTORY + 1)]:
                del self.jobs[key]
            self.log_dir.mkdir(parents=True, exist_ok=True)
            identifier = uuid.uuid4().hex
            log_path = self.log_dir / f"density-{identifier}.log"
            log_path.write_text(f"{label}\nQueued at {time.ctime()}\n", encoding="utf-8")
            job = dict(id=identifier, label=label, status="queued", stage="Queued", completed=0,
                       total=0, created=time.time(), finished=None, result=None, error=None,
                       error_type=None, cancel=False, log_path=str(log_path))
            self.jobs[identifier] = job
            self.pool.submit(self._run, identifier, function, args)
            return self.get(identifier)

    def _update(self, identifier, **updates):
        with self.lock:
            self.jobs[identifier].update(updates)

    def _run(self, identifier, function, args):
        context = multiprocessing.get_context("spawn")
        receive, send = context.Pipe(duplex=False)
        process = None
        try:
            with self.lock:
                job = self.jobs[identifier]
                if job["cancel"]:
                    self._update(identifier, status="cancelled", stage="Cancelled")
                    return
                self._update(identifier, status="running", stage="Starting worker")
                process = context.Process(target=_worker, args=(function, args, send, job["log_path"]))
                process.start()
            send.close()
            while True:
                if self.jobs[identifier]["cancel"]:
                    self._update(identifier, status="cancelled", stage="Cancelled")
                    break
                if receive.poll(.1):
                    try:
                        kind, message = receive.recv()
                    except EOFError:
                        break
                    if kind == "progress":
                        self._update(identifier, **message)
                    elif kind == "result":
                        self._update(identifier, result=message, status="completed", stage="Completed")
                        break
                    else:
                        self._update(identifier, status="failed", stage="Failed", **message)
                        break
                elif not process.is_alive():
                    break
            if self.jobs[identifier]["status"] not in TERMINAL:
                self._update(identifier, status="failed", stage="Failed", error="The inference worker exited without a result.")
        except Exception as error:
            self._update(identifier, status="failed", stage="Failed", error=str(error))
        finally:
            if process is not None and process.pid is not None:
                process.join(timeout=1)
                if process.is_alive():
                    process.terminate()
                    process.join(timeout=5)
                process.close()
            receive.close()
            send.close()
            with open(self.jobs[identifier]["log_path"], "a", encoding="utf-8") as log:
                log.write(f"\nJob {self.jobs[identifier]['status']}\n")
            self._update(identifier, finished=time.time())

    def get(self, identifier, result=False):
        with self.lock:
            job = self.jobs[identifier]
            output = {key: value for key, value in job.items() if key not in {"result", "cancel"}}
            output["elapsed_seconds"] = (job["finished"] or time.time()) - job["created"]
            if result:
                output["result"] = job["result"]
            return output

    def list(self):
        with self.lock:
            return [self.get(identifier) for identifier in self.jobs]

    def cancel(self, identifier):
        with self.lock:
            job = self.jobs[identifier]
            if job["status"] not in TERMINAL:
                job["cancel"] = True
                if job["status"] == "queued":
                    job.update(status="cancelled", stage="Cancelled")
                else:
                    job["stage"] = "Cancelling"
            return self.get(identifier)

    def close(self):
        with self.lock:
            self.closed = True
            for identifier in self.jobs:
                self.cancel(identifier)
        self.pool.shutdown(wait=True)


_manager = None
_manager_lock = threading.Lock()


def get_jobs():
    global _manager
    with _manager_lock:
        if _manager is None or _manager.closed:
            _manager = JobManager()
        return _manager


def shutdown_jobs():
    if _manager is not None:
        _manager.close()
