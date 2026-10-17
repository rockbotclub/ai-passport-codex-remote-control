"""Read-only desktop startup status reconciliation, independent of card I/O."""
import hashlib
import json
import sqlite3
import threading
import time


def thread_catalog(rows):
    """Match the user-chat directory; internal records are not separate tasks."""
    resolved = {}
    for identity, archived, path, source in rows:
        try:
            source = json.loads(source) if source else None
        except (ValueError, TypeError):
            pass  # Plain source names (cli, vscode, exec) are user sessions.
        internal = isinstance(source, dict) and 'subagent' in source
        resolved[identity] = identity if not archived and not path and not internal else None
    return resolved


def compact_snapshot(state):
    """Discard conversation content immediately; retain lifecycle facts only."""
    if not isinstance(state, dict):
        raise ValueError('无法识别电脑端状态快照')
    runtime = state.get('threadRuntimeStatus')
    if not isinstance(runtime, dict) or runtime.get('type') not in ('active', 'idle', 'notLoaded', 'systemError'):
        raise ValueError('无法识别电脑端运行状态')
    kind = runtime['type']
    flags = runtime.get('activeFlags', [])
    if not isinstance(flags, list):
        raise ValueError('无法识别电脑端活动标记')
    requests = state.get('requests', [])
    if not isinstance(requests, list):
        raise ValueError('无法识别电脑端请求')
    status = ('waiting' if requests or any(f in ('waitingOnApproval', 'waitingOnUserInput') for f in flags)
              else 'working' if kind == 'active' else 'error' if kind == 'systemError' else 'idle')
    return {'status': status, 'turn': None, 'tool': None, 'event': 'Snapshot'}


class StatusSync:
    """One bounded background sweep at a time; failed sweeps never imply idle."""
    def __init__(self, desktop, tracker, diagnostics=False):
        self.desktop, self.tracker, self.diagnostics = desktop, tracker, diagnostics
        self.stop = threading.Event()
        self.wake = threading.Event()
        self.worker = None

    def start(self):
        self.worker = threading.Thread(target=self.run, daemon=True)
        self.worker.start()

    def run(self):
        while not self.stop.is_set():
            revision = self.tracker.revision()
            states, complete = {}, True
            try:
                self.wake.clear()
                catalog = self.desktop.activity_index()
                self.tracker.set_catalog(catalog)
                threads = [thread for thread, root in catalog.items() if root is not None]
                for identity, result in self.desktop.activity_snapshots(threads):
                    if self.stop.is_set():
                        return
                    if result is False:
                        complete = False
                    elif result is None:
                        self.tracker.reconcile({}, revision, time.monotonic(), None,
                                               absent=(hashlib.sha256(identity.encode()).hexdigest()[:32],))
                    elif result is not None:
                        states[hashlib.sha256(identity.encode()).hexdigest()[:32]] = result
                        self.tracker.reconcile(states, revision, time.monotonic(), None)
                self.tracker.reconcile(states, revision, time.monotonic(), complete)
            except (OSError, EOFError, RuntimeError, ValueError, KeyError, TypeError, sqlite3.Error):
                complete = False
                self.tracker.reconcile({}, revision, time.monotonic(), False)
            if self.diagnostics:
                print(f'任务状态同步：{"完整" if complete else "尚未完整"}；已观察会话数：{len(states)}', flush=True)
            for _ in range(10 if complete else 5):
                if self.stop.wait(1):
                    return
                if self.wake.is_set():
                    break

    def notify(self, identity):
        if self.tracker.needs_catalog(identity):
            self.wake.set()

    def read(self, identity):
        if self.stop.is_set():
            return False
        try:
            return self.desktop.activity_snapshot(identity)
        except (OSError, EOFError, RuntimeError, ValueError, KeyError, TypeError):
            return False

    def close(self):
        self.stop.set()
        if self.worker:
            self.worker.join(timeout=3)
