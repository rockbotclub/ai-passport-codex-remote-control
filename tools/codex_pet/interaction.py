"""Local desktop IPC adapter, physical approval broker and encrypted voice transport.

Existing-chat IPC never starts a second executor. New chats use one fresh CLI turn.
Voice transcribes and fills the selected chat without reading its PC input.
Only a physical Confirm with the current review token can send voice or approve.
"""
from contextlib import closing
import hmac
import json
import os
from pathlib import Path
import socket
import shutil
import sqlite3
import struct
import subprocess
import sys
import tempfile
import threading
import time
import uuid
import wave
from urllib.parse import quote, urlencode
from speech import WhisperWorker, finish_sentence
from new_chat import NewChatRunner, cli_path

CONTROL_PORT, APPROVAL_PORT = 19285, 19286
WIDTH, HEIGHT = 216, 224
LINE_SPACING = 2
LIST_ENTRIES, LIST_LINE_HEIGHT = 5, 20
PIXELS = WIDTH * HEIGHT // 8
MAX_RECORD = 6144
PROJECTLESS = '__projectless__'


def exact(sock, n):
    result = bytearray()
    while len(result) < n:
        part = sock.recv(n - len(result))
        if not part:
            raise EOFError('Connection closed')
        result.extend(part)
    return bytes(result)


class SecureChannel:
    def __init__(self, sock, key, server=False):
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        self.sock = sock
        secret = key.encode('ascii')
        if server:
            hello = exact(sock, 20)
            if hello[:4] != b'CPG1':
                raise ValueError('Wrong protocol')
            client = hello[4:]
            own = os.urandom(16)
            seed = client + own
            sock.sendall(own + hmac.digest(secret, b'server' + seed, 'sha256'))
            if not hmac.compare_digest(exact(sock, 32), hmac.digest(secret, b'client' + seed, 'sha256')):
                raise ValueError('Pairing failed')
        else:
            client = os.urandom(16)
            sock.sendall(b'CPG1' + client)
            response = exact(sock, 48)
            seed = client + response[:16]
            if not hmac.compare_digest(response[16:], hmac.digest(secret, b'server' + seed, 'sha256')):
                raise ValueError('Pairing failed')
            sock.sendall(hmac.digest(secret, b'client' + seed, 'sha256'))
        c2s = AESGCM(hmac.digest(secret, b'CPG1' + seed + b'C', 'sha256'))
        s2c = AESGCM(hmac.digest(secret, b'CPG1' + seed + b'S', 'sha256'))
        self.tx, self.rx = (s2c, c2s) if server else (c2s, s2c)
        self.sent = self.received = 0

    def send(self, payload):
        if not 1 <= len(payload) <= MAX_RECORD - 16:
            raise ValueError('Record too large')
        self.sent += 1
        nonce = b'\0' * 4 + self.sent.to_bytes(8, 'big')
        body = self.tx.encrypt(nonce, payload, b'CPG1')
        self.sock.sendall(struct.pack('!H', len(body)) + body)

    def receive(self):
        from cryptography.exceptions import InvalidTag
        size = struct.unpack('!H', exact(self.sock, 2))[0]
        if not 17 <= size <= MAX_RECORD:
            raise ValueError('Invalid record length')
        self.received += 1
        nonce = b'\0' * 4 + self.received.to_bytes(8, 'big')
        try:
            return self.rx.decrypt(nonce, exact(self.sock, size), b'CPG1')
        except InvalidTag:
            raise ValueError('Record authentication failed') from None


class Desktop:
    """Use the existing desktop thread owner; never resume a second executor."""
    def __init__(self, root=None):
        self.root = Path(root or Path.home() / '.codex')
        self._sessions = []
        self._refreshing = False
        self._refreshed = 0
        self._lock = threading.Lock()
        self._projects = []
        self._projects_refreshed = 0
        self.new_chats = NewChatRunner(self.open_created)

    def project_state(self):
        try:
            state = json.loads((self.root / '.codex-global-state.json').read_text())
        except FileNotFoundError:
            return {}
        if not isinstance(state, dict):
            raise ValueError('Unsupported desktop project state')
        return state

    def project_id(self, identity, state):
        # Migrated desktop projects retain legacy IDs in older assignments.
        hosts = state.get('app-server-project-id-by-legacy-project-id-by-host', {})
        mapping = hosts.get('local:' + str(self.root.resolve()), hosts.get('local', {}))
        return mapping.get(identity, identity)

    def projects(self):
        if time.monotonic() - self._projects_refreshed >= 10:
            state = self.project_state()
            with closing(sqlite3.connect(f'file:{self.root / "state_5.sqlite"}?mode=ro', uri=True)) as db:
                records = {identity: {'id': identity, 'name': name or 'Unnamed project'}
                           for identity, name in db.execute('SELECT id,name FROM projects ORDER BY name,id')}
            for identity, project in state.get('local-projects', {}).items():
                identity = self.project_id(identity, state)
                records[identity] = {'id': identity, 'name': project.get('name') or 'Unnamed project'}
            self._projects = list(records.values())
            self._projects_refreshed = time.monotonic()
        return list(self._projects)

    def project_roots(self, state):
        roots = {}
        with closing(sqlite3.connect(f'file:{self.root / "state_5.sqlite"}?mode=ro', uri=True)) as db:
            if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='project_roots'").fetchone():
                for project, path in db.execute('SELECT project_id,path FROM project_roots ORDER BY position'):
                    roots.setdefault(self.project_id(project, state), []).append(path)
        for identity, project in state.get('local-projects', {}).items():
            saved = roots.setdefault(self.project_id(identity, state), [])
            saved.extend(path for path in project.get('rootPaths', []) if path not in saved)
        return roots

    def project_directory(self, project_id):
        self._projects_refreshed = 0
        if project_id == PROJECTLESS or not any(p['id'] == project_id for p in self.projects()):
            raise ValueError('Select a saved project to create a chat')
        state = self.project_state()
        roots = self.project_roots(state)
        paths = roots.get(project_id, [])
        if not paths or not Path(paths[0]).is_absolute() or not Path(paths[0]).is_dir():
            raise ValueError('Selected project has no accessible local folder')
        directory = Path(paths[0]).resolve()
        # CLI membership is resolved by cwd. Reject equal roots that name another
        # project rather than silently misassigning the new chat.
        for identity, paths in roots.items():
            if identity != project_id and any(directory == Path(p).resolve() for p in paths):
                raise ValueError('Selected project shares its folder with another project')
        return directory

    def new_session(self, project_id):
        """Prepare device voice entry; this does not create a thread or send a prompt."""
        self.project_directory(project_id)
        cli_path()

    def send_new(self, project_id, text):
        return self.new_chats.start(cli_path(), self.project_directory(project_id), project_id, text)

    def new_status(self, identity):
        return self.new_chats.status(identity)

    def open_created(self, thread):
        if sys.platform != 'darwin':
            return
        url = 'codex://threads/' + quote(thread, safe='')
        subprocess.run(['open', '-b', 'com.openai.codex', url], check=True, timeout=5,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        with self._lock:
            self._refreshed = 0

    def request(self, method, params, version, target=None, timeout=8):
        path = self.root / 'ipc/ipc.sock'
        if path.stat().st_uid != os.getuid() or path.parent.stat().st_mode & 0o022:
            raise RuntimeError('Unsafe desktop IPC ownership')
        with socket.socket(socket.AF_UNIX) as sock:
            sock.settimeout(timeout)
            sock.connect(str(path))
            client = 'initializing-client'
            def call(name, arguments, ver, owner=None):
                identity = str(uuid.uuid4())
                value = {'type': 'request', 'requestId': identity, 'sourceClientId': client,
                         'version': ver, 'method': name, 'params': arguments}
                if owner:
                    value['targetClientId'] = owner
                body = json.dumps(value).encode()
                sock.sendall(struct.pack('<I', len(body)) + body)
                for _ in range(200):
                    n = struct.unpack('<I', exact(sock, 4))[0]
                    if n > 8 * 1024 * 1024:
                        raise ValueError('Desktop response too large')
                    reply = json.loads(exact(sock, n))
                    if reply.get('requestId') == identity:
                        if reply.get('resultType') != 'success':
                            raise RuntimeError(reply.get('error', 'Desktop rejected request'))
                        return reply
                raise RuntimeError('No desktop response')
            client = call('initialize', {'clientType': 'ai-passport'}, 0)['result']['clientId']
            return call(method, params, version, target)

    def owner(self, thread):
        return self.request('thread-owner-discovery', {'hostId': 'local', 'conversationId': thread}, 1, timeout=0.35)['handledByClientId']

    def _scan_sessions(self):
        # List saved chats independently of whether a desktop executor is loaded.
        # Owner discovery belongs to actions, never project membership/listing.
        with closing(sqlite3.connect(f'file:{self.root / "state_5.sqlite"}?mode=ro', uri=True)) as db:
            rows = db.execute('''SELECT t.id,t.name,p.name,t.cwd,t.project_id FROM threads t
                LEFT JOIN projects p ON p.id=t.project_id
                WHERE t.archived=0 AND t.agent_path IS NULL
                ORDER BY t.updated_at DESC,t.id''').fetchall()
        state = self.project_state()
        assignments = state.get('thread-project-assignments', {})
        projects = state.get('local-projects', {})
        roots = self.project_roots(state)
        roots = {identity: [str(Path(path).resolve()) for path in paths if Path(path).is_absolute()]
                 for identity, paths in roots.items()}
        names = {p['id']: p['name'] for p in self.projects()}
        projectless = set(state.get('projectless-thread-ids', []))
        titles = state.get('thread-titles', {}).get('titles', {})
        result = []
        for identity, title, project, cwd, project_id in rows:
            try:
                assignment = assignments.get(identity)
                if assignment:
                    project_id = assignment.get('projectId')
                    saved = projects.get(project_id, {})
                    project = saved.get('name') or project
                elif identity in projectless:
                    project, project_id = None, None
                elif not project_id:
                    # Legacy chats can lack project_id; use the saved project roots,
                    # including nested roots, instead of guessing from a folder name.
                    cwd = str(Path(cwd).resolve()) if cwd and Path(cwd).is_absolute() else None
                    matches = [(len(root), key, names.get(key)) for key, paths in roots.items()
                               for root in paths
                               if cwd and (cwd == root or cwd.startswith(root.rstrip('/') + '/'))]
                    _, project_id, project = max(matches, default=(0, None, None), key=lambda p: p[0])
                # title/first_user_message are prompt-derived; name is the sidebar title.
                result.append({'id': identity, 'title': title or titles.get(identity) or 'Untitled chat',
                               'project': project or ('Unnamed project' if project_id else 'No project'),
                               'project_id': self.project_id(project_id, state) if project_id else PROJECTLESS})
            except (OSError, EOFError, RuntimeError, ValueError, KeyError):
                continue
        return result

    def sessions(self):
        # Keep metadata refresh off the audio/control connection so buttons and
        # one-second snapshots remain responsive even with a large chat catalog.
        with self._lock:
            if not self._refreshing and time.monotonic() - self._refreshed > 10:
                self._refreshing = True
                def refresh():
                    found = []
                    try:
                        found = self._scan_sessions()
                    except (OSError, EOFError, RuntimeError, sqlite3.Error, ValueError, KeyError):
                        pass
                    finally:
                        with self._lock:
                            self._sessions = found
                            self._refreshing = False
                            self._refreshed = time.monotonic()
                threading.Thread(target=refresh, daemon=True).start()
            return [s for s in self._sessions if not self.new_chats.owns(s['id'])]

    def send(self, thread, text):
        if self.new_chats.owns(thread):
            raise RuntimeError('The first CLI turn is still running')
        owner = self.owner(thread)
        request = {'conversationId': thread, 'turnStart': {
            'request': {'threadId': thread, 'input': [{'type': 'text', 'text': text, 'text_elements': []}]},
            'context': {'inheritThreadSettings': True}}}
        return self.request('thread-follower-start-turn', request, 2, owner)

    def stage(self, thread, text):
        """Fill voice text once, without reading or acknowledging the PC input."""
        if sys.platform != 'darwin':
            raise RuntimeError('Desktop composer integration currently requires macOS')
        if not text.strip() or len(text) > 12000:
            raise ValueError('Voice text empty or too long')
        if self.new_chats.owns(thread):
            raise RuntimeError('The first CLI turn is still running')
        url = 'codex://threads/' + quote(thread, safe='') + '?' + urlencode({'prompt': text})
        subprocess.run(['open', '-b', 'com.openai.codex', url], check=True, timeout=5,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)



class Broker:
    def __init__(self):
        self.lock = threading.RLock()
        self.pending = {}

    def add(self, value):
        identity = uuid.uuid4().hex
        with self.lock:
            self.pending[identity] = {'id': identity, 'thread': value['session_id'],
                'text': value.get('tool_name', 'Tool') + '\n' + json.dumps(value.get('tool_input', {}), ensure_ascii=False, indent=2),
                'expires': time.monotonic() + 115, 'answer': None, 'event': threading.Event()}
            return self.pending[identity]

    def find(self, thread):
        with self.lock:
            return next((v for v in self.pending.values() if v['thread'] == thread and
                         v['answer'] is None and time.monotonic() < v['expires']), None)

    def resolve(self, identity, thread, answer):
        with self.lock:
            value = self.pending.get(identity)
            if not value or value['thread'] != thread or value['answer'] is not None or time.monotonic() >= value['expires']:
                return False
            value['answer'] = answer
            value['event'].set()
            return True

    def invalidate(self, thread):
        with self.lock:
            for value in self.pending.values():
                if value['thread'] == thread:
                    value['event'].set()
                    value['expires'] = 0

    def listen(self):
        def handle(sock):
            identity = None
            try:
                sock.settimeout(120)
                size = struct.unpack('!I', exact(sock, 4))[0]
                if not 1 <= size <= 65536:
                    return
                value = json.loads(exact(sock, size))
                if value.get('hook_event_name') != 'PermissionRequest' or not isinstance(value.get('session_id'), str):
                    return
                item = self.add(value)
                identity = item['id']
                item['event'].wait(115)
                with self.lock:
                    answer = item['answer']
                    result = {} if not answer else {'hookSpecificOutput': {'hookEventName': 'PermissionRequest', 'decision': {'behavior': answer}}}
                sock.sendall(json.dumps(result).encode() + b'\n')
            except (OSError, EOFError, ValueError, TypeError):
                pass
            finally:
                if identity:
                    with self.lock:
                        self.pending.pop(identity, None)
                sock.close()
        server = socket.socket()
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(('127.0.0.1', APPROVAL_PORT))
        server.listen(4)
        self.server = server
        def accept():
            while True:
                try:
                    sock, _ = server.accept()
                except OSError:
                    return
                with self.lock:
                    busy = len(self.pending) >= 8
                if busy:
                    sock.close()
                else:
                    threading.Thread(target=handle, args=(sock,), daemon=True).start()
        threading.Thread(target=accept, daemon=True).start()


def permission_hook(value):
    try:
        body = json.dumps(value).encode()
        if len(body) > 65536:
            return {}
        with socket.create_connection(('127.0.0.1', APPROVAL_PORT), timeout=0.2) as sock:
            sock.settimeout(118)
            sock.sendall(struct.pack('!I', len(body)) + body)
            result = bytearray()
            while len(result) < 1024:
                part = sock.recv(1024)
                if not part:
                    break
                result.extend(part)
                if b'\n' in part:
                    return json.loads(result)
    except (OSError, ValueError):
        pass
    return {}


class UnsupportedText(ValueError):
    pass


class Renderer:
    def __init__(self, font=None):
        from PIL import ImageFont
        from fontTools.ttLib import TTFont
        # Render locally, without redistributing the system's font asset.
        source = str(font or '/System/Library/Fonts/Supplemental/Arial Unicode.ttf')
        self.source = source
        self.font = ImageFont.truetype(source, 16)
        with TTFont(source, fontNumber=0) as asset:
            self.coverage = set(asset.getBestCmap())
        self.cache = {}

    def pages(self, text):
        for char in text:
            if char != '\n' and ord(char) not in self.coverage:
                raise UnsupportedText(f'Unsupported U+{ord(char):04X}.\nReview on PC.\nHold DOWN to dismiss.')
        lines, line = [], ''
        for char in text:
            if char == '\n':
                lines.append(line); line = ''
            else:
                if self.font.getlength(line + char) > WIDTH - 8:
                    lines.append(line); line = ''
                line += char
        lines.append(line)
        # The seventh visible line is reserved for the review page number.
        return ['\n'.join(lines[i:i+6]) for i in range(0, len(lines), 6)] or ['']

    def bitmap(self, text, selection=None):
        from PIL import Image, ImageDraw
        key = (text, selection)
        if key in self.cache:
            return self.cache[key]
        image = Image.new('1', (WIDTH, HEIGHT))
        draw = ImageDraw.Draw(image)
        if selection is None:
            draw.multiline_text((4, 0), text, font=self.font, fill=1, spacing=LINE_SPACING)
        else:
            # Five entries use at most eleven lines, including the selected title's wrap.
            # Invert the whole selected chat (title and project), not just its marker.
            lines = text.split('\n')
            first, end = selection
            if not 0 <= first < end <= len(lines) <= HEIGHT // LIST_LINE_HEIGHT:
                raise ValueError('Invalid selected chat layout')
            draw.rounded_rectangle((0, first * LIST_LINE_HEIGHT, WIDTH - 1,
                                    end * LIST_LINE_HEIGHT - 1), radius=5, fill=1)
            for index, line in enumerate(lines):
                bounds = draw.textbbox((0, 0), line, font=self.font, anchor='lt')
                if bounds[2] > WIDTH - 8 or bounds[3] > LIST_LINE_HEIGHT:
                    raise ValueError('Selected chat text exceeds panel')
                draw.text((4, index * LIST_LINE_HEIGHT + (LIST_LINE_HEIGHT - bounds[3]) // 2), line,
                          font=self.font, anchor='lt', fill=0 if first <= index < end else 1)
        result = image.tobytes()
        if len(self.cache) > 50:
            self.cache.clear()
        self.cache[key] = result
        return result

    def summary(self, text, count=1):
        """Fit metadata to a row without slicing Unicode at an arbitrary length."""
        text = ' '.join(text.split())
        lines = self.pages(text)[0].split('\n')
        if len(lines) > count:
            lines = lines[:count]
            end = lines[-1]
            while end and self.font.getlength(end + '…') > WIDTH - 8:
                end = end[:-1]
            lines[-1] = end + '…'
        return lines


class SelectionMemory:
    """Keep only the chosen IDs in a private local file; never store chat text."""
    def __init__(self, path=None):
        self.path = Path(path) if path else None
        self.project = self.target = None
        if self.path:
            try:
                if self.path.stat().st_size > 8192:
                    return
                value = json.loads(self.path.read_text())
                if isinstance(value, dict) and all(isinstance(value.get(k), str) and
                        0 < len(value[k]) <= 256 for k in ('project', 'target')):
                    self.project, self.target = value['project'], value['target']
            except (OSError, ValueError):
                pass

    def remember(self, project, target):
        if not project or not target or (project, target) == (self.project, self.target):
            return
        self.project, self.target = project, target
        if self.path:
            temporary = None
            try:
                fd, temporary = tempfile.mkstemp(prefix='.pet-selection-', dir=self.path.parent)
                with os.fdopen(fd, 'w') as output:
                    json.dump({'project': project, 'target': target}, output)
                os.replace(temporary, self.path)
            except OSError:
                pass  # In-memory restoration remains available if disk is read-only.
            finally:
                if temporary and os.path.exists(temporary):
                    os.unlink(temporary)


class Review:
    def __init__(self, desktop, broker, renderer, selection=None):
        self.desktop, self.broker, self.renderer = desktop, broker, renderer
        self.selection = selection if selection is not None else SelectionMemory()
        self.sessions = []
        self.projects = []
        self.project = self.selection.project
        self.last_targets = ({self.selection.project: self.selection.target}
                             if self.selection.target else {})
        self.return_mode = 1
        self.target = None
        self.mode = 7
        self.token = uuid.uuid4().hex
        self.text = ''
        self.pages = ['']
        self.page = 0
        self.seen = set()
        self.pending = None
        self.error = ''
        self.expires = 0
        self.refresh_at = 0
        self.recording_text = ''
        self.new_project = None
        self.new_job = None

    @staticmethod
    def session_project(session):
        return session.get('project_id', session.get('project', PROJECTLESS))

    def project_sessions(self):
        return [s for s in self.sessions if self.session_project(s) == self.project]

    def refresh_lists(self):
        previous = (self.sessions, self.projects, self.project, self.target)
        try:
            sessions = self.desktop.sessions()
            projects = {p['id']: dict(p) for p in self.desktop.projects()}
            for session in sessions:
                identity = self.session_project(session)
                projects.setdefault(identity, {'id': identity, 'name': session.get('project', 'No project')})
            self.sessions, self.projects = sessions, list(projects.values())
            self.error = ''
        except (OSError, EOFError, RuntimeError, sqlite3.Error, ValueError, KeyError):
            self.sessions, self.projects = [], []
            self.error = 'Desktop unavailable'
        ids = [p['id'] for p in self.projects]
        if self.project not in ids:
            self.project = ids[0] if ids else None
            if self.mode == 1:
                self.change(7)
        if self.mode == 7:
            self.target = None
        else:
            ids = [s['id'] for s in self.project_sessions()]
            if self.target not in ids:
                remembered = self.last_targets.get(self.project)
                self.target = remembered if remembered in ids else (ids[0] if ids else None)
        if previous != (self.sessions, self.projects, self.project, self.target):
            self.token = uuid.uuid4().hex

    def change(self, mode, text='', pending=None):
        self.mode, self.text, self.pending = mode, text, pending
        self.token = uuid.uuid4().hex
        try:
            self.pages = self.renderer.pages(text)
        except UnsupportedText as error:
            self.mode, self.text = 4, ''
            self.pages = self.renderer.pages(str(error))
        self.page = 0
        self.seen = {0}
        self.expires = time.monotonic() + 180

    def sync(self):
        now = time.monotonic()
        if self.mode in (2, 3) and (now >= self.expires or (self.pending and not self.broker.find(self.target))):
            self.change(1)
        if self.new_project is not None:
            return  # Pin the new-chat draft; never fall back to an existing session.
        if self.mode == 8 and self.new_job:
            job = self.desktop.new_status(self.new_job)
            if job and job['status'] in ('complete', 'failed'):
                if job['status'] == 'failed':
                    self.new_job = None
                    self.change(4, 'New chat not confirmed.\nCheck chat on PC.\nDo not retry blindly.')
                    return
                self.refresh_lists()
                if any(s['id'] == job['thread'] for s in self.project_sessions()):
                    self.target, self.new_job = job['thread'], None
                    self.last_targets[self.project] = self.target
                    self.selection.remember(self.project, self.target)
                    self.return_mode = 1
                    self.change(1)
                else:
                    self.target = None
            return
        if self.mode not in (1, 7):
            return
        if now >= self.refresh_at:
            self.refresh_at = now + 1
            self.refresh_lists()
        pending = self.broker.find(self.target) if self.mode == 1 and self.target else None
        if pending:
            self.change(3, pending['text'], pending['id'])

    def action(self, command, token):
        self.sync()
        if command == 'sessions':
            # Wake is navigation only: a refreshed list token must not prevent
            # opening it. Voice/approval screens resume without any confirmation.
            if self.mode == 5:
                return False
            if self.new_project is not None:
                self.token = uuid.uuid4().hex
                return True
            if self.mode in (1, 7):
                ids = [p['id'] for p in self.projects]
                if self.selection.project in ids:
                    self.project = self.selection.project
                sessions = [s['id'] for s in self.project_sessions()]
                remembered = self.last_targets.get(self.project)
                self.target = remembered if remembered in sessions else (sessions[0] if sessions else None)
                self.change(1 if self.project is not None else 7)
                if self.target:
                    self.last_targets[self.project] = self.target
                self.selection.remember(self.project, self.target)
            else:
                self.token = uuid.uuid4().hex
            return True
        if token != self.token:
            return False
        if self.mode == 5:
            return False
        if command == 'back' and self.mode == 7:
            return False
        if command == 'back' and self.mode == 1:
            if self.target:
                self.last_targets[self.project] = self.target
            self.target = None
            self.new_project = None
            self.change(7)
        elif command in ('cancel', 'back'):
            if self.pending:
                self.broker.resolve(self.pending, self.target, 'deny')
            self.new_job = None
            self.change(self.return_mode if self.mode in (4, 8) else 1)
            self.return_mode = 1
        elif command == 'new' and self.mode == 7 and self.project is not None:
            # Consume the physical action before invoking the desktop. A lost
            # acknowledgement must not prepare another draft automatically.
            self.return_mode = 7
            if self.project == PROJECTLESS:
                self.change(4, 'No saved project.\nCreate a standalone chat\non PC. Hold UP: Projects')
                return False
            self.change(8, 'Preparing new chat.')
            try:
                self.desktop.new_session(self.project)
                self.target = None
                self.new_project = self.project
                self.return_mode = 1
                self.change(1)
            except (OSError, RuntimeError, ValueError, sqlite3.Error, subprocess.SubprocessError):
                self.change(4, 'New chat unavailable.\nCheck local project\nand Codex CLI on PC.\nHold UP: Projects')
        elif command in ('up', 'down'):
            if self.mode == 7 and self.projects:
                ids = [p['id'] for p in self.projects]
                self.project = ids[(ids.index(self.project) + (-1 if command == 'up' else 1)) % len(ids)]
                self.token = uuid.uuid4().hex
            elif self.mode == 1 and self.target:
                ids = [s['id'] for s in self.project_sessions()]
                self.target = ids[(ids.index(self.target) + (-1 if command == 'up' else 1)) % len(ids)]
                self.last_targets[self.project] = self.target
                self.selection.remember(self.project, self.target)
                self.token = uuid.uuid4().hex
            elif self.mode in (2, 3):
                if self.mode == 3 and command == 'down':
                    self.broker.resolve(self.pending, self.target, 'deny')
                    self.change(1)
                else:
                    self.page = (self.page + (-1 if command == 'up' and self.mode == 2 else 1)) % len(self.pages)
                    self.seen.add(self.page)
                    self.token = uuid.uuid4().hex
            else:
                return False
        elif command == 'ok' and self.mode == 7 and self.project is not None:
            ids = [s['id'] for s in self.project_sessions()]
            remembered = self.last_targets.get(self.project)
            self.target = remembered if remembered in ids else (ids[0] if ids else None)
            if self.target:
                self.last_targets[self.project] = self.target
                self.selection.remember(self.project, self.target)
            self.change(1)
        elif command == 'ok' and (self.mode == 2 or
                                  (self.mode == 3 and len(self.seen) == len(self.pages))):
            target, mode, pending, text = self.target, self.mode, self.pending, self.text
            if mode == 2 and self.new_project is not None:
                project, self.new_project = self.new_project, None
                self.return_mode = 7
                self.change(8, 'New chat submitted.\nWaiting for first reply.\nHold UP: Projects')
                try:
                    self.new_job = self.desktop.send_new(project, text)
                except (OSError, EOFError, RuntimeError, ValueError, KeyError, sqlite3.Error, subprocess.SubprocessError):
                    self.change(4, 'New chat not confirmed.\nCheck chat on PC.\nDo not retry blindly.')
                return True
            # Consume first: an uncertain desktop response must never resend automatically.
            self.change(1)
            if mode == 3:
                return self.broker.resolve(pending, target, 'allow')
            try:
                self.desktop.send(target, text)
            except (OSError, EOFError, RuntimeError, ValueError, KeyError):
                self.change(4, 'Send not confirmed.\nCheck chat on PC.\nDo not retry blindly.')
        elif command == 'record' and self.mode in (1, 2) and (self.target or self.new_project is not None):
            if self.target and self.broker.find(self.target):
                return False
            self.recording_text = self.text if self.mode == 2 else ''
            self.change(5, 'Recording...\nRelease OK to transcribe\nMaximum: 30 seconds')
        else:
            return False
        return True

    def transcript(self, text):
        if self.mode != 5:
            return
        previous, self.recording_text = self.recording_text, ''
        if text.strip():
            voice = previous + text.strip()
            if len(voice) > 12000:
                self.change(4, 'Voice text limit reached.\nHold UP to start again.')
                return
            self.change(2, voice)
            try:
                if self.new_project is None:
                    self.desktop.stage(self.target, voice)
            except (OSError, EOFError, RuntimeError, ValueError, KeyError, subprocess.SubprocessError):
                pass  # The transcript remains available even if desktop filling fails.
        elif previous:
            self.change(2, previous)
        else:
            self.change(4, 'No speech recognized.\nPress any key to dismiss.')

    def screen(self):
        self.sync()
        selection = None
        if self.mode == 7:
            if self.projects:
                lines, selection = self.project_rows()
                content = '\n'.join(lines)
            else:
                content = self.error or 'No projects.\nOpen Codex on PC.'
        elif self.mode == 1:
            if self.new_project is not None:
                project = next((p['name'] for p in self.projects if p['id'] == self.new_project), 'Project')
                try:
                    heading = '\n'.join(self.renderer.summary(project, 2))
                except UnsupportedText:
                    heading = 'Project: view on PC'
                content = heading + '\nNew chat\nHold OK to record.\nReview, then OK to send.'
            elif self.target:
                lines, selection = self.session_rows()
                content = '\n'.join(lines)
            else:
                project = next((p['name'] for p in self.projects if p['id'] == self.project), 'Project')
                try:
                    heading = '\n'.join(self.renderer.summary(project, 2))
                except UnsupportedText:
                    heading = 'Project: view on PC'
                content = heading + '\nNo sessions yet.\nCreate a chat on PC.\nHold UP: Projects'
        else:
            content = self.pages[self.page] + f'\n[{self.page+1}/{len(self.pages)}]'
        return bytes([self.mode]) + bytes.fromhex(self.token) + self.renderer.bitmap(content, selection=selection)

    def session_list(self):
        return '\n'.join(self.session_rows()[0])

    def session_rows(self):
        sessions = self.project_sessions()
        index = [s['id'] for s in sessions].index(self.target)
        start = max(0, min(index - 1, len(sessions) - LIST_ENTRIES))
        lines, selection = [], None
        for i in range(start, min(start + LIST_ENTRIES, len(sessions))):
            session = sessions[i]
            selected = i == index
            prefix = '' if selected else '  '
            try:
                row = self.renderer.summary(prefix + session['title'], 2 if selected else 1)
                # Projects come from Codex's named project record, never the prompt.
                row.extend(self.renderer.summary(session.get('project', 'No project') +
                           (' / ' + session['id'][-8:] if selected else ''), 1))
            except UnsupportedText:
                row = [prefix + 'Title: view on PC', 'Unsupported project/title']
            if selected:
                selection = (len(lines), len(lines) + len(row))
            lines.extend(row)
        return lines, selection

    def project_rows(self):
        index = [p['id'] for p in self.projects].index(self.project)
        start = max(0, min(index - 1, len(self.projects) - LIST_ENTRIES))
        lines, selection = [], None
        for i in range(start, min(start + LIST_ENTRIES, len(self.projects))):
            project = self.projects[i]
            selected = i == index
            count = sum(self.session_project(s) == project['id'] for s in self.sessions)
            try:
                row = self.renderer.summary(('' if selected else '  ') + project['name'], 2 if selected else 1)
            except UnsupportedText:
                row = ['Project: view on PC']
            row.extend(self.renderer.summary(f'{count} sessions', 1))
            if selected:
                selection = (len(lines), len(lines) + len(row))
            lines.extend(row)
        return lines, selection


class Transcriber:
    def __init__(self, model, executable='whisper-cli', chinese_script='simplified', backend='auto'):
        self.model, self.executable = Path(model), executable
        if not self.model.is_file():
            raise ValueError('Whisper model missing; configure --model before recording')
        conversions = {'simplified': 't2s', 'traditional': 's2t', 'keep': None}
        if chinese_script not in conversions:
            raise ValueError('Unsupported Chinese script')
        self.converter = None
        if conversions[chinese_script]:
            from opencc import OpenCC
            self.converter = OpenCC(conversions[chinese_script])
        if backend not in ('auto', 'server', 'cli'):
            raise ValueError('Unsupported transcription backend')
        server = shutil.which('whisper-server') if backend != 'cli' else None
        if backend == 'server' and not server:
            raise ValueError('whisper-server missing; install whisper.cpp or use --asr-backend cli')
        self.worker = WhisperWorker(self.model, server) if server else None

    def start(self):
        if self.worker:
            self.worker.start()

    def close(self):
        if self.worker:
            self.worker.close()

    def __call__(self, pcm):
        if len(pcm) < 16000:
            return ''
        if len(pcm) % 2 or len(pcm) > 960000:
            raise ValueError('Invalid recording size')
        if self.worker:
            return self.normalize(self.worker(pcm))
        with tempfile.TemporaryDirectory(prefix='passport-voice-') as directory:
            file = Path(directory) / 'voice.wav'
            with wave.open(str(file), 'wb') as wav:
                wav.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
                wav.writeframes(pcm)
            out = Path(directory) / 'text'
            subprocess.run([self.executable, '-m', str(self.model), '-f', str(file), '-l', 'auto',
                            '-otxt', '-of', str(out), '-np'], timeout=65, check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return self.normalize(out.with_suffix('.txt').read_text())

    def normalize(self, text):
        if self.converter:
            text = self.converter.convert(text)
        text = finish_sentence(text)
        if len(text) > 12000:
            raise ValueError('Transcript too long')
        return text


class InteractionServer:
    def __init__(self, key, model, bind, font=None, desktop=None, chinese_script='simplified', asr_backend='auto'):
        self.key, self.bind = key, bind
        self.desktop = desktop or Desktop()
        self.broker = Broker()
        self.renderer = Renderer(font)
        from dashboard import DashboardRenderer
        self.dashboard = DashboardRenderer(self.renderer)
        self.tracker = None
        self.transcribe = Transcriber(model, chinese_script=chinese_script, backend=asr_backend)
        self.active = threading.Lock()
        self.target = None
        self.selection = SelectionMemory(self.desktop.root / 'codex-pet-selection.json'
                                         if hasattr(self.desktop, 'root') else None)

    def start(self):
        self.transcribe.start()
        self.broker.listen()
        server = socket.socket()
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((self.bind, CONTROL_PORT))
        server.listen(2)
        self.server = server
        def loop():
            while True:
                try:
                    sock, _ = server.accept()
                except OSError:
                    return
                threading.Thread(target=self.handle, args=(sock,), daemon=True).start()
        threading.Thread(target=loop, daemon=True).start()

    def handle(self, sock):
        if not self.active.acquire(False):
            sock.close(); return
        pcm = bytearray()
        try:
            sock.settimeout(4)
            wire = SecureChannel(sock, self.key, server=True)
            sock.settimeout(75)
            review = Review(self.desktop, self.broker, self.renderer, self.selection)
            while True:
                data = wire.receive()
                if data[0] == 2:
                    if review.mode != 5 or len(pcm) + len(data) - 1 > 16000 * 2 * 30:
                        raise ValueError('Invalid audio stream')
                    pcm.extend(data[1:])
                    continue
                if data[0] != 1:
                    raise ValueError('Invalid action')
                value = json.loads(data[1:])
                command = value.get('cmd')
                if command == 'stop' and review.mode == 5 and value.get('token') == review.token:
                    try:
                        review.transcript(self.transcribe(pcm))
                    except (OSError, ValueError, subprocess.SubprocessError):
                        review.change(4, 'Transcription failed.\nNothing was sent.\nPress any key to dismiss.')
                    pcm.clear()
                elif command != 'sync':
                    review.action(command, value.get('token'))
                screen = review.screen()
                self.target = review.target
                wire.send(screen)
                # Opt-in keeps older clients' single-response framing intact.
                # The home view is read-only and never selects an action target.
                if value.get('home') is True:
                    from dashboard import overview
                    activity = self.tracker.activity(time.monotonic()) if self.tracker else {}
                    with self.broker.lock:
                        pending = [p['thread'] for p in self.broker.pending.values()
                                   if not p['answer'] and p['expires'] > time.monotonic()]
                    model = overview(activity, self.desktop.sessions(), pending)
                    wire.send(self.dashboard.frame(model))
        except (OSError, EOFError, ValueError, KeyError):
            pass
        finally:
            pcm.clear()
            sock.close()
            self.target = None
            self.active.release()

    def close(self):
        self.transcribe.close()
        if hasattr(self.desktop, 'new_chats'):
            self.desktop.new_chats.close()
        for server in (getattr(self, 'server', None), getattr(self.broker, 'server', None)):
            if server:
                server.close()
