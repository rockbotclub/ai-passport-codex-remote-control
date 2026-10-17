"""PC dictation state, capability negotiation and non-sending release/cleanup."""
from pathlib import Path
from contextlib import closing
import json
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools/codex_pet'))
from interaction import (Broker, COMPOSER_CONTROL_FIELDS, COMPOSER_DIAGNOSTIC_FIELDS, COMPOSER_TIMING_FIELDS, ComposerActionError,
                         Desktop, InteractionServer, PIXELS, Review, SecureChannel, SelectionMemory,
                         report_composer_diagnostics)


class FakeDesktop:
    def __init__(self):
        self.calls, self.sent = [], []
    def sessions(self): return [{'id': 'one', 'title': 'One', 'project': '项目'}]
    def projects(self): return [{'id': '项目', 'name': '项目'}]
    def composer_action(self, thread, action): self.calls.append((thread, action))
    def invalidate_sessions(self): pass
    def open_new_chat(self, project):
        self.calls.append((project, 'new'))
        return {'id': '@new:test', 'title': '新会话', 'project_id': project, 'project': project}
    def send(self, thread): self.sent.append(thread); return True


class Renderer:
    def pages(self, text): return text.split('|')
    def summary(self, text, count=1): return [text]
    def bitmap(self, text, selection=None, fixed_rows=None): return bytes(PIXELS)


class NativeDictationTests(unittest.TestCase):
    def setUp(self):
        self.desktop, self.broker = FakeDesktop(), Broker()
        self.review = Review(self.desktop, self.broker, Renderer())
        self.review.pc_dictation_capable = True
        self.review.sync(); self.review.action('ok', self.review.token)

    def action(self, command): return self.review.action(command, self.review.token)

    def test_native_new_route_preserves_selected_id_and_forces_codex_mode(self):
        desktop = Desktop()
        projects = [{'id': 'a &/中文', 'name': 'Alpha'}, {'id': 'b', 'name': 'Beta'}]
        with patch('interaction.sys.platform', 'darwin'), patch.object(desktop, 'projects', return_value=projects), \
                patch('interaction.subprocess.run') as run, patch.object(desktop, '_ipc_socket') as ipc, \
                patch.object(desktop, '_scan_sessions', return_value=[{'id': 'already-saved'}]):
            draft = desktop.open_new_chat('a &/中文')
        self.assertEqual(run.call_args.args[0], ['open', '-b', 'com.openai.codex',
            'codex://new?mode=codex&projectId=a%20%26%2F%E4%B8%AD%E6%96%87'])
        self.assertEqual(draft['project_id'], 'a &/中文')
        self.assertEqual(draft['baseline'], {'already-saved'})
        self.assertTrue(draft['id'].startswith('@new:')); ipc.assert_not_called()

    def test_new_rejects_missing_project_duplicate_names_and_projectless_before_navigation(self):
        desktop = Desktop()
        for project, projects in [('missing', []), ('__projectless__', []),
                                  ('a', [{'id': 'a', 'name': 'Same'}, {'id': 'b', 'name': 'Same'}])]:
            with self.subTest(project=project), patch('interaction.sys.platform', 'darwin'), \
                    patch.object(desktop, 'projects', return_value=projects), patch('interaction.subprocess.run') as run:
                with self.assertRaises(ValueError): desktop.open_new_chat(project)
                run.assert_not_called()

    def test_draft_controls_do_not_reopen_or_read_saved_chat_titles(self):
        desktop = Desktop()
        desktop._new_composer = {'id': '@new:test', 'project': 'Alpha', 'project_id': 'a'}
        desktop._composer_helper_dir = SimpleNamespace(name='/tmp/fake-project-helper')
        with patch('interaction.sys.platform', 'darwin'), patch.object(desktop, 'open_chat') as navigate, \
                patch.object(desktop, '_composer_title') as titles, \
                patch('interaction.subprocess.run', return_value=SimpleNamespace(stderr=b'')) as run:
            for action in ('dictate-start', 'dictate-stop', 'send'):
                desktop.composer_action('@new:test', action)
                self.assertEqual(json.loads(run.call_args.kwargs['input']),
                    {'thread': '@new:test', 'action': action, 'draftProject': 'Alpha'})
        navigate.assert_not_called(); titles.assert_not_called()

    def test_expired_draft_cannot_fall_back_to_an_existing_chat(self):
        desktop = Desktop()
        with patch('interaction.sys.platform', 'darwin'), patch.object(desktop, 'prepare_composer'), \
                patch.object(desktop, 'open_chat') as navigate, patch('interaction.subprocess.run') as run:
            with self.assertRaises(ComposerActionError): desktop.composer_action('@new:expired', 'send')
        navigate.assert_not_called(); run.assert_not_called()

    def test_hold_release_inserts_without_transcription_prefill_or_submission(self):
        token = self.review.token
        self.assertTrue(self.action('record'))
        self.assertEqual(self.review.mode, 10)
        self.assertFalse(self.review.action('record', token))
        self.assertFalse(self.action('sessions'))
        self.assertFalse(self.action('ok'))
        self.review.finish_dictation()
        self.assertEqual(self.review.mode, 1)
        self.assertEqual(self.desktop.calls, [('one', 'dictate-start'), ('one', 'dictate-stop')])
        self.assertEqual(self.desktop.sent, [])
        self.assertTrue(self.action('ok'))
        self.assertEqual(self.desktop.sent, ['one'])

    def test_legacy_card_never_starts_pc_microphone(self):
        self.review.pc_dictation_capable = False
        self.assertFalse(self.action('record'))
        self.assertEqual(self.review.mode, 4)
        self.assertIn('请更新设备固件', self.review.text)
        self.assertEqual(self.desktop.calls, [])

    def test_release_or_disconnect_cleanup_is_never_repeated(self):
        self.action('record')
        self.review.finish_dictation(cancel=True)
        self.review.finish_dictation(cancel=True)
        self.assertEqual(self.desktop.calls, [('one', 'dictate-start'), ('one', 'dictate-cancel')])
        self.assertEqual(self.desktop.sent, [])
        self.assertEqual(self.review.mode, 4)

    def test_manual_dictation_is_not_adopted_or_cancelled(self):
        with patch.object(self.desktop, 'composer_action', side_effect=ComposerActionError('dictation-already-active')) as action:
            self.assertFalse(self.action('record'))
        action.assert_called_once_with('one', 'dictate-start')
        self.assertIsNone(self.review.dictation_thread)

    def test_attempted_start_without_readiness_is_cancelled_in_same_chat(self):
        with patch.object(self.desktop, 'composer_action', side_effect=[ComposerActionError('dictation-start-not-ready'), None]) as action:
            self.assertFalse(self.action('record'))
        self.assertEqual([call.args for call in action.call_args_list],
                         [('one', 'dictate-start'), ('one', 'dictate-cancel')])

    def test_unknown_timeout_without_press_evidence_does_not_cancel_manual_capture(self):
        with patch.object(self.desktop, 'composer_action', side_effect=subprocess.TimeoutExpired('helper', 8)) as action:
            self.assertFalse(self.action('record'))
        action.assert_called_once_with('one', 'dictate-start')

    def test_start_errors_show_the_actual_failure_instead_of_blame_microphone(self):
        for reason, expected in (
                ('chat-not-found', '未找到所选会话'),
                ('accessibility-denied', '开启辅助功能权限'),
                ('accessibility-view-unavailable', '无法读取 Codex 界面'),
                ('multiple-writable-editors', '关闭多余输入框'),
                ('composer-button-unavailable', '语音输入暂不可用'),
                ('dictation-already-active', '语音输入正在进行')):
            with self.subTest(reason=reason):
                self.review.change(1)
                with patch.object(self.desktop, 'composer_action', side_effect=ComposerActionError(reason)) as action:
                    self.assertFalse(self.action('record'))
                action.assert_called_once_with('one', 'dictate-start')
                self.assertIn(expected, self.review.text)
                self.assertNotIn('microphone', self.review.text)

    def test_stop_failure_never_falls_back_to_send_or_toggle(self):
        self.action('record')
        with patch.object(self.desktop, 'composer_action', side_effect=ComposerActionError('chat-changed')) as action:
            self.review.finish_dictation()
        action.assert_called_once_with('one', 'dictate-stop')
        self.assertEqual(self.desktop.sent, [])
        self.assertEqual(self.review.mode, 4)
        self.assertIn('在电脑上停止录音', self.review.text)

    def test_approval_progress_survives_dictation_without_granting_approval(self):
        pending = self.broker.add({'session_id': 'one', 'tool_name': '工具', 'tool_input': {'arg': 'a|b'}})
        self.review.sync(); self.action('up')
        page, seen = self.review.page, set(self.review.seen)
        self.action('record'); self.review.finish_dictation()
        self.assertEqual((self.review.mode, self.review.page, self.review.seen), (3, page, seen))
        self.assertIsNone(pending['answer'])
        self.assertEqual(self.desktop.sent, [])

    def test_new_chat_opens_native_composer_and_allows_device_dictation(self):
        self.action('back')
        self.assertEqual(self.review.mode, 7)
        self.assertTrue(self.action('new'))
        self.assertEqual(self.review.mode, 1)
        self.assertEqual(self.review.target, '@new:test')
        self.assertTrue(self.action('record'))
        self.review.finish_dictation()
        self.assertEqual(self.desktop.calls, [('项目', 'new'), ('@new:test', 'dictate-start'),
                                             ('@new:test', 'dictate-stop')])
        self.assertEqual(self.desktop.sent, [])

    def test_server_has_only_native_controls_without_an_audio_backend(self):
        with patch('interaction.Renderer', return_value=Renderer()), patch('dashboard.DashboardRenderer'):
            server = InteractionServer('a' * 32, '127.0.0.1', desktop=self.desktop)
        self.assertFalse(hasattr(server, 'transcribe'))
        self.assertFalse(hasattr(server, 'voice_input'))
        server.close()

    def test_start_timeout_carries_press_evidence_but_no_prompt(self):
        with tempfile.TemporaryDirectory() as directory:
            desktop = Desktop(directory)
            desktop._composer_helper_dir = SimpleNamespace(name=directory)
            with patch('interaction.sys.platform', 'darwin'), patch.object(desktop, 'open_chat'), \
                    patch('interaction.subprocess.run', side_effect=subprocess.TimeoutExpired('helper', 8, output=b'pressed\n')) as run:
                with self.assertRaises(ComposerActionError) as error:
                    desktop.composer_action('one', 'dictate-start')
            self.assertEqual(error.exception.reason, 'dictation-start-not-ready')
            self.assertEqual(json.loads(run.call_args.kwargs['input']), {'thread': 'one', 'action': 'dictate-start'})

    def test_only_numeric_chat_discovery_counts_are_logged(self):
        counts = dict.fromkeys(COMPOSER_DIAGNOSTIC_FIELDS, 0)
        for diagnostic, expected in ((json.dumps(counts).encode(), True),
                (json.dumps({**counts, 'text': 'private prompt'}).encode(), False),
                (json.dumps({**counts, 'links': 'private prompt'}).encode(), False),
                (b'arbitrary private stderr', False)):
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as directory:
                desktop = Desktop(directory)
                desktop._composer_helper_dir = SimpleNamespace(name=directory)
                failure = subprocess.CalledProcessError(13, 'helper', stderr=diagnostic)
                with patch('interaction.sys.platform', 'darwin'), patch.object(desktop, 'open_chat'), \
                        patch('interaction.subprocess.run', side_effect=failure), patch('builtins.print') as report:
                    with self.assertRaises(ComposerActionError):
                        desktop.composer_action('one', 'dictate-start')
                logged = [call.args for call in report.call_args_list]
                self.assertEqual(any(args[0] == '电脑端会话发现统计：' for args in logged), expected)
                self.assertNotIn('private', str(logged))

    def test_native_stage_timings_accept_only_fixed_numeric_fields(self):
        timings = dict.fromkeys(COMPOSER_TIMING_FIELDS, 12)
        for values, accepted in ((timings, True), ({**timings, 'text': 'private'}, False),
                ({**timings, 'setup_ms': 'private'}, False), ({**timings, 'setup_ms': True}, False),
                ({**timings, 'setup_ms': -1}, False), ({**timings, 'setup_ms': 60001}, False)):
            with self.subTest(values=values), patch('builtins.print') as report:
                report_composer_diagnostics(json.dumps(values).encode())
                self.assertEqual(report.called, accepted)
                if accepted:
                    self.assertEqual(report.call_args.args[0], '电脑端原生操作耗时：')
                self.assertNotIn('private', str(report.call_args_list))
        counts = dict.fromkeys(COMPOSER_DIAGNOSTIC_FIELDS, 0)
        with patch('builtins.print') as report:
            report_composer_diagnostics(json.dumps(counts).encode() + b'\n' + json.dumps(timings).encode())
        self.assertEqual([call.args[0] for call in report.call_args_list],
                         ['电脑端会话发现统计：', '电脑端原生操作耗时：'])

    def test_successful_native_action_reports_numeric_stage_timing(self):
        with tempfile.TemporaryDirectory() as directory:
            desktop = Desktop(directory)
            desktop._composer_helper_dir = SimpleNamespace(name=directory)
            timings = dict.fromkeys(COMPOSER_TIMING_FIELDS, 10)
            result = subprocess.CompletedProcess(['helper'], 0, stderr=json.dumps(timings).encode())
            with patch('interaction.sys.platform', 'darwin'), patch.object(desktop, 'open_chat'), \
                    patch('interaction.subprocess.run', return_value=result), patch('builtins.print') as report:
                desktop.composer_action('one', 'dictate-start')
            self.assertEqual(report.call_args_list[0].args[0], '电脑端原生操作耗时：')

    def test_native_control_counts_never_include_labels_or_text(self):
        counts = dict.fromkeys(COMPOSER_CONTROL_FIELDS, 1)
        for values, accepted in ((counts, True), ({**counts, 'title': 'private'}, False),
                ({**counts, 'editors': 'private'}, False), ({**counts, 'candidates': -1}, False)):
            with self.subTest(values=values), patch('builtins.print') as report:
                report_composer_diagnostics(json.dumps(values).encode())
                self.assertEqual(report.called, accepted)
                if accepted: self.assertEqual(report.call_args.args[0], '电脑端原生控件统计：')
                self.assertNotIn('private', str(report.call_args_list))

    def test_button_sidebar_binding_requires_a_fresh_unique_title(self):
        for rows, title in (([{'id': 'one', 'title': 'First'}], 'First'),
                ([{'id': 'one', 'title': 'Same'}, {'id': 'two', 'title': 'Same'}], None),
                ([], None)):
            with self.subTest(title=title), tempfile.TemporaryDirectory() as directory:
                desktop = Desktop(directory)
                desktop._composer_helper_dir = SimpleNamespace(name=directory)
                with closing(sqlite3.connect(str(Path(directory) / 'state_5.sqlite'))) as db:
                    db.execute('CREATE TABLE threads (id TEXT, name TEXT, archived INTEGER, agent_path TEXT)')
                    db.executemany('INSERT INTO threads VALUES (?, ?, 0, NULL)',
                                   [(row['id'], row['title']) for row in rows])
                    db.commit()
                with patch('interaction.sys.platform', 'darwin'), patch.object(desktop, 'open_chat'), \
                        patch.object(desktop, '_scan_sessions') as full_scan, patch('interaction.subprocess.run') as run:
                    desktop.composer_action('one', 'dictate-start')
                full_scan.assert_not_called()
                request = json.loads(run.call_args.kwargs['input'])
                self.assertEqual(request.get('title'), title)
                self.assertEqual(request['thread'], 'one')

    def test_stop_and_cancel_never_navigate_or_fill_a_composer(self):
        with tempfile.TemporaryDirectory() as directory:
            desktop = Desktop(directory)
            desktop._composer_helper_dir = SimpleNamespace(name=directory)
            with patch('interaction.sys.platform', 'darwin'), patch.object(desktop, 'open_chat') as navigate, \
                    patch('interaction.subprocess.run') as run:
                desktop.composer_action('one', 'dictate-stop')
                desktop.composer_action('one', 'dictate-cancel')
            navigate.assert_not_called()
            self.assertEqual([json.loads(call.kwargs['input'])['action'] for call in run.call_args_list],
                             ['dictate-stop', 'dictate-cancel'])


class NativeWireTests(unittest.TestCase):
    def setUp(self):
        try: import cryptography
        except ImportError: self.skipTest('Bridge requires cryptography')
        self.server = InteractionServer.__new__(InteractionServer)
        self.server.key = 'a' * 32
        self.server.desktop, self.server.broker = FakeDesktop(), Broker()
        self.server.renderer, self.server.selection = Renderer(), SelectionMemory()
        self.server.active, self.server.target = threading.Lock(), None
        self.client, accepted = socket.socketpair()
        self.client.settimeout(2)
        self.worker = threading.Thread(target=self.server.handle, args=(accepted,))
        self.worker.start()
        self.wire = SecureChannel(self.client, self.server.key)
        self.addCleanup(self.disconnect)

    def disconnect(self):
        self.client.close(); self.worker.join(2)
        self.assertFalse(self.worker.is_alive())

    def request(self, command, token='', capable=True):
        self.wire.send(b'\x01' + json.dumps({'cmd': command, 'token': token, 'pc_dictation': capable}).encode())
        reply = self.wire.receive()
        return reply[0], reply[1:17].hex()

    def begin(self, capable=True):
        _, token = self.request('sync', capable=capable)
        _, token = self.request('ok', token, capable)
        return self.request('record', token, capable)

    def test_release_needs_current_token_and_never_submits_audio_or_message(self):
        mode, token = self.begin()
        self.assertEqual(mode, 10)
        self.assertEqual(self.request('stop', '0' * 32)[0], 10)
        self.assertEqual(self.request('stop', token)[0], 1)
        self.assertEqual(self.server.desktop.calls, [('one', 'dictate-start'), ('one', 'dictate-stop')])
        self.assertEqual(self.server.desktop.sent, [])
        self.assertFalse(hasattr(self.server, 'transcribe'))

    def test_disconnect_cancels_only_the_owned_capture(self):
        self.assertEqual(self.begin()[0], 10)
        self.disconnect()
        self.assertEqual(self.server.desktop.calls, [('one', 'dictate-start'), ('one', 'dictate-cancel')])
        self.assertEqual(self.server.desktop.sent, [])

    def test_pcm_is_rejected_and_capture_cancelled_in_native_mode(self):
        self.begin()
        self.wire.send(b'\x02' + bytes(1024))
        self.worker.join(2)
        self.assertFalse(self.worker.is_alive())
        self.assertEqual(self.server.desktop.calls[-1], ('one', 'dictate-cancel'))
        self.assertFalse(hasattr(self.server, 'transcribe'))

    def test_no_capability_means_no_pc_capture_and_no_new_wire_mode(self):
        self.assertEqual(self.begin(capable=False)[0], 4)
        self.assertEqual(self.server.desktop.calls, [])


class CLIOptionsTests(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1] /
                              'tools/codex_pet/bridge.py'), 'run', *args],
                              capture_output=True, text=True, timeout=5)

    def test_help_exposes_only_native_control_configuration(self):
        result = self.run_cli('--help')
        self.assertEqual(result.returncode, 0)
        for option in ('--voice-input', '--model', '--asr-backend', '--asr-language',
                       '--asr-context', '--chinese-script'):
            self.assertNotIn(option, result.stdout)
        self.assertIn('--interactive', result.stdout)

    def test_retired_options_cannot_enable_a_fallback(self):
        for option, value in (('--voice-input', 'card'), ('--model', '/not/a/model')):
            with self.subTest(option=option):
                result = self.run_cli(option, value)
                self.assertEqual(result.returncode, 2)
                self.assertIn('无法识别的参数', result.stderr)


if __name__ == '__main__': unittest.main()
