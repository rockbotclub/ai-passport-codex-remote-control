"""Own one bounded Doubao left-Control hold; transcripts stay in the input method/composer."""
import json
from messages import reason_text
from pathlib import Path
import select
import subprocess


class DoubaoError(RuntimeError):
    def __init__(self, reason, diagnostics=None):
        self.reason = reason
        self.diagnostics = diagnostics
        super().__init__('豆包语音控制失败：' + reason_text(reason))


REASONS = {10: 'accessibility-denied', 11: 'app-unavailable', 13: 'chat-not-found',
           14: 'multiple-chat-views', 15: 'writable-editor-not-found',
           16: 'multiple-writable-editors', 20: 'accessibility-tree-limit',
           21: 'invalid-composer-request', 22: 'composer-button-unavailable',
           23: 'multiple-composer-buttons', 24: 'chat-changed',
           25: 'dictation-already-active', 27: 'accessibility-view-unavailable',
           30: 'composer-focus-failed', 40: 'doubao-unavailable',
           41: 'doubao-input-required', 42: 'modifier-held', 43: 'codex-focus-required',
           44: 'key-dispatch-failed', 45: 'dictation-interrupted',
           46: 'dictation-timeout', 47: 'dictation-target-changed',
           48: 'doubao-state-unavailable', 49: 'doubao-start-unconfirmed',
           50: 'doubao-insert-pending'}


class DoubaoDictation:
    def __init__(self, directory):
        self.executable = Path(directory) / 'doubao-dictation'
        self.process = None
        self.thread = None

    def prepare(self):
        if self.executable.exists():
            return
        subprocess.run(['/usr/bin/clang', '-fobjc-arc', '-Wall', '-Wextra', '-Werror',
                        '-framework', 'AppKit', '-framework', 'ApplicationServices',
                        '-framework', 'Carbon', str(Path(__file__).with_suffix('.m')),
                        '-o', str(self.executable)], check=True, timeout=20,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def start(self, thread, title=None, draft_project=None):
        if self.process is not None:
            raise DoubaoError('dictation-already-active')
        self.prepare()
        request = {'thread': thread}
        if title:
            request['title'] = title
        if draft_project:
            request['draftProject'] = draft_project
        process = subprocess.Popen([str(self.executable)], stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.process, self.thread = process, thread
        try:
            process.stdin.write(json.dumps(request).encode() + b'\n')
            process.stdin.flush()
            if not select.select([process.stdout], [], [], 8)[0]:
                raise DoubaoError('dictation-start-not-ready')
            if process.stdout.readline(32) != b'held\n':
                code = process.wait(timeout=2)
                diagnostics = process.stderr.read(32768) if getattr(process, 'stderr', None) else None
                raise DoubaoError(REASONS.get(code, 'helper-failed'), diagnostics)
            # Native startup writes only bounded numeric discovery statistics.
            # Do not block on a live helper's stderr; read it after it exits.
        except BaseException:
            self.close()
            raise

    def finish(self, thread, cancel=False):
        process = self.process
        if process is None:
            return
        if self.thread != thread:
            raise DoubaoError('chat-changed')
        self.process, self.thread = None, None
        try:
            if process.poll() is None:
                # EOF also releases left Control. Cancellation can leave partial text;
                # it never sends Escape/Return or decides a Codex approval.
                if not cancel:
                    process.stdin.write(b'stop\n')
                    process.stdin.flush()
                process.stdin.close()
            code = process.wait(timeout=3)
            diagnostics = process.stderr.read(32768) if getattr(process, 'stderr', None) else None
            if code and not cancel:
                raise DoubaoError(REASONS.get(code, 'helper-failed'), diagnostics)
            return diagnostics
        finally:
            self._dispose(process)

    @staticmethod
    def _dispose(process):
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                # Do not SIGKILL a process that may still own a held Control key.
                raise DoubaoError('key-release-unconfirmed')
        for stream in (process.stdin, process.stdout, getattr(process, 'stderr', None)):
            if stream and not stream.closed:
                stream.close()

    def close(self):
        if self.process is not None:
            self.finish(self.thread, cancel=True)
