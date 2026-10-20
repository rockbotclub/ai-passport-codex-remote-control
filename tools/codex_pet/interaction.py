"""Native desktop controls, physical approval broker and encrypted control transport.

Confirm operates native Send plus Codex or opt-in Doubao PC dictation.
No card microphone, bridge transcripts or CLI executor.
"""
from contextlib import closing
from messages import reason_text
import hashlib
import hmac
import json
import os
from pathlib import Path
import socket
import sqlite3
import struct
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from urllib.parse import quote

CONTROL_PORT, APPROVAL_PORT = 19285, 19286
WIDTH, HEIGHT = 216, 224
LINE_SPACING = 2
LIST_ENTRIES, LIST_LINE_HEIGHT = 5, 20
PIXELS = WIDTH * HEIGHT // 8
MAX_RECORD = 6144
PROJECTLESS = '__projectless__'
COMPOSER_DIAGNOSTIC_FIELDS = frozenset({
    'webAreas', 'shellAreas', 'missingURLs', 'otherURLs', 'links', 'targetLinks',
    'currentMarkers', 'numericCurrentMarkers', 'selectedLinks', 'treeLimit',
    'roots', 'visited', 'roleReadErrors', 'childReadErrors', 'childAPIDisabled',
    'childCannotComplete', 'listedWindows', 'mainWindow', 'focusedWindow', 'appChildren',
    'windowAttributeAvailable', 'windowAPIDisabled', 'windowCannotComplete',
    'appChildAttributeAvailable', 'appChildAPIDisabled', 'appChildCannotComplete',
    'enableAccepted', 'enableUnsupported', 'enableAPIDisabled', 'enableCannotComplete',
    'enableStatusAvailable', 'enabled',
    'enhancedRequested', 'enhancedAccepted', 'enhancedUnsupported', 'enhancedAPIDisabled',
    'enhancedCannotComplete', 'enhancedStatusAvailable', 'enhancedEnabled',
})
COMPOSER_TIMING_FIELDS = frozenset({'setup_ms', 'target_ms', 'controls_ms', 'press_ms', 'ready_ms'})
COMPOSER_CONTROL_FIELDS = frozenset({'editors', 'buttons', 'candidates', 'scan_complete',
    'submit_buttons', 'dictate_buttons', 'stop_buttons', 'resume_buttons', 'voice_buttons'})
COMPOSER_DRAFT_FIELDS = frozenset({'draft_route_ok', 'draft_current_chat',
    'draft_project_matches', 'draft_hero_matches', 'draft_project_conflicts', 'draft_scan_complete',
    'draft_buttons', 'draft_popups', 'draft_named_buttons', 'draft_partial_buttons', 'draft_hero_shapes',
    'draft_popup_matches'})


def report_composer_diagnostics(data):
    """Accept only fixed numeric schemas from the native helper's stderr."""
    if not isinstance(data, bytes):
        return
    for line in data.splitlines():
        try:
            values = json.loads(line)
            if not isinstance(values, dict):
                continue
            if set(values) == COMPOSER_DIAGNOSTIC_FIELDS and all(
                    type(value) in (int, bool) and 0 <= value <= 20000 for value in values.values()):
                print('电脑端会话发现统计：', json.dumps(values, sort_keys=True), flush=True)
            elif set(values) == COMPOSER_TIMING_FIELDS and all(
                    type(value) is int and 0 <= value <= 60000 for value in values.values()):
                print('电脑端原生操作耗时：', json.dumps(values, sort_keys=True), flush=True)
            elif set(values) == COMPOSER_CONTROL_FIELDS and all(
                    type(value) is int and 0 <= value <= 20000 for value in values.values()):
                print('电脑端原生控件统计：', json.dumps(values, sort_keys=True), flush=True)
            elif set(values) == COMPOSER_DRAFT_FIELDS and all(
                    type(value) in (int, bool) and 0 <= value <= 20000 for value in values.values()):
                print('电脑端新会话定位统计：', json.dumps(values, sort_keys=True), flush=True)
        except (TypeError, ValueError, UnicodeError):
            pass


def exact(sock, n):
    result = bytearray()
    while len(result) < n:
        part = sock.recv(n - len(result))
        if not part:
            raise EOFError('连接已关闭')
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
                raise ValueError('通信协议不匹配')
            client = hello[4:]
            own = os.urandom(16)
            seed = client + own
            sock.sendall(own + hmac.digest(secret, b'server' + seed, 'sha256'))
            if not hmac.compare_digest(exact(sock, 32), hmac.digest(secret, b'client' + seed, 'sha256')):
                raise ValueError('配对失败')
        else:
            client = os.urandom(16)
            sock.sendall(b'CPG1' + client)
            response = exact(sock, 48)
            seed = client + response[:16]
            if not hmac.compare_digest(response[16:], hmac.digest(secret, b'server' + seed, 'sha256')):
                raise ValueError('配对失败')
            sock.sendall(hmac.digest(secret, b'client' + seed, 'sha256'))
        c2s = AESGCM(hmac.digest(secret, b'CPG1' + seed + b'C', 'sha256'))
        s2c = AESGCM(hmac.digest(secret, b'CPG1' + seed + b'S', 'sha256'))
        self.tx, self.rx = (s2c, c2s) if server else (c2s, s2c)
        self.sent = self.received = 0

    def send(self, payload):
        if not 1 <= len(payload) <= MAX_RECORD - 16:
            raise ValueError('数据包过大')
        self.sent += 1
        nonce = b'\0' * 4 + self.sent.to_bytes(8, 'big')
        body = self.tx.encrypt(nonce, payload, b'CPG1')
        self.sock.sendall(struct.pack('!H', len(body)) + body)

    def receive(self):
        from cryptography.exceptions import InvalidTag
        size = struct.unpack('!H', exact(self.sock, 2))[0]
        if not 17 <= size <= MAX_RECORD:
            raise ValueError('数据包长度无效')
        self.received += 1
        nonce = b'\0' * 4 + self.received.to_bytes(8, 'big')
        try:
            return self.rx.decrypt(nonce, exact(self.sock, size), b'CPG1')
        except InvalidTag:
            raise ValueError('数据包认证失败') from None


class ComposerActionError(RuntimeError):
    """A selected composer action was unavailable or its outcome is unknown."""

    def __init__(self, reason):
        self.reason = reason
        super().__init__('电脑端输入框操作失败：' + reason_text(reason))


class Desktop:
    """Read desktop status and operate the selected UI without a second executor."""
    def __init__(self, root=None, dictation_backend='codex'):
        if dictation_backend not in ('codex', 'doubao'):
            raise ValueError('不支持此语音输入方式')
        self.dictation_backend = dictation_backend
        self._doubao = None
        self.root = Path(root or Path.home() / '.codex')
        self._sessions = []
        self._refreshing = False
        self._refreshed = 0
        self._refresh_attempted = 0
        self._lock = threading.Lock()
        self._projects = []
        self._projects_refreshed = 0
        self._composer_helper_dir = None
        self._new_composer = None

    def project_state(self):
        try:
            state = json.loads((self.root / '.codex-global-state.json').read_text())
        except FileNotFoundError:
            return {}
        if not isinstance(state, dict):
            raise ValueError('无法识别电脑端项目状态')
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
                records = {identity: {'id': identity, 'name': name or '未命名项目'}
                           for identity, name in db.execute('SELECT id,name FROM projects ORDER BY name,id')}
            for identity, project in state.get('local-projects', {}).items():
                identity = self.project_id(identity, state)
                records[identity] = {'id': identity, 'name': project.get('name') or '未命名项目'}
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

    def open_chat(self, thread):
        if sys.platform != 'darwin':
            return
        url = 'codex://threads/' + quote(thread, safe='')
        subprocess.run(['open', '-b', 'com.openai.codex', url], check=True, timeout=5,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        with self._lock:
            self._refreshed = 0

    def invalidate_sessions(self):
        with self._lock:
            self._refreshed = 0

    def open_new_chat(self, project):
        """Open Codex's native new-chat composer in the selected saved project."""
        if sys.platform != 'darwin':
            raise RuntimeError('电脑端新建会话需要 macOS')
        if not project or project == PROJECTLESS:
            raise ValueError('请先选择一个已保存的项目')
        # Resolve by ID, never by display name or a guessed working directory.
        self._projects_refreshed = 0
        if project not in {item['id'] for item in self.projects()}:
            raise ValueError('所选项目已不存在')
        name = next(item['name'] for item in self.projects() if item['id'] == project)
        if sum(item['name'] == name for item in self.projects()) != 1:
            raise ValueError('项目重名，请先在电脑上区分项目名称')
        # Session membership uses app-server IDs after migration, but the
        # installed new-thread deep-link handler indexes local-projects by its
        # original desktop ID. Resolve only through the explicit saved mapping.
        state = self.project_state()
        native_projects = [identity for identity in state.get('local-projects', {})
                           if self.project_id(identity, state) == project]
        if len(native_projects) != 1:
            raise ValueError('电脑端项目不可用')
        native_project = native_projects[0]
        baseline = {session['id'] for session in self._scan_sessions()}
        # /threads/new with only projectId discards the project in the installed
        # desktop parser. /new uses its native project-aware newThread handler.
        url = 'codex://new?mode=codex&projectId=' + quote(native_project, safe='')
        subprocess.run(['open', '-b', 'com.openai.codex', url], check=True, timeout=5,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self._new_composer = {'id': '@new:' + uuid.uuid4().hex, 'title': '新会话',
                              'project_id': project, 'project': name, 'baseline': baseline}
        return dict(self._new_composer)

    def _ipc_socket(self, timeout):
        path = self.root / 'ipc/ipc.sock'
        if path.stat().st_uid != os.getuid() or path.parent.stat().st_mode & 0o022:
            raise RuntimeError('电脑端通信端点的所有者不匹配')
        sock = socket.socket(socket.AF_UNIX)
        try:
            sock.settimeout(timeout)
            sock.connect(str(path))
        except BaseException:
            sock.close()
            raise
        return sock

    @staticmethod
    def _ipc_send(sock, value):
        body = json.dumps(value).encode()
        sock.sendall(struct.pack('<I', len(body)) + body)

    @staticmethod
    def _ipc_receive(sock, deadline):
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('等待电脑端响应超时')
            sock.settimeout(remaining)
            n = struct.unpack('<I', exact(sock, 4))[0]
            if n > 32 * 1024 * 1024:
                raise ValueError('电脑端响应数据过大')
            reply = json.loads(exact(sock, n))
            if not isinstance(reply, dict):
                raise ValueError('无法识别电脑端消息')
            if reply.get('type') != 'client-discovery-request':
                return reply
            # This observer owns no threads. Ignoring discovery would stall
            # other desktop clients until the router's timeout expires.
            Desktop._ipc_send(sock, {'type': 'client-discovery-response',
                                    'requestId': reply['requestId'], 'response': {'canHandle': False}})

    def _ipc_call(self, sock, client, name, arguments, version, deadline):
        identity = str(uuid.uuid4())
        value = {'type': 'request', 'requestId': identity, 'sourceClientId': client,
                 'version': version, 'method': name, 'params': arguments}
        self._ipc_send(sock, value)
        for _ in range(200):
            reply = self._ipc_receive(sock, deadline)
            if reply.get('requestId') == identity:
                if reply.get('resultType') != 'success':
                    raise RuntimeError('电脑端拒绝了请求')
                return reply
        raise RuntimeError('电脑端未响应')

    def activity_threads(self):
        return [thread for thread, root in self.activity_index().items() if root is not None]

    def activity_index(self):
        # Source includes internal agents whose agent_path can be NULL.
        from status_sync import thread_catalog
        with closing(sqlite3.connect(f'file:{self.root / "state_5.sqlite"}?mode=ro', uri=True)) as db:
            columns = {row[1] for row in db.execute('PRAGMA table_info(threads)')}
            source = 'source' if 'source' in columns else 'NULL'
            return thread_catalog(db.execute(
                f'SELECT id,archived,agent_path,{source} FROM threads ORDER BY updated_at DESC'))

    def activity_snapshots(self, threads):
        """Pipeline discovery so unloaded history cannot delay active tasks."""
        from status_sync import compact_snapshot
        with self._ipc_socket(12) as sock:
            deadline = time.monotonic() + 12
            client = self._ipc_call(sock, 'initializing-client', 'initialize',
                                    {'clientType': 'ai-passport'}, 0, deadline)['result']['clientId']
            pending, following = {}, {}
            def follow(thread, owner, enabled):
                self._ipc_send(sock, {'type': 'broadcast', 'sourceClientId': client, 'version': 1,
                    'method': 'thread-stream-following-changed', 'targetClientIds': [owner],
                    'params': {'hostId': 'local', 'conversationId': thread, 'following': enabled}})
            try:
                for thread in threads:
                    request = str(uuid.uuid4())
                    pending[request] = thread
                    self._ipc_send(sock, {'type': 'request', 'requestId': request,
                        'sourceClientId': client, 'version': 1, 'method': 'thread-owner-discovery',
                        'params': {'hostId': 'local', 'conversationId': thread}})
                while pending or following:
                    reply = self._ipc_receive(sock, deadline)
                    request = reply.get('requestId')
                    if reply.get('type') == 'response' and request in pending:
                        thread = pending.pop(request)
                        if reply.get('resultType') == 'success':
                            owner = reply['handledByClientId']
                            following[thread] = owner
                            follow(thread, owner, True)
                        else:
                            yield thread, None if reply.get('error') == 'no-client-found' else False
                        continue
                    params = reply.get('params', {})
                    if not isinstance(params, dict):
                        raise ValueError('无法识别电脑端状态快照参数')
                    thread = params.get('conversationId')
                    change = params.get('change', {})
                    if not isinstance(change, dict):
                        raise ValueError('无法识别电脑端状态快照变更')
                    if (thread in following and reply.get('method') == 'thread-stream-state-changed'
                            and reply.get('version') == 11 and reply.get('sourceClientId') == following[thread]
                            and params.get('hostId') == 'local' and change.get('type') == 'snapshot'):
                        owner = following.pop(thread)
                        follow(thread, owner, False)
                        try:
                            result = compact_snapshot(change['conversationState'])
                        except (KeyError, TypeError, ValueError):
                            result = False
                        yield thread, result
            except (OSError, EOFError):
                for thread in list(pending.values()) + list(following):
                    yield thread, False
            finally:
                for thread, owner in following.items():
                    try:
                        follow(thread, owner, False)
                    except OSError:
                        break

    def activity_snapshot(self, thread):
        with closing(self.activity_snapshots([thread])) as results:
            return next(results)[1]

    def _scan_sessions(self):
        # List saved chats independently of whether a desktop executor is loaded.
        # Owner discovery belongs to actions, never project membership/listing.
        catalog = self.activity_index()
        with self._lock:
            saved_titles = {session['id']: session['title'] for session in self._sessions}
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
            if catalog.get(identity) != identity:
                continue
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
                result.append({'id': identity, 'title': title or titles.get(identity) or saved_titles.get(identity) or '未命名会话',
                               'project': project or ('未命名项目' if project_id else '无项目'),
                               'project_id': self.project_id(project_id, state) if project_id else PROJECTLESS})
            except (OSError, EOFError, RuntimeError, ValueError, KeyError):
                continue
        return result

    def sessions(self, required=()):
        # Keep metadata refresh off the audio/control connection so buttons and
        # one-second snapshots remain responsive even with a large chat catalog.
        with self._lock:
            known = {hashlib.sha256(session['id'].encode()).hexdigest()[:32] for session in self._sessions}
            missing = any(identity not in known for identity in required if not identity.startswith('@'))
            now = time.monotonic()
            if (not self._refreshing and now - self._refresh_attempted >= 1
                    and (missing or now - self._refreshed > 10)):
                self._refreshing = True
                self._refresh_attempted = now
                def refresh():
                    found = None
                    try:
                        found = self._scan_sessions()
                    except (OSError, EOFError, RuntimeError, sqlite3.Error, ValueError, KeyError):
                        pass
                    finally:
                        with self._lock:
                            if found is not None:
                                self._sessions = found
                                self._refreshed = time.monotonic()
                            self._refreshing = False
                threading.Thread(target=refresh, daemon=True).start()
            return list(self._sessions)

    def send(self, thread):
        """Press Send once; the live UI owns payload, validation and clearing."""
        self.composer_action(thread, 'send')
        return True

    def prepare_composer(self):
        """Compile native controls without opening or interacting with an app."""
        if sys.platform != 'darwin':
            raise RuntimeError('原生输入框控制需要 macOS')
        if self._composer_helper_dir is None:
            directory = tempfile.TemporaryDirectory(prefix='passport-composer-')
            subprocess.run(['/usr/bin/clang', '-fobjc-arc', '-framework', 'AppKit',
                            '-framework', 'ApplicationServices',
                            str(Path(__file__).with_name('composer_action.m')),
                            '-o', str(Path(directory.name) / 'composer-action')],
                           check=True, timeout=20, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self._composer_helper_dir = directory
        if self.dictation_backend == 'doubao' and self._doubao is None:
            from doubao_dictation import DoubaoDictation
            self._doubao = DoubaoDictation(self._composer_helper_dir.name)
            self._doubao.prepare()

    def _composer_title(self, thread):
        """Read only chat names; control startup needs no project/path resolution."""
        with closing(sqlite3.connect(f'file:{self.root / "state_5.sqlite"}?mode=ro', uri=True)) as db:
            rows = db.execute('SELECT id,name FROM threads WHERE archived=0 AND agent_path IS NULL').fetchall()
        fallback = (self.project_state().get('thread-titles', {}).get('titles', {})
                    if any(not name for _, name in rows) else {})
        titles = {identity: name or fallback.get(identity) or '未命名会话' for identity, name in rows}
        title = titles.get(thread)
        return title if title and sum(value == title for value in titles.values()) == 1 else None

    def composer_action(self, thread, action):
        """Target one UI action; never read prompts or submit text via IPC."""
        if action not in ('send', 'dictate-start', 'dictate-stop', 'dictate-cancel'):
            raise ValueError('不支持此输入框操作')
        if sys.platform != 'darwin':
            raise RuntimeError('电脑端输入框不可用')
        started = time.monotonic()
        self.prepare_composer()
        draft = self._new_composer if self._new_composer and self._new_composer['id'] == thread else None
        if thread.startswith('@new:') and draft is None:
            raise ComposerActionError('chat-changed')
        if action in ('send', 'dictate-start') and not draft:
            self.open_chat(thread)
        navigated = time.monotonic()
        request = {'thread': thread, 'action': action}
        if draft:
            request['draftProject'] = draft['project']
        # New sidebar rows expose an accessible title/current marker, not href.
        # Supply a fresh title only when it uniquely identifies this saved chat.
        try:
            title = self._composer_title(thread) if not draft else None
            if title:
                request['title'] = title
        except (OSError, EOFError, RuntimeError, sqlite3.Error, ValueError, KeyError):
            pass  # URL-bound views still work; never guess a title on failure.
        catalogued = time.monotonic()
        try:
            if self.dictation_backend == 'doubao' and action != 'send':
                from doubao_dictation import DoubaoError
                try:
                    if action == 'dictate-start':
                        if draft:
                            self._doubao.start(thread, draft_project=draft['project'])
                        else:
                            self._doubao.start(thread, request.get('title'))
                    else:
                        report_composer_diagnostics(self._doubao.finish(thread, cancel=action == 'dictate-cancel'))
                except DoubaoError as error:
                    report_composer_diagnostics(error.diagnostics)
                    print('电脑端输入框操作结果：', reason_text(error.reason), flush=True)
                    raise ComposerActionError(error.reason) from error
                return
            completed = subprocess.run([str(Path(self._composer_helper_dir.name) / 'composer-action')],
                                       input=json.dumps(request).encode(),
                                       check=True, timeout=8, stdout=(subprocess.PIPE if action == 'dictate-start'
                                                                   else subprocess.DEVNULL), stderr=subprocess.PIPE)
            report_composer_diagnostics(completed.stderr)
        except subprocess.TimeoutExpired as error:
            report_composer_diagnostics(error.stderr)
            if action == 'dictate-start' and error.stdout == b'pressed\n':
                raise ComposerActionError('dictation-start-not-ready') from error
            raise
        except subprocess.CalledProcessError as error:
            # Helper diagnostics are numeric discovery counts only. Never log
            # arbitrary stderr, app labels, URLs, chat identities or input text.
            report_composer_diagnostics(error.stderr)
            if action == 'dictate-start' and error.stdout == b'pressed\n':
                raise ComposerActionError('dictation-start-not-ready') from error
            reasons = {10: 'accessibility-denied', 11: 'app-unavailable', 12: 'windows-unavailable',
                       13: 'chat-not-found', 14: 'multiple-chat-views', 15: 'writable-editor-not-found',
                       16: 'multiple-writable-editors', 18: 'press-unsupported',
                       19: 'press-not-acknowledged', 20: 'accessibility-tree-limit',
                       21: 'invalid-composer-request', 22: 'composer-button-unavailable',
                       23: 'multiple-composer-buttons', 24: 'chat-changed',
                       25: 'dictation-already-active', 26: 'dictation-start-not-ready',
                       27: 'accessibility-view-unavailable', 28: 'send-disabled',
                       29: 'send-input-required'}
            reason = reasons.get(error.returncode, 'helper-failed')
            print('电脑端输入框操作结果：', reason_text(reason), flush=True)
            raise ComposerActionError(reason) from error
        finally:
            print('电脑端输入框操作耗时：', {'send': '发送', 'dictate-start': '启动语音输入', 'dictate-stop': '结束语音输入', 'dictate-cancel': '取消语音输入'}[action],
                  '导航毫秒：', round((navigated - started) * 1000),
                  '目录查询毫秒：', round((catalogued - navigated) * 1000),
                  '原生操作毫秒：', round((time.monotonic() - catalogued) * 1000), flush=True)




class Broker:
    def __init__(self):
        self.lock = threading.RLock()
        self.pending = {}

    def add(self, value):
        identity = uuid.uuid4().hex
        with self.lock:
            self.pending[identity] = {'id': identity, 'thread': value['session_id'],
                'text': value.get('tool_name', '工具') + '\n' + json.dumps(value.get('tool_input', {}), ensure_ascii=False, indent=2),
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
        from ui_glyphs import REQUIRED_GLYPHS
        if not REQUIRED_GLYPHS <= self.coverage:
            raise ValueError('字体缺少中文提示所需字符，请使用 --font 指定完整的中文字体。')
        self.cache = {}

    def pages(self, text):
        for char in text:
            if char != '\n' and ord(char) not in self.coverage:
                raise UnsupportedText(f'不支持字符 U+{ord(char):04X}\n请在电脑上查看\n按任意键关闭提示')
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

    def bitmap(self, text, selection=None, fixed_rows=None):
        from PIL import Image, ImageDraw
        key = (text, selection, fixed_rows)
        if key in self.cache:
            return self.cache[key]
        image = Image.new('1', (WIDTH, HEIGHT))
        draw = ImageDraw.Draw(image)
        if selection is None:
            draw.multiline_text((4, 0), text, font=self.font, fill=1, spacing=LINE_SPACING)
        else:
            # Both lists reserve five equal slots even when fewer entries exist.
            lines = text.split('\n')
            first, end = selection
            if fixed_rows is not None and not 1 <= fixed_rows <= HEIGHT:
                raise ValueError('固定行数无效')
            row_height = HEIGHT // fixed_rows if fixed_rows else LIST_LINE_HEIGHT
            top = (HEIGHT - fixed_rows * row_height) // 2 if fixed_rows else 0
            limit = fixed_rows or HEIGHT // row_height
            if not 0 <= first < end <= len(lines) <= limit:
                raise ValueError('所选会话的布局无效')
            draw.rounded_rectangle((0, top + first * row_height, WIDTH - 1,
                                    top + end * row_height - 1), radius=5, fill=1)
            for index, line in enumerate(lines):
                bounds = draw.textbbox((0, 0), line, font=self.font, anchor='lt')
                if bounds[2] > WIDTH - 8 or bounds[3] > row_height:
                    raise ValueError('所选会话文字超出显示区域')
                draw.text((4, top + index * row_height + (row_height - bounds[3]) // 2), line,
                          font=self.font, anchor='lt', fill=0 if first <= index < end else 1)
        result = image.tobytes()
        if len(self.cache) > 50:
            self.cache.clear()
        self.cache[key] = result
        return result

    def summary(self, text, count=1):
        """Fit display text to rows by rendered width, preserving Unicode characters."""
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
        if not project or not target or target.startswith('@new:') or (project, target) == (self.project, self.target):
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
        self.dictation_thread = None
        self.pc_dictation_capable = False
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
        self.dictation_review = None
        self.draft = None

    @staticmethod
    def session_project(session):
        return session.get('project_id', session.get('project', PROJECTLESS))

    def project_sessions(self):
        return [s for s in self.sessions if self.session_project(s) == self.project]

    def refresh_lists(self):
        previous = (self.sessions, self.projects, self.project, self.target)
        try:
            if self.draft and self.draft['submitted']:
                self.desktop.invalidate_sessions()
            sessions = self.desktop.sessions()
            projects = {p['id']: dict(p) for p in self.desktop.projects()}
            if self.draft and self.draft['project_id'] in projects:
                created = [s for s in sessions if self.session_project(s) == self.draft['project_id']
                           and s['id'] not in self.draft['baseline']]
                if self.draft['submitted'] and created:
                    if self.target == self.draft['id']:
                        self.target = created[0]['id'] if len(created) == 1 else None
                        if self.target:
                            self.last_targets[self.draft['project_id']] = self.target
                            self.selection.remember(self.draft['project_id'], self.target)
                        else:
                            self.change(4, '发现多个新会话\n请返回后选择会话')
                    self.draft = None
                else:
                    sessions = [dict(self.draft)] + sessions
            for session in sessions:
                identity = self.session_project(session)
                projects.setdefault(identity, {'id': identity, 'name': session.get('project', '无项目')})
            self.sessions, self.projects = sessions, list(projects.values())
            self.error = ''
        except (OSError, EOFError, RuntimeError, sqlite3.Error, ValueError, KeyError):
            self.sessions, self.projects = [], []
            self.error = '电脑端暂不可用'
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
        # Only approvals expire; dictation is bounded by the control connection.
        if self.mode == 3 and (now >= self.expires or not self.broker.find(self.target)):
            self.change(1)
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
            if self.mode == 10:
                return False
            if self.mode in (1, 7):
                ids = [p['id'] for p in self.projects]
                preferred = self.draft['project_id'] if self.draft else self.selection.project
                if preferred in ids:
                    self.project = preferred
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
        if token != self.token or self.mode == 10:
            return False
        if command == 'back' and self.mode == 7:
            return False
        if command == 'back' and self.mode == 1:
            if self.target:
                self.last_targets[self.project] = self.target
            self.target = None
            self.change(7)
        elif command in ('cancel', 'back'):
            if self.mode == 4 and self.dictation_review is not None:
                self.restore_approval()
                return True
            if self.pending:
                self.broker.resolve(self.pending, self.target, 'deny')
            self.change(self.return_mode if self.mode == 4 else 1)
            self.return_mode = 1
        elif command == 'new' and self.mode == 7 and self.project is not None:
            self.return_mode = 7
            # Consume the token before native navigation; a timeout is never retried.
            self.change(1)
            try:
                baseline = {s['id'] for s in self.sessions}
                draft = self.desktop.open_new_chat(self.project)
                self.draft = {**draft, 'baseline': draft.get('baseline', baseline), 'submitted': False}
                self.target = draft['id']
                self.last_targets[self.project] = self.target
                self.return_mode = 1
                self.refresh_lists()
            except (OSError, RuntimeError, ValueError, KeyError, sqlite3.Error, subprocess.SubprocessError):
                self.change(4, '暂时无法新建会话\n请在电脑上检查 Codex\n和所选项目名称')
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
            elif self.mode == 3:
                if command == 'down':
                    self.broker.resolve(self.pending, self.target, 'deny')
                    self.change(1)
                else:
                    self.page = (self.page + 1) % len(self.pages)
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
        elif command == 'ok' and ((self.mode == 1 and self.target) or
                                  (self.mode == 3 and len(self.seen) == len(self.pages))):
            target, mode, pending = self.target, self.mode, self.pending
            # Consume before the native side effect; never retry uncertain sends.
            self.change(1)
            if mode == 3:
                return self.broker.resolve(pending, target, 'allow')
            try:
                if self.draft and target == self.draft['id']:
                    if self.draft['submitted']:
                        return False
                    self.draft['submitted'] = True
                    if not self.desktop.send(target):
                        self.draft['submitted'] = False
                        return False
                    self.desktop.invalidate_sessions()
                    self.refresh_at = 0
                    return True
                return self.desktop.send(target)
            except ComposerActionError as error:
                if self.draft and target == self.draft['id'] and error.reason not in (
                        'press-not-acknowledged', 'helper-failed'):
                    self.draft['submitted'] = False
                # These failures occur before Press. Only an uncertain dispatch
                # should tell the user that sending could already have happened.
                messages = {
                    'accessibility-denied': '暂时无法发送\n请在电脑上为连接程序\n开启辅助功能权限',
                    'app-unavailable': '暂时无法发送\n请在电脑上打开 Codex\n尚未发送任何内容',
                    'windows-unavailable': '暂时无法发送\n请在电脑上打开 Codex\n尚未发送任何内容',
                    'chat-not-found': '未找到所选会话\n请在电脑上打开该会话\n尚未发送任何内容',
                    'chat-changed': '所选会话已变化\n请在电脑上检查会话\n尚未发送任何内容',
                    'multiple-chat-views': '发现多个会话视图\n请在电脑上仅保留\n一个所选会话视图',
                    'writable-editor-not-found': '未找到输入框\n请在电脑上检查该会话\n尚未发送任何内容',
                    'multiple-writable-editors': '发现多个输入框\n请在电脑上关闭多余输入框\n尚未发送任何内容',
                    'press-unsupported': '暂时无法发送\n请在电脑上操作 Codex\n尚未发送任何内容',
                    'accessibility-tree-limit': '无法读取 Codex 界面\n请检查电脑端访问权限\n尚未发送任何内容',
                    'accessibility-view-unavailable': '无法读取 Codex 界面\n请检查电脑端访问权限\n尚未发送任何内容',
                    'composer-button-unavailable': '暂时无法发送\n请在电脑上检查输入框\n和会话控件',
                    'multiple-composer-buttons': '发现多个发送按钮\n请在电脑上检查会话\n尚未发送任何内容',
                    'send-disabled': '发送按钮不可用\n请在电脑上检查\n输入内容和附件',
                    'send-input-required': '暂无可发送内容\n返回后在电脑上输入\n或长按确认键语音输入',
                }
                self.change(4, messages.get(error.reason,
                    '尚未确认发送结果\n请在电脑上检查输入和会话\n确认结果后再决定是否重试'))
            except (OSError, EOFError, RuntimeError, ValueError, KeyError, sqlite3.Error,
                    subprocess.SubprocessError):
                self.change(4, '尚未确认发送结果\n请在电脑上检查输入和会话\n确认结果后再决定是否重试')
        elif command == 'record' and self.mode in (1, 3) and self.target:
            if self.draft and self.target == self.draft['id'] and self.draft['submitted']:
                return False
            return self.start_dictation()
        else:
            return False
        return True

    def start_dictation(self):
        """Use the selected PC dictation backend; release never submits."""
        if not self.pc_dictation_capable:
            self.change(4, '请更新设备固件\n以使用电脑端语音输入\n尚未启动录音')
            return False
        if not self.target:
            self.change(4, '请先在电脑上新建会话\n再在设备上选择该会话\n然后开始语音输入')
            return False
        prior = (self.text, self.pending, self.page, set(self.seen), self.expires) if self.mode == 3 else None
        target = self.target
        # Consume the physical token before any native side effect.
        backend = '豆包语音输入' if getattr(self.desktop, 'dictation_backend', 'codex') == 'doubao' else 'Codex 语音输入'
        self.change(10, f'使用电脑麦克风\n{backend}\n松开确认键插入文字')
        try:
            self.desktop.composer_action(target, 'dictate-start')
        except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
            # A failed press/readiness acknowledgement can still have started
            # capture. Cancel only our attempted capture in the same chat.
            if isinstance(error, ComposerActionError) and error.reason in (
                    'press-not-acknowledged', 'dictation-start-not-ready'):
                try:
                    self.desktop.composer_action(target, 'dictate-cancel')
                except (OSError, RuntimeError, ValueError, subprocess.SubprocessError):
                    pass
            reason = error.reason if isinstance(error, ComposerActionError) else 'helper-failed'
            messages = {
                'accessibility-denied': '语音输入暂不可用\n请在电脑上为连接程序\n开启辅助功能权限',
                'chat-not-found': '未找到所选会话\n请在电脑上打开该会话\n然后重试',
                'accessibility-view-unavailable': '无法读取 Codex 界面\n请检查电脑端访问权限\n并查看连接程序日志',
                'chat-changed': '所选会话已变化\n请在电脑上打开该会话\n然后重试',
                'multiple-chat-views': '发现多个会话视图\n请在电脑上仅保留\n一个所选会话视图',
                'multiple-writable-editors': '发现多个输入框\n请在电脑上关闭多余输入框\n然后重试',
                'dictation-already-active': '语音输入正在进行\n请先在电脑上结束录音\n再长按确认键',
                'composer-button-unavailable': '语音输入暂不可用\n请在电脑上检查\n所选会话的控件',
                'dictation-start-not-ready': '语音输入尚未就绪\n请在电脑上检查\n麦克风权限提示',
                'doubao-unavailable': '请在电脑上打开豆包输入法\n然后重试\n尚未启动录音',
                'doubao-input-required': '请在电脑上切换至豆包输入法\n并将长按语音快捷键\n设为左 Control 键',
                'modifier-held': '请松开电脑键盘上的\n修饰键\n然后重试',
                'codex-focus-required': '请将电脑上的 Codex\n切换到前台后重试',
                'composer-focus-failed': '输入框未获得焦点\n请在电脑上点击 Codex 输入框\n然后重试',
                'doubao-state-unavailable': '无法读取豆包状态\n请检查电脑端访问权限\n然后重试',
                'doubao-start-unconfirmed': '豆包语音面板未打开\n请在电脑上检查\n左 Control 键快捷设置',
            }
            self.change(4, messages.get(reason, '语音输入暂不可用\n请在电脑上检查 Codex\n并查看连接程序日志'))
            return False
        self.dictation_thread, self.dictation_review = target, prior
        return True

    def finish_dictation(self, cancel=False):
        target, self.dictation_thread = self.dictation_thread, None
        if target is None:
            return
        try:
            self.desktop.composer_action(target, 'dictate-cancel' if cancel else 'dictate-stop')
        except (OSError, RuntimeError, ValueError, subprocess.SubprocessError):
            self.change(4, '请检查电脑端语音输入\n并在电脑上停止录音\n内容未自动发送')
            return
        if cancel:
            self.dictation_review = None
            self.change(4, '语音输入已中断\n请检查电脑端输入框\n内容未自动发送')
        elif self.dictation_review is not None:
            self.restore_approval()
        else:
            self.change(1)

    def restore_approval(self):
        text, pending, page, seen, expires = self.dictation_review
        self.dictation_review = None
        self.change(3, text, pending)
        self.page, self.seen, self.expires = page, seen, expires

    def screen(self):
        self.sync()
        selection = None
        fixed_rows = None
        if self.mode == 7:
            if self.projects:
                lines, selection = self.project_rows()
                content = '\n'.join(lines)
                fixed_rows = LIST_ENTRIES
            else:
                content = self.error or '暂无项目\n请在电脑上打开 Codex'
        elif self.mode == 1:
            if self.draft and self.target == self.draft['id']:
                content = ('正在同步新会话\n请稍候' if self.draft['submitted'] else
                           '新会话\n长按确认键语音输入\n松开结束\n短按确认键发送')
            elif self.target:
                lines, selection = self.session_rows()
                content = '\n'.join(lines)
                fixed_rows = LIST_ENTRIES
            else:
                project = next((p['name'] for p in self.projects if p['id'] == self.project), '项目')
                try:
                    heading = '\n'.join(self.renderer.summary(project, 2))
                except UnsupportedText:
                    heading = '请在电脑上查看项目'
                content = heading + '\n暂无会话\n请在电脑上新建会话\n长按上键：查看项目'
        else:
            content = self.pages[self.page] + f'\n[{self.page+1}/{len(self.pages)}]'
        return bytes([self.mode]) + bytes.fromhex(self.token) + self.renderer.bitmap(
            content, selection=selection, fixed_rows=fixed_rows)

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
            try:
                row = self.renderer.summary(session['title'], 1)
            except UnsupportedText:
                row = ['请在电脑上查看会话标题']
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
            try:
                row = self.renderer.summary(project['name'], 1)
            except UnsupportedText:
                row = ['请在电脑上查看项目']
            if selected:
                selection = (len(lines), len(lines) + len(row))
            lines.extend(row)
        return lines, selection



class InteractionServer:
    def __init__(self, key, bind, font=None, desktop=None, dictation_backend='codex'):
        self.key, self.bind = key, bind
        self.desktop = desktop or Desktop(dictation_backend=dictation_backend)
        self.broker = Broker()
        self.renderer = Renderer(font)
        from dashboard import DashboardRenderer
        self.dashboard = DashboardRenderer(self.renderer)
        self.tracker = None
        self.active = threading.Lock()
        self.target = None
        self.review = None
        self.selection = SelectionMemory(self.desktop.root / 'codex-pet-selection.json'
                                         if hasattr(self.desktop, 'root') else None)

    def start(self):
        self.desktop.prepare_composer()
        print('语音输入方式：', '豆包' if getattr(self.desktop, 'dictation_backend', 'codex') == 'doubao' else 'Codex', '（使用电脑麦克风）', flush=True)
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
        review = None
        try:
            sock.settimeout(4)
            wire = SecureChannel(sock, self.key, server=True)
            sock.settimeout(8)
            review = getattr(self, 'review', None)
            if review is None:
                self.review = review = Review(self.desktop, self.broker, self.renderer, self.selection)
            # Reconnection preserves selection/review but invalidates every
            # action token from the previous authenticated connection.
            review.token = uuid.uuid4().hex
            review.pc_dictation_capable = False
            while True:
                data = wire.receive()
                if data[0] != 1:
                    raise ValueError('操作无效')
                value = json.loads(data[1:])
                review.pc_dictation_capable = value.get('pc_dictation') is True
                command = value.get('cmd')
                if command == 'stop' and review.mode == 10 and value.get('token') == review.token:
                    review.finish_dictation()
                elif command != 'sync':
                    review.action(command, value.get('token'))
                screen = review.screen()
                self.target = review.target
                wire.send(screen)
                sock.settimeout(35 if review.mode == 10 else 8)
                # Opt-in keeps older clients' single-response framing intact.
                # The home view is read-only and never selects an action target.
                if value.get('home') is True:
                    from dashboard import overview
                    with self.broker.lock:
                        pending = [p['thread'] for p in self.broker.pending.values()
                                   if not p['answer'] and p['expires'] > time.monotonic()]
                    activity = self.tracker.activity(time.monotonic(), pending) if self.tracker else {'@sync': {'status': 'syncing'}}
                    model = overview(activity, self.desktop.sessions(required=activity))
                    wire.send(self.dashboard.frame(model))
        except (OSError, EOFError, ValueError, KeyError) as error:
            print('设备控制连接已断开：', type(error).__name__,
                  '错误编号：', getattr(error, 'errno', None),
                  '界面模式：', review.mode if review else None, flush=True)
        finally:
            if review is not None and review.mode == 10:
                review.finish_dictation(cancel=True)
            sock.close()
            self.target = None
            self.active.release()

    def close(self):
        if getattr(self, 'review', None) is not None and self.review.dictation_thread is not None:
            self.review.finish_dictation(cancel=True)
        if getattr(self.desktop, '_doubao', None) is not None:
            self.desktop._doubao.close()
        for server in (getattr(self, 'server', None), getattr(self.broker, 'server', None)):
            if server:
                server.close()
