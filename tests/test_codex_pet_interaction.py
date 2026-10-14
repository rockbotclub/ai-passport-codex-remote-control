"""Exercise cross-session isolation, stale approvals, explicit review and wire auth."""
import sys
from contextlib import closing
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools/codex_pet'))
from interaction import (Broker, Review, SecureChannel, SelectionMemory, exact,
                         WIDTH, HEIGHT, PIXELS, MAX_RECORD, LIST_ENTRIES, LIST_LINE_HEIGHT)
import socket
import threading
import time
import unittest
from unittest.mock import patch
import tempfile
import sqlite3

class Desktop:
    def __init__(self):
        self.sent, self.drafts, self.staged, self.created = [], {}, [], []
        self.new_sent = []
        self.job = {'status': 'running', 'thread': None, 'project': None}
    def sessions(self): return [{'id': 'one', 'title': 'First', 'project': 'Alpha'}, {'id': 'two', 'title': 'Second', 'project': 'Beta'}]
    def projects(self):
        return list({s.get('project_id', s['project']): {'id': s.get('project_id', s['project']), 'name': s['project']}
                     for s in self.sessions()}.values())
    def new_session(self, project): self.created.append(project)
    def send_new(self, project, text):
        self.new_sent.append((project, text))
        self.job['project'] = project
        return 'job'
    def new_status(self, identity): return dict(self.job)
    def owner(self, thread): raise AssertionError('Voice must not discover a desktop owner')
    def send(self, thread, text): self.sent.append((thread, text))
    def draft(self, thread): raise AssertionError('Voice must not read PC input')
    def stage(self, thread, text):
        self.drafts[thread] = text
        self.staged.append((thread, text))

class Renderer:
    def __init__(self): self.last = ''
    def pages(self, text): return text.split('|') or ['']
    def bitmap(self, text, selection=None):
        self.last, self.selection = text, selection
        return bytes(PIXELS)
    def summary(self, text, count=1): return [text]

class ProjectNavigationTests(unittest.TestCase):
    def setUp(self):
        self.desktop, self.broker = Desktop(), Broker()
        self.rows = [{'id':'one','title':'First','project':'Same name','project_id':'a'},
                     {'id':'two','title':'Second','project':'Same name','project_id':'a'},
                     {'id':'other','title':'Other project chat','project':'Same name','project_id':'b'}]
        self.desktop.sessions = lambda: list(self.rows)
        self.desktop.projects = lambda: [{'id':'a','name':'Same name'}, {'id':'b','name':'Same name'},
                                         {'id':'empty','name':'Empty project'}]
        self.review = Review(self.desktop, self.broker, Renderer())
        self.review.sync()
    def action(self, name): return self.review.action(name, self.review.token)
    def test_wake_enters_sessions_without_moving_or_sending_and_restores_choice(self):
        self.assertTrue(self.review.action('sessions', 'stale-navigation-token'))
        self.assertEqual(self.review.mode, 1)
        self.assertEqual(self.review.target, 'one')
        self.action('down')
        self.action('back')
        self.action('down') # Browsing another project is not selecting a chat.
        self.assertEqual(self.review.project, 'b')
        self.assertTrue(self.review.action('sessions', 'stale-navigation-token'))
        self.assertEqual((self.review.project, self.review.target), ('a', 'two'))
        self.assertEqual(self.desktop.sent, [])
        self.assertEqual(self.desktop.staged, [])

    def test_selection_survives_reconnection_and_private_file_reload(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'selection.json'
            memory = SelectionMemory(path)
            self.review.selection = memory
            self.action('ok'); self.action('down')
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            for selection in (memory, SelectionMemory(path)):
                restored = Review(self.desktop, self.broker, Renderer(), selection)
                restored.action('sessions', '')
                self.assertEqual((restored.mode, restored.project, restored.target), (1, 'a', 'two'))

    def test_closed_remembered_chat_falls_back_and_corrupt_memory_is_ignored(self):
        memory = SelectionMemory(); memory.remember('a', 'closed')
        restored = Review(self.desktop, self.broker, Renderer(), memory)
        restored.action('sessions', '')
        self.assertEqual(restored.target, 'one')
        self.assertEqual(memory.target, 'one')
        self.rows.clear(); restored.refresh_at = 0
        restored.action('sessions', '')
        self.assertIsNone(restored.target)
        self.assertFalse(restored.action('record', restored.token))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'selection.json'
            for data in ('broken', '[]', '{"project":1,"target":null}', 'x' * 8193):
                path.write_text(data)
                self.assertIsNone(SelectionMemory(path).target)

    def test_wake_resumes_voice_and_approval_without_submitting_or_denying(self):
        self.action('ok'); self.action('record'); self.review.transcript('draft')
        self.assertTrue(self.action('sessions'))
        self.assertEqual(self.review.mode, 2)
        self.assertEqual(self.desktop.sent, [])
        self.action('back')
        pending = self.broker.add({'session_id':'one','tool_name':'Bash'})
        self.review.sync()
        self.assertTrue(self.action('sessions'))
        self.assertEqual(self.review.mode, 3)
        self.assertIsNone(pending['answer'])
    def test_startup_is_projects_and_does_not_select_or_record_a_chat(self):
        frame = self.review.screen()
        self.assertEqual(frame[0], 7)
        self.assertIsNone(self.review.target)
        self.assertNotIn('First', self.review.renderer.last)
        self.assertIn('2 sessions', self.review.renderer.last)
        self.assertNotRegex(self.review.renderer.last, r'\[\d+/\d+\]')
        self.assertFalse(self.action('record'))
        self.assertEqual(self.desktop.created, [])
    def test_enter_filters_by_id_and_back_restores_project_and_chat_selection(self):
        self.assertTrue(self.action('ok'))
        self.review.screen()
        self.assertNotIn('Other project chat', self.review.renderer.last)
        self.action('down'); self.assertEqual(self.review.target, 'two')
        self.action('back'); self.assertEqual(self.review.mode, 7)
        self.assertEqual(self.review.project, 'a'); self.assertIsNone(self.review.target)
        self.action('ok'); self.assertEqual(self.review.target, 'two')
        self.action('back'); self.action('down'); self.action('ok')
        self.assertEqual(self.review.target, 'other')
        self.review.screen(); self.assertNotIn('Second', self.review.renderer.last)
    def test_empty_project_and_missing_desktop_remain_navigable(self):
        self.action('up'); self.action('ok')
        self.assertIsNone(self.review.target)
        self.assertIn(b'\x01', self.review.screen()[:1])
        self.assertIn('No sessions yet', self.review.renderer.last)
        self.assertFalse(self.action('record')); self.assertFalse(self.action('ok'))
        self.action('back'); self.assertEqual(self.review.project, 'empty')
        self.desktop.projects = lambda: []
        self.rows.clear(); self.review.refresh_at = 0
        self.review.screen()
        self.assertFalse(self.action('up')); self.assertFalse(self.action('new'))
        self.assertFalse(self.action('ok'))
    def test_refresh_invalidates_old_screen_even_when_selected_chat_survives(self):
        self.action('ok'); token = self.review.token
        self.rows.reverse(); self.review.refresh_at = 0
        self.assertFalse(self.review.action('record', token))
        self.assertEqual(self.review.target, 'one')
        token = self.review.token
        self.rows[:] = [s for s in self.rows if s['id'] != 'one']
        self.review.refresh_at = 0
        self.assertFalse(self.review.action('record', token))
        self.assertEqual(self.review.target, 'two')
        self.assertEqual(self.desktop.staged, [])
    def test_new_records_selected_project_and_confirm_submits_first_voice_once(self):
        self.action('down'); token = self.review.token
        self.assertTrue(self.review.action('new', token))
        self.assertEqual(self.desktop.created, ['b'])
        self.assertEqual(self.review.mode, 1)
        self.assertIsNone(self.review.target)
        self.assertEqual(self.review.new_project, 'b')
        self.assertFalse(self.review.action('new', token))
        self.review.screen(); self.assertIn('Hold OK to record', self.review.renderer.last)
        self.assertFalse(self.action('ok'))
        # Refresh and wake cannot retarget an uncreated draft to the old chat.
        self.review.refresh_at = 0; self.review.sync(); self.action('sessions')
        self.assertEqual((self.review.project, self.review.target), ('b', None))
        self.assertTrue(self.action('record')); self.review.transcript('first')
        self.assertTrue(self.action('record')); self.review.transcript(' second')
        self.assertEqual(self.desktop.staged, [])
        token = self.review.token
        self.assertTrue(self.review.action('ok', token))
        self.assertEqual(self.desktop.new_sent, [('b', 'firstsecond')])
        self.assertEqual(self.review.mode, 8)
        self.assertFalse(self.review.action('ok', token))
        self.assertFalse(self.action('record'))
        self.action('back')
        self.assertEqual(self.review.mode, 7); self.assertEqual(self.review.project, 'b')
        self.action('ok'); self.assertFalse(self.action('new'))
        self.assertEqual(self.desktop.sent, [])

    def test_new_cancel_empty_speech_and_timeout_do_not_create_a_chat(self):
        self.action('new'); self.action('record'); self.review.transcript('')
        self.assertEqual(self.review.mode, 4)
        self.action('back'); self.assertTrue(self.action('record'))
        self.review.transcript('draft'); self.review.expires = 0; self.review.sync()
        self.assertEqual((self.review.mode, self.review.target), (1, None))
        self.action('back')
        self.assertEqual(self.review.mode, 7)
        self.assertIsNone(self.review.new_project)
        self.assertEqual(self.desktop.new_sent, [])

    def test_new_send_failure_consumes_confirm_without_automatic_retry(self):
        self.action('new'); self.action('record'); self.review.transcript('voice')
        token = self.review.token
        with patch.object(self.desktop, 'send_new', side_effect=EOFError()) as submit:
            self.assertTrue(self.review.action('ok', token))
            self.assertEqual(self.review.mode, 4)
            self.assertFalse(self.review.action('ok', token))
            self.assertFalse(self.action('record'))
            self.review.sync(); self.review.screen(); submit.assert_called_once_with('a', 'voice')
        self.action('back'); self.assertEqual(self.review.mode, 7)

    def test_new_handoff_selects_only_created_thread_after_cli_exit(self):
        self.action('new'); self.action('record'); self.review.transcript('voice'); self.action('ok')
        self.rows.insert(0, {'id':'new','title':'Created','project':'Same name','project_id':'a'})
        self.desktop.job['thread'] = 'new'
        self.review.sync(); self.assertEqual(self.review.mode, 8)
        self.desktop.job['status'] = 'complete'
        self.review.sync()
        self.assertEqual((self.review.mode, self.review.target), (1, 'new'))
        self.assertEqual(self.review.selection.target, 'new')
        self.assertTrue(self.action('record'))

    def test_new_failure_after_thread_creation_is_not_reported_as_sent(self):
        self.action('new'); self.action('record'); self.review.transcript('voice'); self.action('ok')
        self.desktop.job.update(status='failed', thread='partial')
        self.review.sync(); self.assertEqual(self.review.mode, 4)
        self.assertIn('Do not retry blindly', self.review.text)
        self.assertFalse(self.action('ok'))
        self.action('back'); self.assertEqual(self.review.mode, 7)
    def test_new_failure_consumes_action_and_returns_to_projects(self):
        with patch.object(self.desktop, 'new_session', side_effect=TimeoutError()) as create:
            token = self.review.token
            self.action('new')
            self.assertEqual(self.review.mode, 4)
            self.assertFalse(self.review.action('new', token)); self.assertEqual(create.call_count, 1)
        self.action('back'); self.assertEqual(self.review.mode, 7)
    def test_back_discards_voice_and_back_from_approval_denies_exact_request(self):
        self.action('ok'); self.action('record'); self.review.transcript('draft')
        self.action('back'); self.assertEqual(self.review.mode, 1)
        self.assertEqual(self.desktop.drafts, {'one': 'draft'})
        self.assertEqual(self.review.text, '')
        pending = self.broker.add({'session_id':'one','tool_name':'Bash'})
        other = self.broker.add({'session_id':'other','tool_name':'Bash'})
        self.review.sync(); self.action('back')
        self.assertEqual(pending['answer'], 'deny'); self.assertIsNone(other['answer'])
        self.action('back'); self.review.sync(); self.assertEqual(self.review.mode, 7)
    def test_recording_rejects_back_and_new_without_retargeting(self):
        self.action('ok'); self.action('record')
        self.assertFalse(self.action('back')); self.assertFalse(self.action('new'))
        self.assertEqual(self.review.target, 'one'); self.assertEqual(self.review.mode, 5)
    def test_unassigned_sessions_have_a_group_and_cannot_create_in_another_project(self):
        from interaction import PROJECTLESS
        self.rows.append({'id':'loose','title':'Standalone','project':'No project','project_id':PROJECTLESS})
        self.review.refresh_at = 0; self.review.sync(); self.action('up')
        self.assertEqual(self.review.project, PROJECTLESS)
        self.assertFalse(self.action('new')); self.assertEqual(self.desktop.created, [])
        self.action('back'); self.action('ok'); self.assertEqual(self.review.target, 'loose')

class InteractionTests(unittest.TestCase):
    def setUp(self):
        self.desktop, self.broker = Desktop(), Broker()
        self.review = Review(self.desktop, self.broker, Renderer())
        self.review.sync()
        self.review.action('ok', self.review.token)
    def action(self, name): return self.review.action(name, self.review.token)
    def test_sessions_and_recording_pin_target_then_confirm_sends_voice_once(self):
        self.assertEqual(self.review.target, 'one')
        self.action('back'); self.action('down'); self.action('ok')
        self.assertEqual(self.review.target, 'two')
        self.assertTrue(self.action('record'))
        self.assertFalse(self.action('down'))
        self.review.transcript('hello|world')
        self.assertEqual(self.desktop.staged, [('two', 'hello|world')])
        self.assertEqual(self.review.text, 'hello|world')
        self.action('down')
        token = self.review.token
        self.assertTrue(self.review.action('ok', token))
        self.assertEqual(self.desktop.sent, [('two', 'hello|world')])
        self.assertFalse(self.review.action('ok', token))

    def test_pc_edits_do_not_change_transcript_token_or_trigger_reading(self):
        self.desktop.drafts['one'] = 'existing PC draft'
        self.action('record'); self.review.transcript('voice only')
        token = self.review.token
        for draft in ('edited on PC', {'attachments': ['file']}, ''):
            self.desktop.drafts['one'] = draft
            self.review.sync(); self.review.screen()
            self.assertEqual((self.review.mode, self.review.text), (2, 'voice only'))
            self.assertEqual(self.review.token, token)
        self.assertTrue(self.action('ok'))
        self.assertEqual(self.desktop.sent, [('one', 'voice only')])

    def test_multiple_recordings_accumulate_only_voice_and_ignore_pc_edits(self):
        self.desktop.drafts['one'] = '已有指令。'
        self.desktop.drafts['two'] = 'other chat'
        self.action('record'); self.review.transcript('第一段。')
        self.assertEqual(self.review.text, '第一段。')
        self.desktop.drafts['one'] = '电脑补充。'
        self.assertTrue(self.action('record')); self.review.transcript('第二段。')
        self.assertEqual(self.review.text, '第一段。第二段。')
        self.assertEqual(self.desktop.staged, [('one', '第一段。'), ('one', '第一段。第二段。')])
        self.assertEqual(self.desktop.drafts['two'], 'other chat')
        self.assertTrue(self.action('ok'))
        self.assertEqual(self.desktop.sent, [('one', '第一段。第二段。')])

    def test_empty_additional_recording_keeps_transcript_without_refilling(self):
        self.action('record'); self.review.transcript('first segment')
        self.action('record'); self.review.transcript('   ')
        self.assertEqual((self.review.mode, self.review.text), (2, 'first segment'))
        self.assertEqual(self.desktop.staged, [('one', 'first segment')])
        self.assertTrue(self.action('ok'))
        self.assertEqual(self.desktop.sent, [('one', 'first segment')])

    def test_cancel_keeps_pc_input_and_next_recording_starts_new_voice_text(self):
        self.action('record'); self.review.transcript('previous voice')
        self.action('back')
        self.assertEqual(self.desktop.drafts['one'], 'previous voice')
        self.action('record'); self.review.transcript('new voice')
        self.assertEqual(self.review.text, 'new voice')
        self.assertEqual(self.desktop.staged[-1], ('one', 'new voice'))
        self.assertEqual(self.desktop.sent, [])

    def test_desktop_submit_or_delete_does_not_affect_voice_preview(self):
        self.action('record'); self.review.transcript('voice')
        token = self.review.token
        self.desktop.drafts.clear()
        self.review.sync()
        self.assertEqual((self.review.mode, self.review.text, self.review.token), (2, 'voice', token))
        self.assertTrue(self.action('ok'))
        self.assertEqual(self.desktop.sent, [('one', 'voice')])

    def test_input_filling_failure_keeps_transcript_and_allows_more_voice(self):
        self.desktop.drafts['one'] = 'keep this'
        with patch.object(self.desktop, 'stage', side_effect=TimeoutError()) as stage:
            self.action('record'); self.review.transcript('new voice')
            self.assertEqual((self.review.mode, self.review.text), (2, 'new voice'))
            self.action('record'); self.review.transcript(' again')
            self.assertEqual((self.review.mode, self.review.text), (2, 'new voiceagain'))
            self.assertEqual(stage.call_count, 2)
        self.assertEqual(self.desktop.drafts['one'], 'keep this')
        self.assertTrue(self.action('ok'))
        self.assertEqual(self.desktop.sent, [('one', 'new voiceagain')])

    def test_oversized_accumulated_voice_is_bounded_before_input_filling(self):
        self.action('record'); self.review.transcript('a' * 12000)
        self.action('record'); self.review.transcript('b')
        self.assertEqual(self.review.mode, 4)
        self.assertFalse(self.action('ok'))
        self.assertEqual(len(self.desktop.staged), 1)
        self.assertEqual(self.desktop.sent, [])

    def test_preview_expiry_starts_new_voice_without_reading_pc_input(self):
        self.action('record'); self.review.transcript('old voice')
        self.review.expires = 0
        self.review.sync()
        self.assertEqual(self.review.mode, 1)
        self.action('record'); self.review.transcript('fresh voice')
        self.assertEqual(self.review.text, 'fresh voice')
        self.assertEqual(self.desktop.staged[-1], ('one', 'fresh voice'))

    def test_list_displays_titles_projects_and_selection(self):
        self.review.screen()
        content = self.review.renderer.last
        self.assertIn('First', content)
        self.assertNotRegex(content, r'\[\d+/\d+\]')
        self.assertIn('Alpha', content)
        self.assertNotIn('Second', content)
        self.assertNotIn('Beta', content)
        self.assertEqual(self.review.renderer.selection,(0,2))
        self.action('back'); self.action('down'); self.action('ok'); self.review.screen()
        self.assertIn('Second', self.review.renderer.last)
        self.assertNotRegex(self.review.renderer.last, r'\[\d+/\d+\]')
        self.assertEqual(self.review.renderer.selection,(0,2))
    def test_stale_token_cannot_send_to_another_session(self):
        old = self.review.token
        self.action('down')
        self.assertFalse(self.review.action('record', old))
        self.assertEqual(self.desktop.sent, [])
    def test_approval_bound_to_session_and_all_pages(self):
        pending = self.broker.add({'session_id': 'one', 'tool_name': 'Bash', 'tool_input': {'command': 'first|second'}})
        self.review.sync()
        self.assertEqual(self.review.mode, 3)
        self.assertFalse(self.action('ok'))
        self.assertFalse(self.broker.resolve(pending['id'], 'two', 'allow'))
        self.action('up')
        old = self.review.token
        self.assertTrue(self.action('ok'))
        self.assertEqual(pending['answer'], 'allow')
        self.assertFalse(self.review.action('ok', old))
        self.assertFalse(self.broker.resolve(pending['id'], 'one', 'allow'))
    def test_decline_expiry_and_interrupt(self):
        for reason in ('down', 'expiry', 'interrupt'):
            pending = self.broker.add({'session_id':'one', 'tool_name':'Bash'})
            self.review.sync()
            if reason == 'down':
                self.action('down'); self.assertEqual(pending['answer'], 'deny')
            else:
                token = self.review.token
                if reason == 'expiry': pending['expires'] = 0
                else: self.broker.invalidate('one')
                self.assertFalse(self.review.action('ok', token))
                self.assertIsNone(pending['answer'])
    def test_recording_and_transcription_ignore_unavailable_pc_input_and_owner(self):
        with patch.object(self.desktop, 'owner', side_effect=EOFError()) as owner, \
                patch.object(self.desktop, 'draft', side_effect=ValueError()) as draft, \
                patch.object(self.desktop, 'send', side_effect=TimeoutError()) as send:
            self.assertTrue(self.action('record'))
            self.review.transcript('hello')
            self.review.sync(); self.review.screen()
            owner.assert_not_called(); draft.assert_not_called(); send.assert_not_called()
        self.assertEqual((self.review.mode, self.review.text), (2, 'hello'))

    def test_unknown_send_consumed_no_retry(self):
        self.action('record'); self.review.transcript('hello')
        self.desktop.send = lambda *args: (_ for _ in ()).throw(TimeoutError())
        self.action('ok')
        self.assertEqual(self.review.mode, 4)
        self.assertFalse(self.action('ok'))
    def test_desktop_eof_during_send_is_uncertain_and_not_retried(self):
        self.action('record'); self.review.transcript('hello')
        with patch.object(self.desktop,'send',side_effect=EOFError('Connection closed')) as send:
            token=self.review.token
            self.assertTrue(self.review.action('ok',token))
            self.assertEqual(self.review.mode,4)
            self.assertFalse(self.review.action('ok',token))
            self.assertEqual(send.call_count,1)
    def test_empty_speech_and_cancel_never_send(self):
        self.action('record'); self.review.transcript('   ')
        self.assertEqual(self.review.mode, 4)
        self.action('cancel')
        self.action('record'); self.review.transcript('hello')
        self.action('cancel')
        self.assertEqual(self.desktop.sent, [])
        self.assertEqual(self.desktop.drafts, {'one': 'hello'})
    def test_speech_errors_can_dismiss_navigate_and_record_again_on_same_connection(self):
        try: import cryptography
        except ImportError: self.skipTest('Bridge requires cryptography')
        import json
        from interaction import InteractionServer
        for result in ('', '   ', ValueError('Inference failed')):
            for new_chat in (False, True):
                with self.subTest(result=result, new_chat=new_chat):
                    desktop = Desktop()
                    server = InteractionServer.__new__(InteractionServer)
                    server.key, server.desktop = 'a'*32, desktop
                    server.broker, server.renderer = Broker(), Renderer()
                    server.active, server.target = threading.Lock(), None
                    server.selection = SelectionMemory()
                    outcomes = iter((result, 'retry voice'))
                    def transcribe(pcm):
                        outcome = next(outcomes)
                        if isinstance(outcome, Exception):
                            raise outcome
                        return outcome
                    server.transcribe = transcribe
                    a,b = socket.socketpair()
                    a.settimeout(2)
                    worker = threading.Thread(target=server.handle,args=(b,)); worker.start()
                    try:
                        with a:
                            wire = SecureChannel(a,'a'*32)
                            def request(command, token=''):
                                wire.send(b'\x01'+json.dumps({'cmd':command,'token':token}).encode())
                                reply = wire.receive()
                                self.assertEqual(len(reply),17+PIXELS)
                                return reply[0],reply[1:17].hex()
                            mode,token = request('sync'); self.assertEqual(mode,7)
                            mode,token = request('new' if new_chat else 'ok',token)
                            self.assertEqual(mode,1)
                            mode,token = request('record',token); self.assertEqual(mode,5)
                            recording_token = token
                            wire.send(b'\x02'+bytes(1024))
                            mode,token = request('stop',token); self.assertEqual(mode,4)
                            if not isinstance(result, Exception):
                                self.assertIn('No speech recognized', server.renderer.last)
                            self.assertIn('Press any key to dismiss.', server.renderer.last)
                            error_token = token
                            mode,token = request('cancel',recording_token); self.assertEqual(mode,4)
                            self.assertEqual(token,error_token)
                            # Waking an error after local inactivity must still allow dismissal.
                            mode,token = request('sessions'); self.assertEqual(mode,4)
                            mode,token = request('cancel',token); self.assertEqual(mode,1)
                            self.assertEqual(server.target,None if new_chat else 'one')
                            self.assertEqual(desktop.sent,[])
                            self.assertEqual(desktop.new_sent,[])
                            self.assertEqual(desktop.staged,[])
                            mode,token = request('record',token); self.assertEqual(mode,5)
                            wire.send(b'\x02'+bytes(1024))
                            mode,token = request('stop',token); self.assertEqual(mode,2)
                            mode,token = request('cancel',token); self.assertEqual(mode,1)
                            mode,token = request('back',token); self.assertEqual(mode,7)
                            mode,token = request('down',token); self.assertEqual(mode,7)
                            mode,token = request('ok',token); self.assertEqual(mode,1)
                            self.assertEqual(server.target,'two')
                            self.assertEqual(desktop.sent,[])
                            self.assertEqual(desktop.new_sent,[])
                    finally:
                        a.close()
                        worker.join(2)
                    self.assertFalse(worker.is_alive())
    def test_eof_is_not_infinite_loop(self):
        a,b=socket.socketpair();b.close()
        with a, self.assertRaises(EOFError): exact(a, 4)
    def test_encrypted_audio_and_reply(self):
        try: import cryptography
        except ImportError: self.skipTest('Install bridge requirements to test AES-GCM')
        a,b = socket.socketpair()
        errors = []
        def server():
            try:
                with b:
                    wire=SecureChannel(b,'a'*32,True)
                    self.assertEqual(wire.receive(), b'\x02private audio')
                    wire.send(b'\x01reply')
            except BaseException as error: errors.append(error)
        t=threading.Thread(target=server);t.start()
        with a:
            wire=SecureChannel(a,'a'*32)
            wire.send(b'\x02private audio');self.assertEqual(wire.receive(),b'\x01reply')
        t.join(2); self.assertFalse(t.is_alive()); self.assertEqual(errors,[])
    def test_full_voice_flow_uses_encrypted_transport_and_fake_desktop(self):
        try: import cryptography
        except ImportError: self.skipTest('Bridge requires cryptography')
        from interaction import InteractionServer
        server = InteractionServer.__new__(InteractionServer)
        server.key, server.desktop = 'a'*32, self.desktop
        server.broker, server.renderer = self.broker, Renderer()
        server.active, server.target = threading.Lock(), None
        server.selection = SelectionMemory()
        server.transcribe = lambda pcm: 'reviewed voice'
        a,b = socket.socketpair()
        t=threading.Thread(target=server.handle,args=(b,));t.start()
        with a:
            wire=SecureChannel(a,'a'*32)
            import json
            def request(cmd, token=''):
                wire.send(b'\x01'+json.dumps({'cmd':cmd,'token':token}).encode())
                reply=wire.receive()
                self.assertEqual(len(reply),17 + PIXELS)
                return reply[0],reply[1:17].hex()
            mode,token=request('sync');self.assertEqual(mode,7)
            mode,token=request('sessions');self.assertEqual(mode,1)
            self.assertEqual(server.target, 'one')
            mode,token=request('back',token);self.assertEqual(mode,7)
            mode,token=request('down',token)
            mode,token=request('ok',token);self.assertEqual(mode,1)
            mode,token=request('record',token);self.assertEqual(mode,5)
            wire.send(b'\x02'+bytes(1024))
            mode,token=request('stop',token);self.assertEqual(mode,2)
            old=token
            mode,token=request('ok',token);self.assertEqual(mode,1)
            request('ok',old)
        t.join(2);self.assertFalse(t.is_alive())
        self.assertEqual(self.desktop.sent,[('two','reviewed voice')])
        # A fresh authenticated connection restores the choice on its first wake.
        a,b = socket.socketpair()
        t=threading.Thread(target=server.handle,args=(b,));t.start()
        with a:
            wire=SecureChannel(a,'a'*32)
            mode,token=request('sessions');self.assertEqual(mode,1)
            self.assertEqual(server.target, 'two')
            self.assertEqual(self.desktop.sent,[('two','reviewed voice')])
        t.join(2);self.assertFalse(t.is_alive())

    def test_new_chat_voice_and_single_confirm_use_existing_encrypted_protocol(self):
        try:
            import cryptography
        except ImportError:
            self.skipTest('Bridge requires cryptography')
        import json
        from interaction import InteractionServer, PIXELS
        server = InteractionServer.__new__(InteractionServer)
        server.key, server.desktop = 'a'*32, self.desktop
        server.broker, server.renderer = self.broker, Renderer()
        server.active, server.target = threading.Lock(), None
        server.selection = SelectionMemory()
        server.transcribe = lambda pcm: 'first voice'
        a,b = socket.socketpair()
        worker = threading.Thread(target=server.handle,args=(b,)); worker.start()
        with a:
            wire = SecureChannel(a,'a'*32)
            def request(command, token=''):
                wire.send(b'\x01'+json.dumps({'cmd':command,'token':token}).encode())
                reply = wire.receive()
                self.assertEqual(len(reply),17+PIXELS)
                return reply[0],reply[1:17].hex()
            mode,token = request('sync'); self.assertEqual(mode,7)
            mode,token = request('new',token); self.assertEqual(mode,1)
            self.assertIsNone(server.target)
            mode,token = request('record',token); self.assertEqual(mode,5)
            wire.send(b'\x02'+bytes(1024))
            mode,token = request('stop',token); self.assertEqual(mode,2)
            old = token
            mode,token = request('ok',token); self.assertEqual(mode,8)
            mode,token = request('ok',old); self.assertEqual(mode,8)
        worker.join(2); self.assertFalse(worker.is_alive())
        self.assertEqual(self.desktop.new_sent,[('Alpha','first voice')])
        self.assertEqual(self.desktop.sent,[])
        self.assertEqual(self.desktop.staged,[])

    def test_wrong_pairing_key_rejected(self):
        try: import cryptography
        except ImportError: self.skipTest('Install bridge requirements to test AES-GCM')
        a,b=socket.socketpair()
        def server():
            with b:
                try: SecureChannel(b,'a'*32,True)
                except EOFError: pass
        t=threading.Thread(target=server);t.start()
        with a, self.assertRaises(ValueError): SecureChannel(a,'b'*32)
        t.join(2);self.assertFalse(t.is_alive())

    def test_record_authentication_failure_closes_transport(self):
        try: import cryptography
        except ImportError: self.skipTest('Install bridge requirements to test AES-GCM')
        import struct
        a,b=socket.socketpair();errors=[]
        def server():
            try:
                with b:
                    wire=SecureChannel(b,'a'*32,True)
                    wire.receive()
            except Exception as error:errors.append(error)
        t=threading.Thread(target=server);t.start()
        with a:
            SecureChannel(a,'a'*32)
            a.sendall(struct.pack('!H',17)+bytes(17))
        t.join(2);self.assertFalse(t.is_alive())
        self.assertEqual(len(errors),1)
        self.assertIsInstance(errors[0],ValueError)
        self.assertEqual(str(errors[0]),'Record authentication failed')

    def test_reconnect_uses_fresh_keys_and_rejects_previous_record(self):
        try: import cryptography
        except ImportError: self.skipTest('Install bridge requirements to test AES-GCM')
        class RecordingSocket:
            def __init__(self,sock): self.sock,self.records=sock,[]
            def __getattr__(self,name): return getattr(self.sock,name)
            def sendall(self,data): self.records.append(data);self.sock.sendall(data)
        previous=None
        for cycle in range(3):
            a,b=socket.socketpair();received=[];errors=[]
            def server():
                try:
                    with b:
                        wire=SecureChannel(b,'a'*32,True)
                        received.append(wire.receive())
                except Exception as error: errors.append(error)
            t=threading.Thread(target=server);t.start()
            with a:
                capture=RecordingSocket(a)
                wire=SecureChannel(capture,'a'*32)
                capture.records.clear()
                if cycle==2: a.sendall(previous)
                else:
                    wire.send(b'\x01sync')
                    if cycle==0:previous=capture.records[0]
            t.join(2);self.assertFalse(t.is_alive())
            if cycle==2:
                self.assertEqual(received,[])
                self.assertEqual(len(errors),1)
                self.assertIsInstance(errors[0],ValueError)
            else:
                self.assertEqual(received,[b'\x01sync'])
                self.assertEqual(errors,[])

class RendererTests(unittest.TestCase):
    def test_control_bitmap_matches_firmware_wire_size(self):
        import re
        source = (Path(__file__).resolve().parents[1] / 'main/pet_control_layout.h').read_text()
        width = int(re.search(r'#define PET_CONTROL_WIDTH (\d+)', source)[1])
        height = int(re.search(r'#define PET_CONTROL_HEIGHT (\d+)', source)[1])
        self.assertEqual((WIDTH, HEIGHT), (width, height))
        self.assertEqual(PIXELS, width * height // 8)

    def test_new_chat_copy_and_long_project_fit_recording_panel(self):
        try:
            from interaction import Renderer as ActualRenderer
            renderer = ActualRenderer()
        except (ImportError, OSError):
            self.skipTest('Local CJK renderer unavailable')
        from PIL import Image, ImageDraw
        desktop = Desktop()
        desktop.projects = lambda: [{'id':'p','name':'中文项目名称与两层会话导航测试 '*4}]
        desktop.sessions = lambda: []
        review = Review(desktop, Broker(), renderer); review.sync()
        review.action('new', review.token)
        frame = review.screen()
        self.assertEqual(frame[0], 1)
        content = next(text for (text, _) in renderer.cache if 'Hold OK to record.' in text)
        canvas = ImageDraw.Draw(Image.new('1',(216,144)))
        bounds = canvas.multiline_textbbox((4,0),content,font=renderer.font,spacing=2)
        self.assertLessEqual(bounds[2], 216)
        self.assertLessEqual(bounds[3], 144)
        self.assertIsNone(review.target)

    def test_list_windows_cover_small_lists_and_every_selection(self):
        desktop = Desktop()
        for count in range(1, 10):
            desktop.projects = lambda: [{'id':str(i), 'name':f'Project {i}'} for i in range(count)]
            desktop.sessions = lambda: [{'id':str(i), 'title':f'Chat {i}', 'project':'Project 0',
                                        'project_id':'0'} for i in range(count)]
            review = Review(desktop, Broker(), Renderer()); review.sync()
            for index in range(count):
                review.project = str(index)
                lines, selected = review.project_rows()
                names = [line.strip() for line in lines if line.strip().startswith('Project ')]
                self.assertEqual(len(names), min(count, LIST_ENTRIES))
                self.assertIn(f'Project {index}', lines[selected[0]:selected[1]])
                self.assertEqual(names, sorted(names, key=lambda name: int(name.split()[-1])))
                self.assertNotRegex('\n'.join(lines), r'\[\d+/\d+\]')
                review.project, review.target = '0', str(index)
                lines, selected = review.session_rows()
                titles = [line.strip() for line in lines if line.strip().startswith('Chat ')]
                self.assertEqual(len(titles), min(count, LIST_ENTRIES))
                self.assertIn(f'Chat {index}', lines[selected[0]:selected[1]])
                self.assertEqual(titles, sorted(titles, key=lambda title: int(title.split()[-1])))
                self.assertNotRegex('\n'.join(lines), r'\[\d+/\d+\]')

    def test_list_bitmap_stays_within_transport_and_rejects_overflow(self):
        try:
            from interaction import Renderer as ActualRenderer
            renderer = ActualRenderer()
        except (ImportError,OSError): self.skipTest('Local CJK renderer unavailable')
        self.assertLessEqual(17 + PIXELS + 16, MAX_RECORD)
        limit = HEIGHT // LIST_LINE_HEIGHT
        self.assertEqual(len(renderer.bitmap('\n'.join(['Fits'] * limit),
                                             selection=(limit - 2, limit))), PIXELS)
        with self.assertRaises(ValueError):
            renderer.bitmap('\n'.join(['Overflow'] * (limit + 1)), selection=(limit - 1, limit + 1))

    def test_project_cards_fit_long_chinese_names_and_all_selection_positions(self):
        try:
            from interaction import Renderer as ActualRenderer
            renderer = ActualRenderer()
        except (ImportError,OSError): self.skipTest('Local CJK renderer unavailable')
        from PIL import Image
        desktop = Desktop()
        desktop.projects = lambda: [{'id':str(i),'name':'中文项目名称与两层会话导航测试 '*4} for i in range(8)]
        desktop.sessions = lambda: []
        review = Review(desktop, Broker(), renderer); review.sync()
        for index in range(8):
            review.project = str(index)
            frame = review.screen(); lines, selected = review.project_rows()
            self.assertEqual(frame[0], 7); self.assertEqual(len(frame), 17 + PIXELS)
            self.assertLessEqual(len(lines), HEIGHT // LIST_LINE_HEIGHT); self.assertIn('…', '\n'.join(lines))
            self.assertNotRegex('\n'.join(lines), r'\[\d+/\d+\]')
            self.assertEqual(lines.count('0 sessions'), LIST_ENTRIES)
            pixels = Image.frombytes('1', (WIDTH,HEIGHT), frame[17:])
            for line in range(len(lines)):
                self.assertEqual(bool(pixels.getpixel((0,line*20+10))), selected[0] <= line < selected[1])
                self.assertEqual(bool(pixels.getpixel((215,line*20+10))), selected[0] <= line < selected[1])
    def test_selected_chat_has_full_width_inverted_card_at_every_position(self):
        try:
            from interaction import Renderer as ActualRenderer
            renderer=ActualRenderer()
        except (ImportError,OSError):self.skipTest('Local CJK renderer unavailable')
        from PIL import Image
        desktop=Desktop()
        desktop.sessions=lambda:[{'id':str(i),'title':'会话选择测试标题 '*3,'project':'AI Passport'} for i in range(8)]
        review=Review(desktop,Broker(),renderer);review.sync();review.action('ok',review.token)
        for index in range(8):
            review.target=str(index)
            frame=review.screen()
            self.assertEqual(len(frame),17 + PIXELS)
            image=Image.frombytes('1',(WIDTH,HEIGHT),frame[17:])
            lines,selected=review.session_rows()
            first,end=selected
            self.assertLessEqual(len(lines),HEIGHT // LIST_LINE_HEIGHT)
            self.assertEqual(sum('AI Passport' in line for line in lines), LIST_ENTRIES)
            self.assertNotRegex('\n'.join(lines), r'\[\d+/\d+\]')
            for line in range(len(lines)):
                self.assertEqual(bool(image.getpixel((0,line*20+10))),first <= line < end)
                self.assertEqual(bool(image.getpixel((215,line*20+10))),first <= line < end)
            self.assertEqual(renderer.bitmap('\n'.join(lines),selection=selected),frame[17:])
            self.assertNotEqual(renderer.bitmap('\n'.join(lines)),frame[17:])

    def test_long_chinese_titles_and_projects_fit_list_and_review_panel(self):
        try:
            from interaction import Renderer as ActualRenderer, LINE_SPACING
            renderer = ActualRenderer()
        except (ImportError,OSError):self.skipTest('Local CJK renderer unavailable')
        from PIL import Image,ImageDraw
        desktop=Desktop()
        desktop.sessions=lambda:[{'id':str(i),'title':'中文会话标题与项目列表显示测试 '*4,
                                  'project':'中文项目名称'} for i in range(8)]
        review=Review(desktop,Broker(),renderer);review.sync();review.action('ok',review.token);review.action('down',review.token)
        review.screen();content=review.session_list()
        self.assertLessEqual(len(content.splitlines()),HEIGHT // LIST_LINE_HEIGHT)
        bounds=ImageDraw.Draw(Image.new('1',(WIDTH,HEIGHT))).multiline_textbbox((4,0),content,font=renderer.font,spacing=LINE_SPACING)
        self.assertLessEqual(bounds[2],WIDTH);self.assertLessEqual(bounds[3],HEIGHT)
        self.assertIn('中文项目名称',content)
        self.assertIn('…',content)
        self.assertNotRegex(content, r'\[\d+/\d+\]')
        self.assertEqual(content.count('中文项目名称'), LIST_ENTRIES)
        self.assertEqual(len(renderer.bitmap(content)),PIXELS)
        for page in renderer.pages('中文转写文字 '*100):
            bounds=ImageDraw.Draw(Image.new('1',(WIDTH,HEIGHT))).multiline_textbbox((4,0),page+'\n[1/99]',font=renderer.font,spacing=LINE_SPACING)
            self.assertLessEqual(bounds[3],144)

    def test_chinese_coverage_and_missing_glyph_blocks_review(self):
        try:
            import PIL, fontTools
        except ImportError:
            self.skipTest('Renderer needs the local bridge environment')
        font = Path('/System/Library/Fonts/Supplemental/Arial Unicode.ttf')
        if not font.is_file():
            self.skipTest('Configure a local CJK font outside macOS')
        from interaction import Renderer as ActualRenderer, UnsupportedText
        renderer = ActualRenderer(font)
        self.assertTrue(renderer.pages('\u4e2d\u6587 ABC 123'))
        self.assertEqual(len(renderer.bitmap('\u4e2d\u6587')), PIXELS)
        with self.assertRaises(UnsupportedText): renderer.pages('\U0010ffff')
        review = Review(Desktop(), Broker(), renderer)
        review.sync();review.action('ok',review.token);review.change(2, '\U0010ffff')
        self.assertEqual(review.mode, 4)
        self.assertFalse(review.action('ok', review.token))
        pending = review.broker.add({'session_id':review.target,'tool_name':'\U0010ffff'})
        review.change(3, pending['text'], pending['id'])
        self.assertEqual(review.mode,4)
        review.action('cancel',review.token)
        self.assertEqual(pending['answer'],'deny')

class TranscriberTests(unittest.TestCase):
    def transcribe(self, raw, script='simplified'):
        try:
            import opencc
        except ImportError:self.skipTest('Install bridge requirements for Chinese normalization')
        from interaction import Transcriber
        with tempfile.TemporaryDirectory() as directory:
            model=Path(directory)/'model.bin';model.write_bytes(b'model')
            outputs=[]
            def whisper(args, **kwargs):
                self.assertEqual(args[args.index('-l')+1],'auto')
                out=Path(args[args.index('-of')+1]).with_suffix('.txt')
                out.write_text(raw,encoding='utf-8');outputs.append(out)
            with patch('interaction.subprocess.run',side_effect=whisper):
                text=Transcriber(model,chinese_script=script,backend='cli')(bytes(16000))
            self.assertTrue(all(not p.exists() for p in outputs))
            return text

    def test_mixed_script_normalizes_to_simplified_preserving_english(self):
        self.assertEqual(self.transcribe('現在選擇会話，請在後面繼續输入。Codex OK /tmp/test.py --foo=1\nSecond line.'),
                         '现在选择会话，请在后面继续输入。Codex OK /tmp/test.py --foo=1\nSecond line.')

    def test_only_voice_is_converted_and_accumulated(self):
        desktop=Desktop();desktop.drafts['one']='原有繁體草稿。'
        review=Review(desktop,Broker(),Renderer());review.sync();review.action('ok',review.token)
        review.action('record',review.token)
        review.transcript(self.transcribe('繼續輸入。'))
        review.action('record',review.token)
        review.transcript(self.transcribe('現在又變成了繁體中文。'))
        self.assertEqual(desktop.drafts['one'], '继续输入。现在又变成了繁体中文。')
        self.assertEqual(review.text, desktop.drafts['one'])
        self.assertEqual(desktop.sent,[])

    def test_traditional_and_keep_are_explicit_options(self):
        self.assertEqual(self.transcribe('现在选择会话。', 'traditional'),'現在選擇會話。')
        raw='現在选择会話。'
        self.assertEqual(self.transcribe(raw,'keep'),raw)

    def test_sentence_boundaries_on_consecutive_mixed_language_segments(self):
        desktop=Desktop();desktop.drafts['one']='已有繁體文字。'
        review=Review(desktop,Broker(),Renderer());review.sync();review.action('ok',review.token)
        for raw in ('第一句使用 Codex', 'Next sentence', '這是第三句？'):
            review.action('record',review.token)
            review.transcript(self.transcribe(raw))
        self.assertEqual(desktop.drafts['one'], '第一句使用 Codex。Next sentence.这是第三句？')
        self.assertEqual(review.text, desktop.drafts['one'])
        self.assertEqual(desktop.sent,[])

    def test_terminators_quotes_empty_and_trailing_commas(self):
        from speech import finish_sentence
        cases={'':'', '  ':'', 'Hello':'Hello.', '中文，':'中文。', 'Hello!':'Hello!',
               '真的吗？':'真的吗？', '「完成。」':'「完成。」', '"Done."':'"Done."',
               '继续…':'继续…', '段落一\n段落二':'段落一\n段落二。'}
        for raw,expected in cases.items():
            with self.subTest(raw=raw):self.assertEqual(finish_sentence(raw),expected)

class WhisperWorkerTests(unittest.TestCase):
    def test_reuses_owned_model_and_keeps_audio_on_loopback(self):
        from speech import WhisperWorker
        from unittest.mock import MagicMock
        process=MagicMock();process.poll.return_value=None
        health=MagicMock();health.status=200;health.read.return_value=b'{"status":"ok"}'
        result=MagicMock();result.status=200;result.read.return_value=b'{"text":"Codex test"}'
        connection=MagicMock();connection.getresponse.side_effect=[health,result,result]
        with patch('speech.subprocess.Popen',return_value=process) as popen, \
             patch('speech.http.client.HTTPConnection',return_value=connection) as http:
            worker=WhisperWorker('/tmp/test-model.bin','/usr/bin/whisper-server')
            try:
                worker.start();directory=Path(worker.directory.name)
                self.assertEqual(worker(bytes(16000)),'Codex test')
                self.assertEqual(worker(bytes(32000)),'Codex test')
                self.assertEqual(popen.call_count,1)
                args=popen.call_args.args[0]
                self.assertEqual(args[args.index('--host')+1],'127.0.0.1')
                self.assertEqual(args[args.index('-mc')+1],'0')
                self.assertEqual(args[args.index('--public')+1],str(directory))
                self.assertEqual(popen.call_args.kwargs['stdout'],__import__('subprocess').DEVNULL)
                for call in http.call_args_list:self.assertEqual(call.args[0],'127.0.0.1')
                posts=[c for c in connection.request.call_args_list if c.args[0]=='POST']
                self.assertEqual(len(posts),2)
                body=posts[0].args[2]
                self.assertIn(b'name="language"\r\n\r\nauto\r\n',body)
                self.assertIn(b'name="response_format"\r\n\r\njson\r\n',body)
                self.assertIn(b'RIFF',body)
            finally:worker.close()
            process.terminate.assert_called_once();process.wait.assert_called_once_with(timeout=3)
            self.assertFalse(directory.exists())

    def test_failed_inference_stops_worker_and_rejects_response(self):
        from speech import WhisperWorker
        from unittest.mock import MagicMock
        for status,data in ((500,b'{}'),(200,b'x'*65537),(200,b'{"text":null}'),(200,b'[]')):
            with self.subTest(status=status,size=len(data)):
                worker=WhisperWorker('/tmp/model.bin','whisper-server')
                worker.process=MagicMock();worker.process.poll.return_value=None
                worker.port=1234
                response=MagicMock();response.status=status;response.read.return_value=data
                connection=MagicMock();connection.getresponse.return_value=response
                process=worker.process
                with patch('speech.http.client.HTTPConnection',return_value=connection):
                    with self.assertRaises(ValueError):worker(bytes(16000))
                response.read.assert_called_once_with(65537)
                process.terminate.assert_called_once()
                self.assertIsNone(worker.process)

    def test_startup_failure_cleans_child_and_private_directory(self):
        from speech import WhisperWorker
        from unittest.mock import MagicMock
        process=MagicMock();process.poll.return_value=1
        worker=WhisperWorker('/tmp/model.bin','whisper-server')
        with patch('speech.subprocess.Popen',return_value=process) as popen:
            with self.assertRaises(OSError):worker.start()
        self.assertFalse(Path(popen.call_args.kwargs['cwd']).exists())
        self.assertIsNone(worker.process)

    def test_invalid_audio_never_starts_worker(self):
        from speech import WhisperWorker
        worker=WhisperWorker('/tmp/model.bin','whisper-server')
        with patch('speech.subprocess.Popen') as popen:
            for pcm in (bytes(16001),bytes(960002),bytes(4)):
                with self.assertRaises(ValueError):worker(pcm)
            popen.assert_not_called()

    def test_startup_timeout_forces_hung_child_to_stop(self):
        from speech import WhisperWorker
        from unittest.mock import MagicMock
        import subprocess
        process=MagicMock();process.poll.return_value=None
        process.wait.side_effect=[subprocess.TimeoutExpired('whisper-server',3),None]
        worker=WhisperWorker('/tmp/model.bin','whisper-server')
        with patch('speech.subprocess.Popen',return_value=process), \
             patch('speech.time.monotonic',side_effect=[0,26]):
            with self.assertRaises(OSError):worker.start()
        process.terminate.assert_called_once();process.kill.assert_called_once()
        self.assertIsNone(worker.directory)

    def test_next_recording_restarts_worker_after_inference_failure(self):
        from speech import WhisperWorker
        from unittest.mock import MagicMock
        process=MagicMock();process.poll.return_value=None
        health=MagicMock();health.status=200;health.read.return_value=b'{"status":"ok"}'
        failure=MagicMock();failure.status=500;failure.read.return_value=b'{}'
        result=MagicMock();result.status=200;result.read.return_value=b'{"text":"second recording"}'
        connection=MagicMock();connection.getresponse.side_effect=[health,failure,health,result]
        worker=WhisperWorker('/tmp/model.bin','whisper-server')
        with patch('speech.subprocess.Popen',return_value=process) as popen, \
             patch('speech.http.client.HTTPConnection',return_value=connection):
            try:
                with self.assertRaises(ValueError):worker(bytes(16000))
                self.assertEqual(worker(bytes(16000)),'second recording')
                self.assertEqual(popen.call_count,2)
            finally:worker.close()

    def test_restart_time_shares_the_inference_timeout_budget(self):
        from speech import WhisperWorker
        from unittest.mock import MagicMock
        worker=WhisperWorker('/tmp/model.bin','whisper-server');worker.port=1234
        response=MagicMock();response.status=200;response.read.return_value=b'{"text":"hello"}'
        connection=MagicMock();connection.getresponse.return_value=response
        with patch.object(worker,'start'),patch('speech.time.monotonic',side_effect=[0,10]), \
             patch('speech.http.client.HTTPConnection',return_value=connection) as http:
            self.assertEqual(worker(bytes(16000)),'hello')
        http.assert_called_once_with('127.0.0.1',1234,timeout=55)

class DesktopReconnectTests(unittest.TestCase):
    def write_draft(self, directory, text):
        import json
        state = {'electron-persisted-atom-state': {'composer-prompt-drafts-v2': {
            'local:one': {'prompt': text, 'pullRequestChecks': []},
            'local:other': {'prompt': 'other draft', 'pullRequestChecks': []}}}}
        (Path(directory) / '.codex-global-state.json').write_text(json.dumps(state))

    def test_stage_fills_only_voice_once_without_pc_state_or_acknowledgement(self):
        from interaction import Desktop as ActualDesktop
        from urllib.parse import urlparse, parse_qs
        with tempfile.TemporaryDirectory() as directory:
            desktop = ActualDesktop(directory)
            self.write_draft(directory, 'existing PC text')
            state = Path(directory) / '.codex-global-state.json'
            for stored in (state.read_text(), 'invalid JSON'):
                state.write_text(stored)
                with patch('interaction.sys.platform', 'darwin'), \
                        patch.object(desktop, 'owner', side_effect=EOFError()) as owner, \
                        patch.object(desktop, 'request') as request, \
                        patch('interaction.time.sleep') as sleep, \
                        patch('interaction.subprocess.run') as launch, \
                        patch.object(Path, 'read_text', side_effect=AssertionError('Must not read PC state')):
                    desktop.stage('one/encoded', 'voice & +\nnext')
                    launch.assert_called_once(); owner.assert_not_called()
                    request.assert_not_called(); sleep.assert_not_called()
                    route = urlparse(launch.call_args.args[0][-1])
                    self.assertEqual((route.scheme, route.netloc, route.path), ('codex', 'threads', '/one%2Fencoded'))
                    self.assertEqual(parse_qs(route.query), {'prompt': ['voice & +\nnext']})
                    self.assertEqual(launch.call_args.args[0][:3], ['open', '-b', 'com.openai.codex'])
                    self.assertEqual(launch.call_args.kwargs['timeout'], 5)
                self.assertEqual(state.read_text(), stored)

    def test_filling_error_preserves_voice_preview_without_ipc_or_retry(self):
        from interaction import Desktop as ActualDesktop
        import subprocess
        for error in (OSError(), subprocess.TimeoutExpired('open', 5), subprocess.CalledProcessError(1, 'open')):
            with self.subTest(error=type(error)), tempfile.TemporaryDirectory() as directory:
                desktop = ActualDesktop(directory)
                with patch.object(desktop, 'sessions', return_value=Desktop().sessions()), \
                        patch.object(desktop, 'projects', return_value=Desktop().projects()), \
                        patch.object(desktop, 'request') as request, \
                        patch('interaction.sys.platform', 'darwin'), \
                        patch('interaction.subprocess.run', side_effect=error) as launch:
                    review = Review(desktop, Broker(), Renderer()); review.sync(); review.action('ok', review.token)
                    self.assertTrue(review.action('record', review.token)); review.transcript('voice')
                    self.assertEqual((review.mode, review.text), (2, 'voice'))
                    review.sync(); review.screen()
                    launch.assert_called_once(); request.assert_not_called()

    def test_confirm_sends_only_device_transcript_without_pc_draft_or_ack(self):
        from interaction import Desktop as ActualDesktop
        with tempfile.TemporaryDirectory() as directory:
            desktop = ActualDesktop(directory)
            self.write_draft(directory, 'existing PC text')
            with patch.object(desktop, 'sessions', return_value=Desktop().sessions()), \
                    patch.object(desktop, 'projects', return_value=Desktop().projects()), \
                    patch.object(desktop, 'owner', return_value='owner') as owner, \
                    patch.object(desktop, 'request') as request, \
                    patch('interaction.sys.platform', 'darwin'), patch('interaction.subprocess.run') as launch, \
                    patch('interaction.time.sleep') as sleep:
                review = Review(desktop, Broker(), Renderer()); review.sync(); review.action('ok', review.token)
                review.action('record', review.token); review.transcript('voice only')
                owner.assert_not_called(); request.assert_not_called()
                token = review.token
                self.write_draft(directory, 'edited on PC')
                review.sync(); self.assertEqual(review.token, token)
                self.assertTrue(review.action('ok', token))
                self.assertFalse(review.action('ok', token))
                owner.assert_called_once_with('one'); request.assert_called_once()
                method, params, version, target = request.call_args.args
                self.assertEqual((method, version, target), ('thread-follower-start-turn', 2, 'owner'))
                self.assertEqual(params['conversationId'], 'one')
                self.assertEqual(params['turnStart']['request']['input'][0]['text'], 'voice only')
                launch.assert_called_once(); sleep.assert_not_called()

    def test_empty_or_oversized_voice_never_launches_input_filling(self):
        from interaction import Desktop as ActualDesktop
        desktop = ActualDesktop()
        with patch('interaction.sys.platform', 'darwin'), patch('interaction.subprocess.run') as launch:
            for text in ('', '   ', 'x' * 12001):
                with self.subTest(size=len(text)), self.assertRaises(ValueError):
                    desktop.stage('one', text)
            launch.assert_not_called()

    def test_new_chat_preparation_pins_migrated_project_without_creating_or_sending(self):
        from interaction import Desktop as ActualDesktop, PROJECTLESS
        desktop = ActualDesktop()
        state = {'local-projects': {'legacy': {'name': 'Project'}},
                 'app-server-project-id-by-legacy-project-id-by-host': {'local': {'legacy':'server'}}}
        with patch.object(desktop, 'projects', return_value=[{'id':'server','name':'Project'}]), patch.object(
                desktop, 'project_state', return_value=state), patch('interaction.sys.platform', 'darwin'), patch(
                'interaction.cli_path', return_value='/codex') as cli, patch.object(
                desktop, 'project_roots', return_value={'server':[tempfile.gettempdir()]}) as roots, patch(
                'interaction.subprocess.Popen') as launch:
            desktop.new_session('server')
            roots.assert_called_once_with(state); cli.assert_called_once(); launch.assert_not_called()
            with self.assertRaises(ValueError): desktop.new_session(PROJECTLESS)
            with self.assertRaises(ValueError): desktop.new_session('missing')

    def test_cli_owned_chat_cannot_be_opened_or_submitted_by_desktop(self):
        from interaction import Desktop as ActualDesktop
        desktop = ActualDesktop()
        with patch.object(desktop.new_chats, 'owns', return_value=True), patch.object(
                desktop, 'request') as request, patch('interaction.subprocess.run') as launch:
            with self.assertRaises(RuntimeError): desktop.send('new', 'followup')
            with self.assertRaises(RuntimeError): desktop.stage('new', 'followup')
            request.assert_not_called(); launch.assert_not_called()

    def test_project_catalog_deduplicates_migration_and_preserves_equal_names(self):
        from interaction import Desktop as ActualDesktop
        import json
        with tempfile.TemporaryDirectory() as directory:
            with closing(sqlite3.connect(str(Path(directory)/'state_5.sqlite'))) as db:
                db.execute('CREATE TABLE projects(id TEXT,name TEXT)')
                db.executemany('INSERT INTO projects VALUES(?,?)', [('server','Old name'),('other','Same name')])
                db.commit()
            (Path(directory)/'.codex-global-state.json').write_text(json.dumps({
                'local-projects':{'legacy':{'name':'Same name'},'empty':{'name':'Empty project'}},
                'app-server-project-id-by-legacy-project-id-by-host':{'local':{'legacy':'server'}}}))
            projects = ActualDesktop(directory).projects()
            self.assertEqual({p['id']: p['name'] for p in projects},
                             {'server':'Same name','other':'Same name','empty':'Empty project'})

    def test_catalog_includes_unloaded_chats_without_owner_discovery(self):
        from interaction import Desktop as ActualDesktop
        with tempfile.TemporaryDirectory() as directory:
            with closing(sqlite3.connect(str(Path(directory)/'state_5.sqlite'))) as db:
                db.execute('CREATE TABLE threads(id TEXT,title TEXT,name TEXT,project_id TEXT,cwd TEXT,archived INTEGER,agent_path TEXT,updated_at INTEGER)')
                db.execute('CREATE TABLE projects(id TEXT,name TEXT)')
                db.execute("INSERT INTO projects VALUES('p','Project name')")
                db.executemany('INSERT INTO threads VALUES(?,\'First user prompt\',?,\'p\',\'/repo\',0,NULL,?)', [('closed','Old',2),('live','Current',1)])
                db.commit()
            desktop=ActualDesktop(directory)
            with patch.object(desktop,'owner',side_effect=EOFError('Connection closed')) as owner:
                self.assertEqual(desktop._scan_sessions(),[
                    {'id':'closed','title':'Old','project':'Project name','project_id':'p'},
                    {'id':'live','title':'Current','project':'Project name','project_id':'p'}])
                owner.assert_not_called()

    def test_legacy_project_assignment_and_renamed_titles(self):
        from interaction import Desktop as ActualDesktop
        import json
        with tempfile.TemporaryDirectory() as directory:
            with closing(sqlite3.connect(str(Path(directory)/'state_5.sqlite'))) as db:
                db.execute('CREATE TABLE threads(id TEXT,title TEXT,name TEXT,project_id TEXT,cwd TEXT,archived INTEGER,agent_path TEXT,updated_at INTEGER)')
                db.execute('CREATE TABLE projects(id TEXT,name TEXT)')
                db.executemany('INSERT INTO threads VALUES(?,\'First prompt\',?,NULL,?,0,NULL,1)',
                               [('assigned','Actual title','/worktree/a'),('nested',None,'/repo/sub/path'),('loose',None,'/repo'),('unnamed',None,'/elsewhere')])
                db.commit()
            (Path(directory)/'.codex-global-state.json').write_text(json.dumps({
                'local-projects':{'p':{'name':'Renamed project','rootPaths':['/repo']},
                                  'sub':{'name':'Nested project','rootPaths':['/repo/sub']}},
                'thread-project-assignments':{'assigned':{'projectKind':'local','projectId':'p'}},
                'thread-titles':{'titles':{'nested':'Saved title'}},
                'projectless-thread-ids':['loose']}))
            desktop=ActualDesktop(directory)
            with patch.object(desktop,'owner',return_value='owner'):
                found={s['id']:s for s in desktop._scan_sessions()}
                self.assertEqual(found['assigned']['project'],'Renamed project')
                self.assertEqual(found['assigned']['project_id'],'p')
                self.assertEqual(found['nested']['project'],'Nested project')
                self.assertEqual(found['nested']['project_id'],'sub')
                self.assertEqual(found['nested']['title'],'Saved title')
                self.assertEqual(found['loose']['project'],'No project')
                self.assertEqual(found['loose']['project_id'],'__projectless__')
                self.assertEqual(found['unnamed']['title'],'Untitled chat')

    def test_project_lists_all_saved_chats_beyond_recent_80_with_host_migration(self):
        from interaction import Desktop as ActualDesktop
        import json
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with closing(sqlite3.connect(str(root / 'state_5.sqlite'))) as db:
                db.execute('CREATE TABLE threads(id TEXT,name TEXT,project_id TEXT,cwd TEXT,archived INTEGER,agent_path TEXT,updated_at INTEGER)')
                db.execute('CREATE TABLE projects(id TEXT,name TEXT)')
                db.executemany('INSERT INTO projects VALUES(?,?)', [('server','Saved project'),('other','Recent project')])
                db.executemany('INSERT INTO threads VALUES(?,?,?,NULL,0,NULL,?)',
                               [(f'recent-{i}',f'Recent {i}','other',100+i) for i in range(90)] +
                               [('old-one','First saved chat',None,2),('old-two','Second saved chat',None,1)])
                db.execute("INSERT INTO threads VALUES('archived','Archived','server',NULL,1,NULL,0)")
                db.execute("INSERT INTO threads VALUES('child','Subagent','server',NULL,0,'/root/child',0)")
                db.commit()
            (root / '.codex-global-state.json').write_text(json.dumps({
                'local-projects': {'legacy': {'name':'Saved project','rootPaths':['/repo']}},
                'thread-project-assignments': {thread: {'projectKind':'local','projectId':'legacy'}
                                               for thread in ('old-one','old-two')},
                'app-server-project-id-by-legacy-project-id-by-host': {
                    'local:' + str(root.resolve()): {'legacy':'server'},
                    'local:/different/account': {'legacy':'wrong-server'}}}))
            desktop = ActualDesktop(directory)
            with patch.object(desktop, 'owner', side_effect=TimeoutError()) as owner:
                desktop._sessions = desktop._scan_sessions()
                desktop._refreshed = time.monotonic()
                self.assertEqual(len(desktop.sessions()), 92)
                self.assertEqual({p['id'] for p in desktop.projects()}, {'server','other'})
                review = Review(desktop, Broker(), Renderer())
                review.project = 'server'
                review.screen()
                self.assertIn('2 sessions', review.renderer.last)
                self.assertTrue(review.action('ok', review.token))
                review.screen()
                self.assertIn('First saved chat', review.renderer.last)
                self.assertIn('Second saved chat', review.renderer.last)
                self.assertNotIn('No sessions', review.renderer.last)
                self.assertNotIn('Recent ', review.renderer.last)
                self.assertEqual(review.target, 'old-one')
                self.assertTrue(review.action('down', review.token))
                self.assertEqual(review.target, 'old-two')
                owner.assert_not_called()

    def test_refresh_recovers_after_desktop_restart(self):
        from interaction import Desktop as ActualDesktop
        desktop=ActualDesktop()
        completed=threading.Event()
        def scan():
            completed.set()
            raise EOFError('Connection closed')
        with patch.object(desktop,'_scan_sessions',side_effect=scan):
            self.assertEqual(desktop.sessions(),[])
            self.assertTrue(completed.wait(1))
            deadline=time.monotonic()+1
            while desktop._refreshing and time.monotonic()<deadline: time.sleep(0.001)
            self.assertFalse(desktop._refreshing)
        with desktop._lock: desktop._refreshed=0
        with patch.object(desktop,'_scan_sessions',return_value=[{'id':'new','title':'Restored'}]):
            desktop.sessions()
            deadline=time.monotonic()+1
            while desktop._refreshing and time.monotonic()<deadline: time.sleep(0.001)
            self.assertEqual(desktop.sessions(),[{'id':'new','title':'Restored'}])

if __name__ == '__main__': unittest.main()
