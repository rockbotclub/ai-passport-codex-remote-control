"""One fresh CLI turn per physical confirmation; never resume an existing chat."""
import json
import os
from pathlib import Path
import plistlib
import signal
import shutil
import subprocess
import threading
import uuid


def cli_path():
    candidates = [os.environ.get('CODEX_CLI_PATH')]
    if os.sys.platform == 'darwin':
        for app in (Path('/Applications/ChatGPT.app'), Path('/Applications/Codex.app')):
            try:
                with (app / 'Contents/Info.plist').open('rb') as file:
                    if plistlib.load(file).get('CFBundleIdentifier') != 'com.openai.codex':
                        continue
                candidates.append(str(app / 'Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex'))
            except (OSError, ValueError):
                pass
    candidates.append(shutil.which('codex'))
    for candidate in dict.fromkeys(candidates):
        if not candidate or not Path(candidate).is_file() or not os.access(candidate, os.X_OK):
            continue
        try:
            version = subprocess.run([candidate, '--version'], check=True, timeout=3,
                                     stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            if version.stdout.startswith(b'codex-cli '):
                return candidate
        except (OSError, subprocess.SubprocessError):
            pass
    raise RuntimeError('A working Codex CLI is required')


class NewChatRunner:
    def __init__(self, finished):
        self.finished = finished
        self.lock = threading.RLock()
        self.jobs = {}
        self.closed = False

    def start(self, executable, directory, project, text):
        if not text.strip() or len(text) > 12000:
            raise ValueError('Voice text empty or too long')
        with self.lock:
            if self.closed or any(j['status'] in ('starting', 'running') for j in self.jobs.values()):
                raise RuntimeError('A new chat is already running')
            # Keep only a bounded set of completed identities; never retain voice or output.
            self.jobs = dict(list(self.jobs.items())[-7:])
            identity = uuid.uuid4().hex
            env = dict(os.environ)
            for key in ('CODEX_THREAD_ID', 'CODEX_TURN_ID'):
                env.pop(key, None)
            process = subprocess.Popen([executable, 'exec', '--json', '--cd', str(directory), '-'],
                                       stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                       stderr=subprocess.DEVNULL, env=env, start_new_session=True)
            job = {'status': 'starting', 'thread': None, 'project': project,
                   'process': process, 'worker': None}
            self.jobs[identity] = job
            worker = threading.Thread(target=self._run, args=(job, text), daemon=True)
            job['worker'] = worker
            try:
                worker.start()
            except RuntimeError:
                self._stop(process)
                process.stdin.close()
                process.stdout.close()
                self.jobs.pop(identity)
                raise
            return identity

    def _run(self, job, text):
        process = job['process']
        complete = failed = False
        try:
            process.stdin.write(text.encode('utf-8'))
            process.stdin.close()
            text = ''
            dropping = False
            while True:
                line = process.stdout.readline(65537)
                if not line:
                    break
                # Drain oversized output without retaining text or partial JSON records.
                if dropping or len(line) > 65536:
                    dropping = not line.endswith(b'\n')
                    continue
                try:
                    event = json.loads(line)
                except (ValueError, UnicodeError):
                    continue
                if not isinstance(event, dict):
                    continue
                if event.get('type') == 'thread.started':
                    thread = event.get('thread_id')
                    try:
                        valid = isinstance(thread, str) and str(uuid.UUID(thread)) == thread
                    except ValueError:
                        valid = False
                    if valid:
                        with self.lock:
                            if job['thread'] and job['thread'] != thread:
                                failed = True
                            else:
                                job['thread'] = thread
                                job['status'] = 'running'
                elif event.get('type') == 'turn.completed':
                    complete = True
                elif event.get('type') == 'turn.failed':
                    failed = True
            code = process.wait()
        except (OSError, ValueError):
            self._stop(process)
            code = -1
        finally:
            for stream in (process.stdin, process.stdout):
                try:
                    stream.close()
                except OSError:
                    pass
        # The desktop may take ownership only after the CLI and its first turn exit.
        with self.lock:
            thread, closed = job['thread'], self.closed
        if thread and not closed:
            try:
                self.finished(thread)
            except (OSError, RuntimeError, subprocess.SubprocessError):
                pass  # The saved chat can still be opened manually; never retry the turn.
        with self.lock:
            job['status'] = 'complete' if code == 0 and complete and thread and not failed else 'failed'

    def status(self, identity):
        with self.lock:
            job = self.jobs.get(identity)
            return {k: job[k] for k in ('status', 'thread', 'project')} if job else None

    def owns(self, thread):
        with self.lock:
            return any(j['status'] in ('starting', 'running') and
                       (j['thread'] is None or j['thread'] == thread) for j in self.jobs.values())

    @staticmethod
    def _stop(process):
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=3)
            except ProcessLookupError:
                process.wait()

    def close(self):
        with self.lock:
            self.closed = True
            jobs = list(self.jobs.values())
        for job in jobs:
            self._stop(job['process'])
        for job in jobs:
            job['worker'].join(timeout=5)
