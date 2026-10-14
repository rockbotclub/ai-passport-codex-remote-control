#!/usr/bin/env python3
"""Privacy-minimal Codex lifecycle hooks -> loopback UDP -> authenticated Wi-Fi/USB pet snapshots."""
import argparse
import hashlib
import hmac
import getpass
import json
import os
from pathlib import Path
import shlex
import socket
import sys
import time
import threading

HOST, PORT = '127.0.0.1', 19283
DEVICE_PORT = 19284
PAIRING_PATH = Path.home() / '.config/ai-passport/codex-pet.json'
EVENTS = ('SessionStart', 'UserPromptSubmit', 'PreToolUse', 'PermissionRequest', 'PostToolUse', 'Stop', 'Interrupt', 'SessionEnd')
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
    def __init__(self):
        self.sessions = {}
        self.lock = threading.RLock()

    def accept(self, message, now):
        with self.lock:
            self._accept(message, now)

    def _accept(self, message, now):
        if not isinstance(message, dict) or message.get('event') not in EVENTS:
            return
        session = message.get('session')
        if not isinstance(session, str) or len(session) != 32:
            return
        event = message['event']
        previous = self.sessions.get(session)
        if event == 'SessionEnd':
            self.sessions.pop(session, None)
            return
        # A late SessionStart on resume must not erase an active turn.
        if event == 'SessionStart' and previous:
            return
        if previous and event not in ('SessionStart', 'UserPromptSubmit') and message.get('turn') != previous['turn']:
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

    def activity(self, now):
        with self.lock:
            return {identity: {**value, 'status': 'error' if value['status'] in ('working', 'waiting') and now - value['seen'] >= 1800 else
                              'done' if value['event'] == 'Stop' and now - value['seen'] < 8 else value['status']}
                    for identity, value in self.sessions.items()}

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
    print(f'Added companion hooks to {path}. Review/trust them in Codex before use; existing hooks are preserved.')


def wireless_packet(frame, key, sequence):
    payload = str(sequence).encode('ascii') + b' ' + frame
    digest = hmac.new(key.encode('ascii'), payload, hashlib.sha256).hexdigest().encode('ascii')
    return b'CPW1 ' + digest + b' ' + payload


def pair_device(host, path=PAIRING_PATH):
    key = getpass.getpass('Pairing key from the device setup page: ').strip()
    if len(key) != 32 or any(c not in '0123456789abcdef' for c in key):
        raise ValueError('The pairing key must contain 32 lowercase hex characters.')
    socket.getaddrinfo(host, DEVICE_PORT, socket.AF_INET, socket.SOCK_DGRAM)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as file:
        json.dump({'host': host, 'key': key}, file)
        file.write('\n')
    temporary.replace(path)
    print(f'Paired with {host}. Run the bridge with: python3 tools/codex_pet/bridge.py run')


def run_bridge(port, dry_run, pairing, interaction=None, diagnostics=False):
    tracker = Tracker()
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
        print('Listening on loopback. Waiting for a Codex lifecycle event.', flush=True)
        try:
            while True:
                now = time.monotonic()
                try:
                    data, _ = sock.recvfrom(2048)
                    message = json.loads(data)
                    if not isinstance(message, dict):
                        continue
                    tracker.accept(message, now)
                    if diagnostics and message.get('event') in EVENTS:
                        selected = interaction.target if interaction else None
                        matches = message.get('session') == hashlib.sha256(selected.encode()).hexdigest()[:32] if selected else False
                        print(f"Lifecycle: {message['event']}; selected={matches}; tracked={len(tracker.sessions)}", flush=True)
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
                    print(f'Selected chat: observed={known}; tracked={len(tracker.sessions)}', flush=True)
                    previous_selection = selected
                frame = tracker.snapshot(now)
                if frame != previous:
                    print(frame.decode().strip(), flush=True)
                    previous = frame
                if dry_run:
                    continue
                if wireless:
                    sequence = max(sequence + 1, time.time_ns())
                    try:
                        wireless.sendto(wireless_packet(frame, pairing['key'], sequence), destination)
                    except OSError as error:
                        print(f'Wi-Fi send failed: {error}; retrying', file=sys.stderr)
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
                    print(f'USB unavailable: {error}; retrying', file=sys.stderr)
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
            if interaction:
                interaction.close()
            if wireless:
                wireless.close()
            if connection:
                connection.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('hook')
    install = sub.add_parser('install-hooks')
    install.add_argument('--path', type=Path, default=Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex'))) / 'hooks.json')
    pair = sub.add_parser('pair')
    pair.add_argument('--host', required=True, help='IPv4 address shown on the pet')
    pair.add_argument('--config', type=Path, default=PAIRING_PATH)
    run = sub.add_parser('run')
    run.add_argument('--config', type=Path, default=PAIRING_PATH)
    run.add_argument('--port', help='Explicit AI-Passport serial port; never autodetect/open arbitrary devices')
    run.add_argument('--dry-run', action='store_true')
    run.add_argument('--interactive', action='store_true')
    run.add_argument('--diagnostics', action='store_true', help='Log event kinds and selection matches; never prompts or session IDs')
    run.add_argument('--model', type=Path, default=Path.home() / '.cache/ai-passport/ggml-base.bin')
    run.add_argument('--bind', default='0.0.0.0', help='LAN interface for encrypted control/audio')
    run.add_argument('--font', type=Path, help='Locally installed CJK font')
    run.add_argument('--chinese-script', choices=('simplified', 'traditional', 'keep'), default='simplified',
                     help='Normalize Chinese speech transcripts before display and input filling')
    run.add_argument('--asr-backend', choices=('auto', 'server', 'cli'), default='auto',
                     help='Keep Whisper loaded locally when whisper-server is installed; cli reloads per recording')
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
                parser.error('Pair the Wi-Fi device first: pair --host <device-IP>')
            pairing = json.loads(args.config.read_text())
            key = pairing.get('key', '')
            if len(key) != 32 or any(c not in '0123456789abcdef' for c in key):
                parser.error('Invalid pairing key; pair again')
        if not args.dry_run and args.port:
            try:
                import serial
            except ImportError:
                parser.error('pyserial is required; activate ESP-IDF or install requirements.txt in a venv')
        interaction = None
        if args.interactive:
            if not pairing:
                parser.error('Interactive mode requires a paired Wi-Fi device')
            from interaction import InteractionServer
            interaction = InteractionServer(pairing['key'], args.model, args.bind, args.font,
                                            chinese_script=args.chinese_script, asr_backend=args.asr_backend)
            try:
                interaction.start()
            except BaseException:
                interaction.close()
                raise
        run_bridge(args.port, args.dry_run, pairing, interaction, args.diagnostics)

if __name__ == '__main__':
    main()
