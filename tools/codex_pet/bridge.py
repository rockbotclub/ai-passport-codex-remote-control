#!/usr/bin/env python3
"""Privacy-minimal Codex lifecycle hooks -> loopback UDP -> authenticated Wi-Fi/USB pet snapshots."""
from messages import ChineseArgumentParser, system_error
import hashlib
import hmac
import getpass
import json
import os
from pathlib import Path
import shlex
import socket
import sys
import subprocess
import time
import threading

HOST, PORT = '127.0.0.1', 19283
DEVICE_PORT = 19284
PAIRING_PATH = Path.home() / '.config/ai-passport/codex-pet.json'
EVENTS = ('SessionStart', 'UserPromptSubmit', 'PreToolUse', 'PermissionRequest', 'PostToolUse', 'Stop', 'Interrupt', 'SessionEnd')
EVENT_LABELS = dict(zip(EVENTS, ('会话开始', '提交输入', '工具调用开始', '请求授权', '工具调用结束', '本轮结束', '中断', '会话结束')))
STATUS_LABELS = {'offline': '电脑已断开', 'idle': '暂无任务', 'working': '正在工作', 'waiting': '需要你处理', 'done': '本轮已结束', 'error': '状态暂不确定', 'syncing': '正在同步任务'}
WORKING = ('UserPromptSubmit', 'PreToolUse', 'PostToolUse')


def compact_event(value):
    """Never forward prompts, tool inputs/results, paths, or assistant messages."""
    event = value.get('hook_event_name')
    session = value.get('session_id')
    if event not in EVENTS or not isinstance(session, str) or not session:
        return None
    tool = value.get('tool_name', '')
    waiting_input = event == 'PreToolUse' and isinstance(tool, str) and tool.endswith('request_user_input')
    return {'event': event, 'session': hashlib.sha256(session.encode()).hexdigest()[:32],
            'turn': hashlib.sha256(str(value.get('turn_id', '')).encode()).hexdigest()[:32],
            'tool': hashlib.sha256(str(tool).encode()).hexdigest()[:16], 'input': waiting_input}


class Tracker:
    def __init__(self, sync=False):
        self.sync_enabled = sync
        self.sync_ready = not sync
        self.sync_started = time.monotonic()
        self.sync_failed = False
        self.generation = 0
        self.changed = {}
        self.sessions = {}
        self.catalog = None
        self.desktop_seen = set()
        self.lock = threading.RLock()

    def set_catalog(self, catalog):
        with self.lock:
            self.catalog = {hashlib.sha256(identity.encode()).hexdigest()[:32]:
                            hashlib.sha256(root.encode()).hexdigest()[:32] if root else None
                            for identity, root in catalog.items()}

    def needs_catalog(self, identity):
        with self.lock:
            return self.catalog is None or identity not in self.catalog

    def revision(self):
        with self.lock:
            return self.generation

    def reconcile(self, states, revision, now, complete, absent=()):
        with self.lock:
            for identity in absent:
                if identity in self.desktop_seen and self.changed.get(identity, 0) <= revision:
                    self.sessions.pop(identity, None)
                    self.desktop_seen.discard(identity)
            for identity, value in states.items():
                if self.changed.get(identity, 0) > revision:
                    continue  # A hook received during the read wins, including SessionEnd.
                self.desktop_seen.add(identity)
                previous = self.sessions.get(identity)
                if previous and previous['status'] == value['status']:
                    self.sessions[identity] = {**previous, 'seen': now if value['status'] in ('working', 'waiting') else previous['seen']}
                else:
                    self.sessions[identity] = {**value, 'seen': now}
            if complete:
                for identity, value in list(self.sessions.items()):
                    if (value['event'] == 'Snapshot' and identity not in states
                            and self.changed.get(identity, 0) <= revision):
                        self.sessions.pop(identity)
                        self.desktop_seen.discard(identity)
                self.changed = {identity: generation for identity, generation in self.changed.items()
                                if identity in self.sessions or generation > revision}
                self.sync_ready = True
            if complete is not None:
                self.sync_failed = not complete

    def accept(self, message, now):
        with self.lock:
            self._accept(message, now)

    def _accept(self, message, now):
        if not isinstance(message, dict) or message.get('event') not in EVENTS:
            return
        session = message.get('session')
        if not isinstance(session, str) or len(session) != 32:
            return
        self.generation += 1
        self.changed[session] = self.generation
        event = message['event']
        previous = self.sessions.get(session)
        if event == 'SessionEnd':
            self.sessions.pop(session, None)
            return
        # A late SessionStart on resume must not erase an active turn.
        if event == 'SessionStart' and previous:
            return
        if previous and previous['turn'] is not None and event not in ('SessionStart', 'UserPromptSubmit') and message.get('turn') != previous['turn']:
            return
        if event == 'PermissionRequest' or message.get('input'):
            status = 'waiting'
        elif event in WORKING:
            status = 'working'
            # A parallel tool's event is not evidence that approval was answered.
            if previous and previous['status'] == 'waiting' and event != 'UserPromptSubmit':
                if event != 'PostToolUse' or message.get('tool') != previous['tool']:
                    return
        elif event == 'Stop':
            status = 'idle'
        else:
            status = 'idle'
        self.sessions[session] = {'status': status, 'turn': message.get('turn'),
                                  'tool': message.get('tool'), 'seen': now, 'event': event}

    def snapshot(self, now, session=None):
        with self.lock:
            return self._snapshot(now, session)

    def activity(self, now, pending_threads=()):
        with self.lock:
            result = {identity: {**value, 'status': 'error' if value['status'] in ('working', 'waiting') and now - value['seen'] >= 1800 else
                              'done' if value['event'] == 'Stop' and now - value['seen'] < 8 else value['status']}
                    for identity, value in self.sessions.items()}
            for thread in pending_threads:
                result[hashlib.sha256(thread.encode()).hexdigest()[:32]] = {'status': 'waiting'}
            if self.catalog is not None or self.sync_enabled:
                visible = {}
                for identity, value in result.items():
                    if self.catalog is None or identity not in self.catalog:
                        if value['status'] in ('working', 'waiting'):
                            status = 'error' if now - value.get('seen', now) >= 15 else 'syncing'
                            if visible.get('@metadata', {}).get('status') != 'error':
                                visible['@metadata'] = {'status': status}
                        continue
                    if self.catalog[identity] is not None:
                        visible[identity] = {**value, 'confirmed': True}
                result = visible
            if self.sync_enabled and (not self.sync_ready or self.sync_failed):
                result['@sync'] = {'status': 'error' if self.sync_ready or now - self.sync_started >= 15 else 'syncing'}
            return result

    def _snapshot(self, now, session=None):
        # Missing lifecycle events cannot prove a disconnected bridge. Only
        # stale active turns become unknown; idle chats do not expire.
        states = [v['status'] for identity, v in self.activity(now).items()
                  if session is None or identity == session]
        active = sum(x in ('working', 'waiting') for x in states)
        waiting = states.count('waiting')
        if waiting:
            status = 'waiting'
        elif active:
            status = 'working'
        elif 'error' in states:
            status = 'error'
        elif 'syncing' in states:
            status = 'syncing'
        elif 'done' in states:
            status = 'done'
        else:
            status = 'idle'
        return f'CP1 {status} {min(active, 999)} {min(waiting, 999)}\n'.encode('ascii')


def emit_hook():
    result = {}
    try:
        value = json.loads(sys.stdin.buffer.read(1024 * 1024))
        message = compact_event(value) if isinstance(value, dict) else None
        if message:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.settimeout(0.1)
                sock.sendto(json.dumps(message).encode(), (HOST, PORT))
            if value.get('hook_event_name') == 'PermissionRequest':
                from interaction import permission_hook
                result = permission_hook(value)
    except (OSError, ValueError, TypeError):
        pass  # The companion never blocks or changes Codex's decisions.
    sys.stdout.write(json.dumps(result) + '\n')


def install_hooks(destination):
    path = destination.expanduser()
    value = json.loads(path.read_text()) if path.exists() else {}
    hooks = value.setdefault('hooks', {})
    command = f'{shlex.quote(sys.executable)} {shlex.quote(str(Path(__file__).resolve()))} hook'
    for event in EVENTS:
        entries = hooks.setdefault(event, [])
        # Idempotence and preservation of every unrelated handler.
        retained = []
        for entry in entries:
            existing = entry.get('hooks', [])
            remaining = [hook for hook in existing if str(Path(__file__).resolve()) not in str(hook.get('command', ''))]
            if remaining:
                retained.append({**entry, 'hooks': remaining})
        entries[:] = retained
        entries.append({'hooks': [{'type': 'command', 'command': command, 'timeout': 120 if event == 'PermissionRequest' else 1}]})
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup = path.with_name(path.name + f'.passport-backup-{time.time_ns()}')
        backup.write_bytes(path.read_bytes())
    temporary = path.with_name(path.name + '.passport-tmp')
    with temporary.open('x') as f:
        json.dump(value, f, indent=2)
        f.write('\n')
    temporary.replace(path)
    print(f'已将宠物事件钩子添加到 {path}。使用前请在 Codex 中审阅并信任这些钩子；已有钩子已保留。')


def wireless_packet(frame, key, sequence):
    payload = str(sequence).encode('ascii') + b' ' + frame
    digest = hmac.new(key.encode('ascii'), payload, hashlib.sha256).hexdigest().encode('ascii')
    return b'CPW1 ' + digest + b' ' + payload


def pair_device(host, path=PAIRING_PATH):
    key = getpass.getpass('请输入设备配网页面上的配对密钥：').strip()
    if len(key) != 32 or any(c not in '0123456789abcdef' for c in key):
        raise ValueError('配对密钥必须是 32 位小写十六进制字符。')
    socket.getaddrinfo(host, DEVICE_PORT, socket.AF_INET, socket.SOCK_DGRAM)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as file:
        json.dump({'host': host, 'key': key}, file)
        file.write('\n')
    temporary.replace(path)
    print(f'已与 {host} 配对。请运行连接程序：python3 tools/codex_pet/bridge.py run')


def run_bridge(port, dry_run, pairing, interaction=None, diagnostics=False):
    tracker = Tracker(sync=True)
    from status_sync import StatusSync
    from interaction import Desktop
    sync = StatusSync(interaction.desktop if interaction else Desktop(), tracker, diagnostics)
    if interaction:
        interaction.tracker = tracker
    connection = None
    next_send = 0
    previous = None
    previous_selection = object()
    sequence = time.time_ns()
    wireless = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) if pairing else None
    destination = (pairing["host"], DEVICE_PORT) if pairing else None
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind((HOST, PORT))
        sock.settimeout(0.1)
        sync.start()
        print('正在监听本机事件，并同步电脑端任务状态。', flush=True)
        try:
            while True:
                now = time.monotonic()
                try:
                    data, _ = sock.recvfrom(2048)
                    message = json.loads(data)
                    if not isinstance(message, dict):
                        continue
                    tracker.accept(message, now)
                    sync.notify(message.get('session'))
                    if diagnostics and message.get('event') in EVENTS:
                        selected = interaction.target if interaction else None
                        matches = message.get('session') == hashlib.sha256(selected.encode()).hexdigest()[:32] if selected else False
                        print(f"生命周期事件：{EVENT_LABELS[message['event']] }；匹配所选会话：{'是' if matches else '否'}；已跟踪会话数：{len(tracker.sessions)}", flush=True)
                    if interaction and message.get('event') in ('Stop', 'Interrupt', 'SessionEnd', 'UserPromptSubmit'):
                        with interaction.broker.lock:
                            threads = [v['thread'] for v in interaction.broker.pending.values()
                                       if hashlib.sha256(v['thread'].encode()).hexdigest()[:32] == message.get('session')]
                        for thread in threads:
                            interaction.broker.invalidate(thread)
                except (socket.timeout, ValueError, UnicodeError):
                    pass
                if now < next_send:
                    continue
                next_send = now + 1
                selected = interaction.target if interaction else None
                if diagnostics and selected != previous_selection:
                    known = bool(selected and hashlib.sha256(selected.encode()).hexdigest()[:32] in tracker.sessions)
                    print(f'所选会话：{"已观察到" if known else "尚未观察到"}；已跟踪会话数：{len(tracker.sessions)}', flush=True)
                    previous_selection = selected
                frame = tracker.snapshot(now)
                if frame != previous:
                    state, active, waiting = frame.decode().split()[1:]
                    print(f'任务状态：{STATUS_LABELS[state]}；活跃：{active}；待处理：{waiting}', flush=True)
                    previous = frame
                if dry_run:
                    continue
                if wireless:
                    sequence = max(sequence + 1, time.time_ns())
                    try:
                        wireless.sendto(wireless_packet(frame, pairing['key'], sequence), destination)
                    except OSError as error:
                        print(f'Wi-Fi 发送失败：{system_error(error)}；正在重试', file=sys.stderr)
                    continue
                try:
                    import serial
                    if connection is None:
                        connection = serial.Serial(port=None, baudrate=115200, timeout=0, write_timeout=0.2)
                        connection.dtr = False
                        connection.rts = False
                        connection.port = port
                        connection.open()
                    connection.write(frame)
                    # Drain firmware logs without printing or storing private data.
                    connection.read(min(connection.in_waiting, 4096))
                except (OSError, serial.SerialException) as error:
                    if connection:
                        connection.close()
                        connection = None
                    print(f'USB 不可用：{system_error(error)}；正在重试', file=sys.stderr)
        except KeyboardInterrupt:
            if wireless:
                sequence = max(sequence + 1, time.time_ns())
                wireless.sendto(wireless_packet(b'CP1 offline 0 0\n', pairing['key'], sequence), destination)
            if connection:
                try:
                    connection.write(b'CP1 offline 0 0\n')
                except OSError:
                    pass
        finally:
            sync.close()
            if interaction:
                interaction.close()
            if wireless:
                wireless.close()
            if connection:
                connection.close()


def main():
    parser = ChineseArgumentParser(description='将 Codex 任务状态同步至 AI-Passport 宠物设备。')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('hook', help='转发 Codex 生命周期事件')
    install = sub.add_parser('install-hooks', help='安装宠物事件钩子')
    install.add_argument('--path', type=Path, default=Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex'))) / 'hooks.json')
    pair = sub.add_parser('pair', help='配对 Wi-Fi 设备')
    pair.add_argument('--host', required=True, help='设备上显示的 IPv4 地址')
    pair.add_argument('--config', type=Path, default=PAIRING_PATH)
    run = sub.add_parser('run', help='运行设备连接程序')
    run.add_argument('--config', type=Path, default=PAIRING_PATH)
    run.add_argument('--port', help='指定 AI-Passport 串口；不会自动打开其他设备')
    run.add_argument('--dry-run', action='store_true')
    run.add_argument('--interactive', action='store_true')
    run.add_argument('--dictation-backend', choices=('codex', 'doubao'), default='codex',
                     help='电脑端语音输入方式；豆包的长按快捷键需设为左 Control 键')
    run.add_argument('--diagnostics', action='store_true',
                     help='记录事件类型、会话匹配结果和控制诊断；不记录语音文字或会话标识')
    run.add_argument('--bind', default='0.0.0.0', help='加密控制使用的局域网监听地址')
    run.add_argument('--font', type=Path, help='本地安装的中文字体')
    args = parser.parse_args()
    if args.command == 'hook':
        emit_hook()
    elif args.command == 'install-hooks':
        install_hooks(args.path)
    elif args.command == 'pair':
        pair_device(args.host, args.config)
    else:
        pairing = None
        if not args.dry_run and not args.port:
            if not args.config.exists():
                parser.error('请先配对 Wi-Fi 设备：pair --host <设备 IP>')
            pairing = json.loads(args.config.read_text())
            if not isinstance(pairing, dict) or not isinstance(pairing.get('host'), str) or not pairing['host']:
                parser.error('配对配置格式无效，请重新配对')
            key = pairing.get('key', '')
            if not isinstance(key, str) or len(key) != 32 or any(c not in '0123456789abcdef' for c in key):
                parser.error('配对密钥无效，请重新配对')
        if not args.dry_run and args.port:
            try:
                import serial
            except ImportError:
                parser.error('需要 pyserial；请激活 ESP-IDF 环境，或在虚拟环境中安装 requirements.txt 中的依赖')
        interaction = None
        if args.interactive:
            if not pairing:
                parser.error('交互模式需要已配对的 Wi-Fi 设备')
            from interaction import InteractionServer
            interaction = InteractionServer(pairing['key'], args.bind, args.font,
                                            dictation_backend=args.dictation_backend)
            try:
                interaction.start()
            except BaseException:
                interaction.close()
                raise
        run_bridge(args.port, args.dry_run, pairing, interaction, args.diagnostics)

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('操作已取消。', file=sys.stderr)
        sys.exit(130)
    except (OSError, ValueError, RuntimeError, ImportError, subprocess.SubprocessError) as error:
        print(f'连接程序运行失败：{system_error(error)}。', file=sys.stderr)
        sys.exit(1)
