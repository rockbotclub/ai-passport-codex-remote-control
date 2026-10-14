"""Exercise hook boundaries, concurrent sessions, snapshots, and packet auth."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import hmac
import hashlib

spec = importlib.util.spec_from_file_location('bridge', Path(__file__).resolve().parents[1] / 'tools/codex_pet/bridge.py')
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)

class BridgeTests(unittest.TestCase):
    def event(self, name, session='a', turn='1', tool='Bash'):
        return bridge.compact_event({'hook_event_name': name, 'session_id': session, 'turn_id': turn, 'tool_name': tool})

    def test_no_private_text(self):
        event = bridge.compact_event({'hook_event_name': 'UserPromptSubmit', 'session_id': 'private-session', 'prompt': 'private prompt', 'cwd': 'private path', 'tool_input': {'password': 'private password'}})
        serialized = json.dumps(event)
        self.assertNotIn('private', serialized)
        self.assertIsNone(bridge.compact_event({'hook_event_name': 'unknown', 'session_id': 'a'}))

    def test_multi_session_wait_has_priority(self):
        state = bridge.Tracker()
        state.accept(self.event('UserPromptSubmit'), 1)
        state.accept(self.event('UserPromptSubmit', session='b'), 2)
        state.accept(self.event('PermissionRequest'), 3)
        self.assertEqual(state.snapshot(4), b'CP1 waiting 2 1\n')
        state.accept(self.event('PostToolUse', tool='different'), 5)
        self.assertEqual(state.snapshot(6), b'CP1 waiting 2 1\n')
        state.accept(self.event('PostToolUse'), 7)
        self.assertEqual(state.snapshot(8), b'CP1 working 2 0\n')
        state.accept(self.event('Stop'), 9)
        self.assertEqual(state.snapshot(10), b'CP1 working 1 0\n')
        state.accept(self.event('Stop', session='b'), 11)
        self.assertEqual(state.snapshot(12), b'CP1 done 0 0\n')
        self.assertEqual(state.snapshot(20), b'CP1 idle 0 0\n')

    def test_late_old_turn_cannot_complete_new_turn(self):
        state = bridge.Tracker()
        state.accept(self.event('UserPromptSubmit'), 1)
        state.accept(self.event('UserPromptSubmit', turn='2'), 2)
        state.accept(self.event('Stop'), 3)
        self.assertEqual(state.snapshot(4), b'CP1 working 1 0\n')

    def test_waiting_input_and_interrupt(self):
        state = bridge.Tracker()
        state.accept(self.event('PreToolUse', tool='mcp__request_user_input'), 1)
        self.assertEqual(state.snapshot(2), b'CP1 waiting 1 1\n')
        state.accept(self.event('Interrupt'), 3)
        self.assertEqual(state.snapshot(4), b'CP1 idle 0 0\n')
        state.accept(self.event('SessionEnd'), 5)
        self.assertEqual(state.snapshot(6), b'CP1 idle 0 0\n')

    def test_no_sessions_and_long_idle_stay_ready(self):
        state = bridge.Tracker()
        self.assertEqual(state.snapshot(0), b'CP1 idle 0 0\n')
        state.accept(self.event('SessionStart'), 1)
        self.assertEqual(state.snapshot(1801), b'CP1 idle 0 0\n')
        state.accept(self.event('Stop'), 1802)
        self.assertEqual(state.snapshot(3602), b'CP1 idle 0 0\n')

    def test_stale_waiting_is_unknown_and_other_active_chat_takes_priority(self):
        state = bridge.Tracker()
        state.accept(self.event('PermissionRequest'), 1)
        self.assertEqual(state.snapshot(1800), b'CP1 waiting 1 1\n')
        self.assertEqual(state.snapshot(1801), b'CP1 error 0 0\n')
        state.accept(self.event('UserPromptSubmit', session='b'), 1802)
        self.assertEqual(state.snapshot(1803), b'CP1 working 1 0\n')
        self.assertEqual(state.snapshot(1803, session=self.event('PermissionRequest')['session']), b'CP1 error 0 0\n')

    def test_finished_animation_belongs_to_its_session(self):
        state = bridge.Tracker()
        state.accept(self.event('SessionStart', session='b'), 1)
        state.accept(self.event('Stop'), 2)
        self.assertEqual(state.snapshot(3, session=self.event('SessionStart', session='b')['session']), b'CP1 idle 0 0\n')

    def test_inactivity_is_unknown_not_success(self):
        state = bridge.Tracker()
        state.accept(self.event('UserPromptSubmit'), 1)
        self.assertEqual(state.snapshot(1801), b'CP1 error 0 0\n')
        state.accept(self.event('PostToolUse'), 1802)
        self.assertEqual(state.snapshot(1803), b'CP1 working 1 0\n')

    def test_signed_packet(self):
        key = 'a'*32
        packet = bridge.wireless_packet(b'CP1 working 2 0\n', key, 123)
        magic, signature, payload = packet.split(b' ', 2)
        self.assertEqual(magic, b'CPW1')
        self.assertEqual(payload, b'123 CP1 working 2 0\n')
        self.assertEqual(signature, hmac.new(key.encode(), payload, hashlib.sha256).hexdigest().encode())
        self.assertNotIn(key.encode(), packet)

    def test_install_preserves_unrelated_hook_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'hooks.json'
            original = {'hooks': {'Stop': [{'hooks': [{'type': 'command', 'command': 'echo unrelated'}]}]}}
            path.write_text(json.dumps(original))
            mixed = {'hooks': [{'type': 'command', 'command': 'echo retained'}, {'type': 'command', 'command': f'python3 {Path(bridge.__file__).resolve()} hook'}]}
            original['hooks']['PreToolUse'] = [mixed]
            path.write_text(json.dumps(original))
            bridge.install_hooks(path)
            bridge.install_hooks(path)
            value = json.loads(path.read_text())
            self.assertEqual(len(value['hooks']['Stop']), 2)
            self.assertEqual(value['hooks']['Stop'][0], original['hooks']['Stop'][0])
            self.assertEqual(value['hooks']['PreToolUse'][0]['hooks'], [{'type': 'command', 'command': 'echo retained'}])
            for name in bridge.EVENTS:
                self.assertEqual(sum('codex_pet/bridge.py' in h['command'] for e in value['hooks'][name] for h in e['hooks']), 1)

if __name__ == '__main__':
    unittest.main()
