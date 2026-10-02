import logging
import sys
import time
import multiprocessing
from pathlib import Path

import pytest

from chronologer_app.services.jobs import JobManager


def slow_work(steps, fail=False, progress_callback=None):
    print('worker stdout', flush=True)
    print('worker stderr', file=sys.stderr, flush=True)
    logging.warning('worker log message')
    for index in range(steps):
        progress_callback(dict(stage='Sampling', completed=index + 1, total=steps))
        time.sleep(.05)
    if fail:
        raise ValueError('Deliberate failure')
    return {'ok': True}


def wait_for(predicate, timeout=20):
    deadline = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < deadline, 'Job timed out'
        time.sleep(.05)


def child_heartbeat(path):
    for _ in range(600):
        Path(path).write_text(str(time.monotonic()))
        time.sleep(.05)


def work_with_child(path, progress_callback=None):
    child = multiprocessing.get_context('spawn').Process(target=child_heartbeat, args=(path,))
    child.start()
    child.join()


def test_cancel_stops_worker_descendants(tmp_path):
    heartbeat = tmp_path / 'heartbeat.txt'
    manager = JobManager(tmp_path, workers=1)
    try:
        job = manager.submit(work_with_child, (str(heartbeat),), 'Nested worker')['id']
        wait_for(heartbeat.exists)
        manager.cancel(job)
        wait_for(lambda: manager.get(job)['finished'] is not None)
        stamp = heartbeat.stat().st_mtime_ns
        time.sleep(.3)
        assert heartbeat.stat().st_mtime_ns == stamp
        assert manager.get(job)['status'] == 'cancelled'
    finally:
        manager.close()


def test_two_workers_queue_cancel_and_logs(tmp_path):
    manager = JobManager(tmp_path, workers=2, max_pending=3)
    try:
        first = manager.submit(slow_work, (100,), 'First')['id']
        second = manager.submit(slow_work, (100,), 'Second')['id']
        third = manager.submit(slow_work, (2,), 'Queued')['id']
        assert manager.get(third)['status'] == 'queued'
        with pytest.raises(ValueError, match='queue is full'):
            manager.submit(slow_work, (1,), 'Overflow')
        wait_for(lambda: manager.get(first)['completed'] > 0 and manager.get(second)['completed'] > 0)
        assert manager.get(third)['status'] == 'queued'
        manager.cancel(second)
        wait_for(lambda: manager.get(second)['status'] == 'cancelled')
        wait_for(lambda: manager.get(third)['status'] == 'completed')
        assert manager.get(third, result=True)['result'] == {'ok': True}
        manager.cancel(first)
        wait_for(lambda: manager.get(first)['status'] == 'cancelled')
        text = (tmp_path / f'density-{third}.log').read_text()
        assert all(message in text for message in ['worker stdout', 'worker stderr', 'worker log message'])
    finally:
        manager.close()


def test_failed_and_queued_cancelled_jobs_release_worker(tmp_path):
    manager = JobManager(tmp_path, workers=1)
    try:
        first = manager.submit(slow_work, (4, True), 'Failure')['id']
        second = manager.submit(slow_work, (1,), 'Cancel queued')['id']
        manager.cancel(second)
        wait_for(lambda: manager.get(first)['status'] == 'failed')
        wait_for(lambda: manager.get(second)['status'] == 'cancelled')
        assert 'Deliberate failure' in manager.get(first)['error']
        text = (tmp_path / f'density-{first}.log').read_text()
        assert 'Traceback' in text and 'Deliberate failure' in text
    finally:
        manager.close()
