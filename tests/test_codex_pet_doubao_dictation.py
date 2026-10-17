"""Doubao hold ownership and release; all subprocesses and key events are fake."""
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools/codex_pet'))
from doubao_dictation import DoubaoDictation, DoubaoError
from interaction import Desktop, ComposerActionError, COMPOSER_DRAFT_FIELDS


class FakeProcess:
    def __init__(self, output=b'held\n', code=0):
        self.stdin = io.BytesIO()
        self.stdout = io.BytesIO(output)
        self.stderr = io.BytesIO()
        self.code = code
        self.running = True
        self.terminations = 0
    def poll(self): return None if self.running else self.code
    def wait(self, timeout):
        self.running = False
        return self.code
    def terminate(self):
        self.terminations += 1
        self.running = False


class DoubaoTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.backend = DoubaoDictation(self.temporary.name)
        self.process = FakeProcess()
        self.addCleanup(self.backend.close)

    def start(self):
        with patch.object(self.backend, 'prepare'), \
                patch('doubao_dictation.subprocess.Popen', return_value=self.process), \
                patch('doubao_dictation.select.select', return_value=([self.process.stdout], [], [])):
            self.backend.start('selected', 'Unique title')

    def test_start_owns_one_hold_and_sends_only_target_metadata(self):
        self.start()
        request = json.loads(self.process.stdin.getvalue())
        self.assertEqual(request, {'thread': 'selected', 'title': 'Unique title'})
        with self.assertRaises(DoubaoError): self.backend.start('other')
        self.assertEqual(self.backend.thread, 'selected')

    def test_release_writes_only_stop_once_and_never_a_send_key(self):
        self.start()
        stream = self.process.stdin
        with patch.object(stream, 'close'):
            self.backend.finish('selected')
            self.assertTrue(stream.getvalue().endswith(b'\nstop\n'))
            value = stream.getvalue()
            self.backend.finish('selected')
            self.assertEqual(stream.getvalue(), value)
        self.assertIsNone(self.backend.process)

    def test_new_composer_passes_project_binding_without_a_saved_chat_title(self):
        with patch.object(self.backend, 'prepare'), \
                patch('doubao_dictation.subprocess.Popen', return_value=self.process), \
                patch('doubao_dictation.select.select', return_value=([self.process.stdout], [], [])):
            self.backend.start('@new:first', draft_project='Alpha')
        self.assertEqual(json.loads(self.process.stdin.getvalue()),
                         {'thread': '@new:first', 'draftProject': 'Alpha'})

    def test_desktop_routes_first_message_dictation_to_same_doubao_backend(self):
        desktop = Desktop(self.temporary.name, dictation_backend='doubao')
        desktop._new_composer = {'id': '@new:first', 'project': 'Alpha'}
        desktop._composer_helper_dir = type('Helper', (), {'name': self.temporary.name})()
        desktop._doubao = Mock()
        with patch('interaction.sys.platform', 'darwin'), patch.object(desktop, 'open_chat') as navigate:
            desktop.composer_action('@new:first', 'dictate-start')
            desktop.composer_action('@new:first', 'dictate-stop')
        desktop._doubao.start.assert_called_once_with('@new:first', draft_project='Alpha')
        desktop._doubao.finish.assert_called_once_with('@new:first', cancel=False)
        navigate.assert_not_called()

    def test_wrong_chat_cannot_release_or_replace_owned_hold(self):
        self.start()
        with self.assertRaises(DoubaoError): self.backend.finish('other')
        self.assertIs(self.backend.process, self.process)

    def test_disconnect_uses_eof_without_escape_return_or_send(self):
        self.start()
        before = self.process.stdin.getvalue()
        with patch.object(self.process.stdin, 'close'):
            self.backend.close()
            self.assertEqual(self.process.stdin.getvalue(), before)
        self.assertIsNone(self.backend.process)

    def test_start_timeout_closes_input_and_cleans_up(self):
        with patch.object(self.backend, 'prepare'), \
                patch('doubao_dictation.subprocess.Popen', return_value=self.process), \
                patch('doubao_dictation.select.select', return_value=([], [], [])):
            with self.assertRaises(DoubaoError) as error: self.backend.start('selected')
        self.assertEqual(error.exception.reason, 'dictation-start-not-ready')
        self.assertTrue(self.process.stdin.closed)
        self.assertIsNone(self.backend.process)

    def test_focus_change_or_watchdog_failure_is_not_reported_as_success(self):
        for code, reason in ((46, 'dictation-timeout'), (47, 'dictation-target-changed')):
            self.process = FakeProcess(code=code)
            self.start()
            with self.assertRaises(DoubaoError) as error: self.backend.finish('selected')
            self.assertEqual(error.exception.reason, reason)
            self.assertIsNone(self.backend.process)

    def test_start_failure_preserves_specific_reason_without_logging_text(self):
        self.process = FakeProcess(output=b'', code=41)
        with patch.object(self.backend, 'prepare'), \
                patch('doubao_dictation.subprocess.Popen', return_value=self.process), \
                patch('doubao_dictation.select.select', return_value=([self.process.stdout], [], [])):
            with self.assertRaises(DoubaoError) as error: self.backend.start('selected')
        self.assertEqual(error.exception.reason, 'doubao-input-required')
        self.assertIsNone(self.backend.process)

    def test_failed_discovery_carries_diagnostics_and_closes_stderr(self):
        self.process = FakeProcess(output=b'', code=13)
        counts = json.dumps(dict.fromkeys(COMPOSER_DRAFT_FIELDS, 0)).encode()
        self.process.stderr.write(counts); self.process.stderr.seek(0)
        with patch.object(self.backend, 'prepare'), \
                patch('doubao_dictation.subprocess.Popen', return_value=self.process), \
                patch('doubao_dictation.select.select', return_value=([self.process.stdout], [], [])):
            with self.assertRaises(DoubaoError) as error: self.backend.start('@new:first', draft_project='Alpha')
        self.assertEqual(error.exception.reason, 'chat-not-found')
        self.assertEqual(error.exception.diagnostics, counts)
        self.assertTrue(self.process.stderr.closed)

    def test_desktop_logs_only_fixed_numeric_draft_diagnostics_on_failure(self):
        desktop = Desktop(self.temporary.name, dictation_backend='doubao')
        desktop._new_composer = {'id': '@new:first', 'project': 'Alpha'}
        desktop._doubao = Mock()
        counts = dict.fromkeys(COMPOSER_DRAFT_FIELDS, 1)
        diagnostic = json.dumps(counts).encode() + b'\nprivate input\n' + json.dumps({**counts, 'name':'private'}).encode()
        desktop._doubao.start.side_effect = DoubaoError('chat-not-found', diagnostic)
        with patch.object(desktop, 'prepare_composer'), patch('builtins.print') as report:
            with self.assertRaises(ComposerActionError): desktop.composer_action('@new:first', 'dictate-start')
        logged = str(report.call_args_list)
        self.assertIn('电脑端新会话定位统计：', logged)
        self.assertNotIn('private', logged)

    def test_successful_finish_returns_numeric_startup_diagnostics_without_reading_live_pipe(self):
        counts = json.dumps(dict.fromkeys(COMPOSER_DRAFT_FIELDS, 1)).encode()
        self.process.stderr.write(counts); self.process.stderr.seek(0)
        self.start()
        self.assertEqual(self.process.stderr.tell(), 0)
        self.assertEqual(self.backend.finish('selected'), counts)
        self.assertTrue(self.process.stderr.closed)

    def test_desktop_routes_only_voice_to_doubao_and_keeps_native_send(self):
        desktop = Desktop(self.temporary.name, dictation_backend='doubao')
        desktop._composer_helper_dir = Mock(name=self.temporary.name)
        desktop._composer_helper_dir.name = self.temporary.name
        desktop._doubao = Mock()
        with patch.object(desktop, 'open_chat'), patch.object(desktop, '_composer_title', return_value='Title'), \
                patch('interaction.subprocess.run', return_value=subprocess.CompletedProcess([], 0, stderr=b'')) as native:
            desktop.composer_action('selected', 'dictate-start')
            desktop.composer_action('selected', 'dictate-stop')
            desktop.composer_action('selected', 'dictate-cancel')
            desktop.send('selected')
        desktop._doubao.start.assert_called_once_with('selected', 'Title')
        self.assertEqual(desktop._doubao.finish.call_count, 2)
        self.assertEqual(json.loads(native.call_args.kwargs['input'])['action'], 'send')
        self.assertEqual(native.call_count, 1)

    def test_doubao_errors_are_exposed_through_existing_state_machine(self):
        desktop = Desktop(self.temporary.name, dictation_backend='doubao')
        desktop._doubao = Mock()
        desktop._doubao.start.side_effect = DoubaoError('modifier-held')
        with patch.object(desktop, 'prepare_composer'), patch.object(desktop, 'open_chat'), \
                patch.object(desktop, '_composer_title', return_value=None):
            with self.assertRaises(ComposerActionError) as error:
                desktop.composer_action('selected', 'dictate-start')
        self.assertEqual(error.exception.reason, 'modifier-held')


if __name__ == '__main__': unittest.main()
